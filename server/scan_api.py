# -*- coding: utf-8 -*-
"""
蜗牛AI Business Opportunity Scan — API 路由
==============================================
所有 /api/scan/* 和 /api/admin/scan/* 路由
"""
import json
import os
import re
import uuid
import time
import logging
import sqlite3
import datetime
from pathlib import Path
from functools import wraps

from flask import request, jsonify, send_file, send_from_directory

from scan_models import (
    init_scan_tables, detect_sensitive_content, sanitize_input,
    normalise_email, generate_public_token, hash_token,
    LEAD_FIT_BANDS, INDUSTRY_GROUPS, EMPLOYEE_BANDS,
    is_sydney_postcode, SCAN_STATUSES, SALES_STATUSES,
    SensitiveDetectionResult,
)

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
AI_MODEL = os.environ.get("AI_MODEL", "glm-5.3-flash")
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT_SECONDS", "120"))
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "2"))

REPORT_TOKEN_SECRET = os.environ.get("REPORT_TOKEN_SECRET", "")
REPORT_LINK_EXPIRY_DAYS = int(os.environ.get("REPORT_LINK_EXPIRY_DAYS", "30"))
REPORT_RETENTION_DAYS = int(os.environ.get("REPORT_RETENTION_DAYS", "90"))

GMAIL_USER = os.environ.get("GMAIL_USER", "robin@snailai.ai")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ROBIN_NOTIFICATION_EMAIL = os.environ.get("ROBIN_NOTIFICATION_EMAIL", "robin12300@gmail.com")
WECHAT_WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")

# 报告文件存放目录
REPORT_DIR = Path(os.environ.get("SCAN_REPORT_DIR", "/data/scan-reports"))


# ──────────────────────────────────────────────
# DB 辅助
# ──────────────────────────────────────────────

def _db():
    """获取数据库连接"""
    from app import db_conn
    return db_conn()


def _scan_db():
    """获取独立连接（用于事务性操作）"""
    from app import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
# Admin 鉴权
# ──────────────────────────────────────────────

def _require_admin(f):
    """装饰器：要求管理员权限"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        from app import _token_from_req, _current_user
        token = _token_from_req()
        if not token:
            return jsonify(ok=False, error="Unauthorized"), 401
        user = _current_user()
        if not user or user.get("role") not in ("admin", "instructor"):
            return jsonify(ok=False, error="Forbidden"), 403
        return f(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────
# Turnstile 验证
# ──────────────────────────────────────────────

def _verify_turnstile(token: str, remote_ip: str) -> bool:
    """验证 Cloudflare Turnstile token"""
    if not TURNSTILE_SECRET_KEY:
        log.warning("[scan] TURNSTILE_SECRET_KEY not set; skipping verification")
        return True  # 未配置时跳过（开发模式）
    try:
        import requests as http
        resp = http.post(TURNSTILE_VERIFY_URL, data={
            "secret": TURNSTILE_SECRET_KEY,
            "response": token,
            "remoteip": remote_ip,
        }, timeout=10)
        result = resp.json()
        return result.get("success", False)
    except Exception as e:
        log.error(f"[scan] Turnstile verification failed: {e}")
        return False


# ──────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────

# 前端 start.html 按分步结构（step1..step6）收集数据；
# 后端验证/清洗/入库全部使用扁平 key。此映射表负责把嵌套结构拍平。
# 前端字段名 → 后端字段名；同名步骤内字段不改名的直接合并。
_FRONTEND_STEP_FIELD_MAP = {
    "step1": {
        "full_name": "full_name", "work_email": "work_email",
        "mobile": "mobile_number", "company_name": "company_name",
        "company_website": "company_website",
        "website_consent": "website_review_consent",
        "suburb": "suburb", "postcode": "postcode", "role": "role",
        "decision_authority": "decision_authority",
        "employees": "employee_band",
    },
    "step2": {
        "industry_group": "industry_group", "sub_industry": "sub_industry",
        "years_operating": "years_operating", "business_model": "business_model",
        "primary_goal": "primary_goal",
    },
    "step3": {
        "general_tools": "tools", "industry_tools": "industry_tools",
        "integration": "systems_integration",
        "reentry_frequency": "re_entry_frequency",
    },
    "step4": {
        "pain_description": "main_pain_process",
        "pain_frequency": "pain_frequency",
        "people_involved": "people_involved", "weekly_hours": "weekly_hours",
        "what_goes_wrong": "what_goes_wrong",
        "success_description": "success_looks_like",
        "workflows": "industry_workflows",
        "top_priority": "top_workflow_priority",
    },
    "step5": {
        "process_documented": "process_documented",
        "process_champion": "process_owner_exists",
        "willing_pilot": "pilot_willingness",
        "automation_level": "automation_level",
        "data_sensitivity": "data_sensitivity",
        "desired_start": "desired_start_time",
        "budget": "indicative_budget",
        "preferred_contact_method": "preferred_contact_method",
        "onsite_assessment": "onsite_assessment_interest",
    },
    "step6": {
        "consent_report": "consent_report",
        "consent_no_personal": "consent_no_sensitive",
        "consent_privacy": "consent_privacy",
        "consent_email": "consent_email_delivery",
        "newsletter": "marketing_opt_in",
    },
}


def _flatten_payload(data: dict) -> dict:
    """兼容前端嵌套格式（step1..step6）与旧扁平格式，统一输出扁平 key。"""
    flat = dict(data)  # 保留 turnstile_token / idempotency_key / utm 等
    flat.pop("utm", None)
    if isinstance(data.get("utm"), dict):
        for k, v in data["utm"].items():
            flat[k] = v
    for step, mapping in _FRONTEND_STEP_FIELD_MAP.items():
        step_data = data.get(step)
        if not isinstance(step_data, dict):
            continue
        for fe_key, be_key in mapping.items():
            if fe_key in step_data:
                flat[be_key] = step_data[fe_key]
    return flat


def api_scan_submit():
    """
    POST /api/scan/submit
    接收问卷提交，返回 scan_id 和处理状态。
    幂等：如果 idempotency_key 已存在，返回已有记录。
    """
    data = _flatten_payload(request.get_json(silent=True) or {})
    remote_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    # 1. Turnstile 验证
    turnstile_token = data.get("turnstile_token", "")
    if not _verify_turnstile(turnstile_token, remote_ip):
        return jsonify(ok=False, error="CAPTCHA verification failed"), 400

    # 2. 幂等性检查
    idem_key = data.get("idempotency_key", "")
    if idem_key:
        conn = _scan_db()
        try:
            row = conn.execute(
                "SELECT id, status FROM scan_submissions WHERE idempotency_key=?",
                (idem_key,)
            ).fetchone()
            if row:
                return jsonify(ok=True, scan_id=row["id"], status=row["status"], duplicate=True)
        finally:
            conn.close()

    # 3. 输入验证
    errors = _validate_submission(data)
    if errors:
        return jsonify(ok=False, errors=errors), 400

    # 4. 敏感内容检测
    free_text_fields = [
        data.get("main_pain_process", ""),
        data.get("success_looks_like", ""),
    ]
    is_medical = data.get("industry_group") == "C"
    all_text = " ".join(free_text_fields)
    detection = detect_sensitive_content(all_text, is_medical=is_medical)
    if detection.blocked:
        _log_sensitive_event("BLOCKED", detection)
        return jsonify(ok=False, error="Your submission appears to contain sensitive personal information. Please describe business processes only, without entering personal, client, patient or confidential data.", flags=detection.flags), 400

    # 5. 生成 ID 和 token
    scan_id = str(uuid.uuid4())
    public_token = generate_public_token()
    token_hash = hash_token(public_token)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    retention_date = (datetime.datetime.utcnow() + datetime.timedelta(days=REPORT_RETENTION_DAYS)).isoformat() + "Z"

    # 6. 清洗输入
    clean = _clean_submission(data)

    # 7. 写入数据库
    conn = _scan_db()
    try:
        conn.execute("""
            INSERT INTO scan_submissions (
                id, public_token_hash, created_at, updated_at, status,
                full_name, work_email, mobile_number, company_name, company_website,
                suburb, postcode, role, decision_authority, employee_band,
                industry_group, sub_industry, years_operating, business_model, primary_goal,
                tools_json, industry_tools_json, systems_integration, re_entry_frequency,
                main_pain_process, pain_frequency, people_involved, weekly_hours,
                what_goes_wrong_json, success_looks_like,
                industry_workflows_json, top_workflow_priority,
                process_documented, process_owner_exists, pilot_willingness, automation_level,
                data_sensitivity, desired_start_time, indicative_budget, onsite_assessment_interest,
                preferred_contact_method,
                website_review_consent,
                consent_report, consent_no_sensitive, consent_privacy, consent_email_delivery,
                marketing_opt_in,
                source, utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                retention_delete_at, idempotency_key, turnstile_token
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
        """, (
            scan_id, token_hash, now, now, "NEW",
            clean["full_name"], normalise_email(clean["work_email"]), clean.get("mobile_number", ""),
            clean["company_name"], clean.get("company_website", ""),
            clean["suburb"], clean["postcode"], clean["role"], clean["decision_authority"], clean["employee_band"],
            clean["industry_group"], clean["sub_industry"], clean.get("years_operating", ""),
            clean.get("business_model", ""), clean.get("primary_goal", ""),
            json.dumps(clean.get("tools", [])), json.dumps(clean.get("industry_tools", [])),
            clean.get("systems_integration", ""), clean.get("re_entry_frequency", ""),
            sanitize_input(clean.get("main_pain_process", ""), 600),
            clean.get("pain_frequency", ""), clean.get("people_involved", ""),
            clean.get("weekly_hours", ""),
            json.dumps(clean.get("what_goes_wrong", [])),
            sanitize_input(clean.get("success_looks_like", ""), 500),
            json.dumps(clean.get("industry_workflows", [])),
            clean.get("top_workflow_priority", ""),
            clean.get("process_documented", ""), clean.get("process_owner_exists", ""),
            clean.get("pilot_willingness", ""), clean.get("automation_level", ""),
            clean.get("data_sensitivity", ""), clean.get("desired_start_time", ""),
            clean.get("indicative_budget", ""), clean.get("onsite_assessment_interest", ""),
            clean.get("preferred_contact_method", ""),
            1 if clean.get("website_review_consent") else 0,
            1 if clean.get("consent_report") else 0,
            1 if clean.get("consent_no_sensitive") else 0,
            1 if clean.get("consent_privacy") else 0,
            1 if clean.get("consent_email_delivery") else 0,
            1 if clean.get("marketing_opt_in") else 0,
            clean.get("source", ""), clean.get("utm_source", ""),
            clean.get("utm_medium", ""), clean.get("utm_campaign", ""),
            clean.get("utm_content", ""), clean.get("utm_term", ""),
            retention_date, idem_key or None, turnstile_token,
        ))

        # 初始分析记录
        conn.execute("""
            INSERT INTO scan_analysis (scan_id, created_at, pipeline_stage)
            VALUES (?, ?, 'PENDING')
        """, (scan_id, now))

        # 活动日志
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'CREATED', 'system', ?, ?)
        """, (scan_id, json.dumps({"industry_group": clean["industry_group"]}), now))

        conn.commit()
    finally:
        conn.close()

    log.info(f"[scan] New submission: {scan_id[:8]}... industry={clean['industry_group']} company={clean['company_name'][:30]}")

    # 8. 触发异步处理（由后台 worker 拾取）
    # V1 使用 APScheduler 在当前进程内处理
    try:
        _enqueue_processing(scan_id)
    except Exception as e:
        log.error(f"[scan] Failed to enqueue processing for {scan_id}: {e}")

    return jsonify(ok=True, scan_id=scan_id, public_token=public_token, status="NEW")


def api_scan_status(scan_id):
    """
    GET /api/scan/<scan_id>/status
    查询处理状态
    """
    conn = _scan_db()
    try:
        sub = conn.execute(
            "SELECT id, status, created_at FROM scan_submissions WHERE id=?",
            (scan_id,)
        ).fetchone()
        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        analysis = conn.execute(
            "SELECT pipeline_stage, pipeline_error FROM scan_analysis WHERE scan_id=?",
            (scan_id,)
        ).fetchone()

        return jsonify(ok=True, status=sub["status"],
                       pipeline_stage=analysis["pipeline_stage"] if analysis else None,
                       pipeline_error=analysis["pipeline_error"] if analysis else None)
    finally:
        conn.close()


def api_scan_report(public_token):
    """
    GET /api/scan/report/<public_token>
    查看安全报告（需要有效 token，未过期，未撤销）
    """
    token_hash = hash_token(public_token)
    conn = _scan_db()
    try:
        report = conn.execute("""
            SELECT r.*, s.status as sub_status, s.company_name
            FROM scan_reports r
            JOIN scan_submissions s ON r.scan_id = s.id
            WHERE r.secure_token_hash=?
        """, (token_hash,)).fetchone()

        if not report:
            return jsonify(ok=False, error="Report not found"), 404

        # 检查过期
        if report["expires_at"] < datetime.datetime.utcnow().isoformat() + "Z":
            return jsonify(ok=False, error="Report link has expired"), 410

        # 检查撤销
        if report["revoked_at"]:
            return jsonify(ok=False, error="Report link has been revoked"), 403

        # 记录访问
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'REPORT_VIEWED', 'visitor', ?, ?)
        """, (report["scan_id"], json.dumps({"token_prefix": public_token[:8]}), now))
        conn.commit()

        # 返回渲染的 HTML
        if report["rendered_html"]:
            return report["rendered_html"], 200, {"Content-Type": "text/html; charset=utf-8",
                                                    "X-Robots-Tag": "noindex, nofollow"}
        return jsonify(ok=False, error="Report content not available"), 500
    finally:
        conn.close()


def api_scan_report_pdf(public_token):
    """
    GET /api/scan/report/<public_token>/pdf
    下载 PDF 报告
    """
    token_hash = hash_token(public_token)
    conn = _scan_db()
    try:
        report = conn.execute("""
            SELECT r.*, s.status as sub_status
            FROM scan_reports r
            JOIN scan_submissions s ON r.scan_id = s.id
            WHERE r.secure_token_hash=?
        """, (token_hash,)).fetchone()

        if not report:
            return jsonify(ok=False, error="Not found"), 404
        if report["expires_at"] < datetime.datetime.utcnow().isoformat() + "Z":
            return jsonify(ok=False, error="Expired"), 410
        if report["revoked_at"]:
            return jsonify(ok=False, error="Revoked"), 403

        if not report["pdf_path"]:
            return jsonify(ok=False, error="PDF not yet generated"), 404

        pdf_file = REPORT_DIR / report["pdf_path"]
        if not pdf_file.exists():
            return jsonify(ok=False, error="PDF file missing"), 500

        # 记录下载
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'PDF_DOWNLOADED', 'visitor', ?, ?)
        """, (report["scan_id"], json.dumps({"token_prefix": public_token[:8]}), now))
        conn.commit()

        return send_file(str(pdf_file), mimetype="application/pdf",
                         as_attachment=True, download_name=f"Snail-AI-Business-Opportunity-Report.pdf")
    finally:
        conn.close()


def api_scan_call_request(public_token):
    """
    POST /api/scan/report/<public_token>/call-request
    客户申请 20 分钟电话
    """
    token_hash = hash_token(public_token)
    data = request.get_json(silent=True) or {}
    conn = _scan_db()
    try:
        sub = conn.execute("""
            SELECT s.id, s.work_email, s.company_name
            FROM scan_submissions s
            JOIN scan_reports r ON r.scan_id = s.id
            WHERE r.secure_token_hash=?
        """, (token_hash,)).fetchone()

        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'CALL_REQUESTED', 'visitor', ?, ?)
        """, (sub["id"], json.dumps({"preferred_time": data.get("preferred_time", "")}), now))

        # 更新销售状态
        conn.execute("UPDATE scan_submissions SET sales_status='CALL_REQUESTED', updated_at=? WHERE id=?",
                     (now, sub["id"]))
        conn.commit()

        # 通知 Robin
        _notify_robin_call_request(sub["id"], sub["company_name"], sub["work_email"], data)

        return jsonify(ok=True)
    finally:
        conn.close()


def api_scan_onsite_application(public_token):
    """
    POST /api/scan/report/<public_token>/onsite-application
    客户申请两小时现场评估
    """
    token_hash = hash_token(public_token)
    data = request.get_json(silent=True) or {}
    conn = _scan_db()
    try:
        sub = conn.execute("""
            SELECT s.id, s.work_email, s.company_name, s.employee_band, s.suburb
            FROM scan_submissions s
            JOIN scan_reports r ON r.scan_id = s.id
            WHERE r.secure_token_hash=?
        """, (token_hash,)).fetchone()

        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'ONSITE_APPLIED', 'visitor', ?, ?)
        """, (sub["id"], json.dumps({
            "employee_band": sub["employee_band"],
            "suburb": sub["suburb"],
            "message": sanitize_input(data.get("message", ""), 500),
        }), now))

        conn.execute("UPDATE scan_submissions SET sales_status='ONSITE_APPROVED', updated_at=? WHERE id=?",
                     (now, sub["id"]))
        conn.commit()

        # 通知 Robin
        _notify_robin_onsite_application(sub["id"], sub["company_name"], sub["employee_band"], sub["suburb"])

        return jsonify(ok=True)
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Admin API
# ──────────────────────────────────────────────

@_require_admin
def api_admin_scan_list():
    """GET /api/admin/scan/list"""
    page = int(request.args.get("page", "1"))
    per_page = int(request.args.get("per_page", "20"))
    status_filter = request.args.get("status", "")
    sales_filter = request.args.get("sales_status", "")
    search = request.args.get("search", "")

    offset = (page - 1) * per_page
    where_parts = ["1=1"]
    params = []

    if status_filter:
        where_parts.append("s.status=?")
        params.append(status_filter)
    if sales_filter:
        where_parts.append("s.sales_status=?")
        params.append(sales_filter)
    if search:
        where_parts.append("(s.company_name LIKE ? OR s.full_name LIKE ? OR s.work_email LIKE ?)")
        params.extend([f"%{search}%"] * 3)

    where = " AND ".join(where_parts)

    conn = _scan_db()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM scan_submissions s WHERE {where}", params).fetchone()[0]
        rows = conn.execute(f"""
            SELECT s.id, s.created_at, s.company_name, s.full_name, s.suburb,
                   s.industry_group, s.employee_band, s.sales_status, s.status,
                   a.deterministic_scores_json, a.pipeline_stage
            FROM scan_submissions s
            LEFT JOIN scan_analysis a ON a.scan_id = s.id
            WHERE {where}
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()

        items = []
        for r in rows:
            scores = json.loads(r["deterministic_scores_json"]) if r["deterministic_scores_json"] else {}
            items.append({
                "id": r["id"],
                "created_at": r["created_at"],
                "company_name": r["company_name"],
                "full_name": r["full_name"],
                "suburb": r["suburb"],
                "industry_group": r["industry_group"],
                "employee_band": r["employee_band"],
                "sales_status": r["sales_status"],
                "status": r["status"],
                "lead_fit_score": scores.get("lead_fit_score"),
                "lead_fit_band": scores.get("lead_fit_band"),
                "pipeline_stage": r["pipeline_stage"],
            })

        return jsonify(ok=True, items=items, total=total, page=page, per_page=per_page)
    finally:
        conn.close()


@_require_admin
def api_admin_scan_detail(scan_id):
    """GET /api/admin/scan/<scan_id>"""
    conn = _scan_db()
    try:
        sub = conn.execute("SELECT * FROM scan_submissions WHERE id=?", (scan_id,)).fetchone()
        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        analysis = conn.execute("SELECT * FROM scan_analysis WHERE scan_id=?", (scan_id,)).fetchone()
        report = conn.execute("SELECT * FROM scan_reports WHERE scan_id=?", (scan_id,)).fetchone()
        activities = conn.execute(
            "SELECT * FROM scan_activities WHERE scan_id=? ORDER BY created_at DESC LIMIT 50",
            (scan_id,)
        ).fetchall()

        return jsonify(ok=True, submission=dict(sub), analysis=dict(analysis) if analysis else None,
                       report=dict(report) if report else None,
                       activities=[dict(a) for a in activities])
    finally:
        conn.close()


@_require_admin
def api_admin_scan_regenerate(scan_id):
    """POST /api/admin/scan/<scan_id>/regenerate"""
    conn = _scan_db()
    try:
        sub = conn.execute("SELECT id, status FROM scan_submissions WHERE id=?", (scan_id,)).fetchone()
        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("UPDATE scan_submissions SET status='NEW', updated_at=? WHERE id=?", (now, scan_id))
        conn.execute("UPDATE scan_analysis SET pipeline_stage='PENDING', pipeline_error=NULL WHERE scan_id=?", (scan_id,))
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'REGENERATED', ?, ?, ?)
        """, (scan_id, f"admin:{request.headers.get('X-Admin-User', 'unknown')}",
              json.dumps({"trigger": "manual"}), now))
        conn.commit()
    finally:
        conn.close()

    _enqueue_processing(scan_id)
    return jsonify(ok=True)


@_require_admin
def api_admin_scan_resend(scan_id):
    """POST /api/admin/scan/<scan_id>/resend"""
    conn = _scan_db()
    try:
        sub = conn.execute("SELECT * FROM scan_submissions WHERE id=?", (scan_id,)).fetchone()
        if not sub:
            return jsonify(ok=False, error="Not found"), 404

        # 重发邮件
        _send_report_email(scan_id)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'EMAIL_SENT', ?, ?, ?)
        """, (scan_id, f"admin:{request.headers.get('X-Admin-User', 'unknown')}",
              json.dumps({"trigger": "manual_resend"}), now))
        conn.commit()
    finally:
        conn.close()

    return jsonify(ok=True)


@_require_admin
def api_admin_scan_revoke(scan_id):
    """POST /api/admin/scan/<scan_id>/revoke"""
    conn = _scan_db()
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("UPDATE scan_reports SET revoked_at=? WHERE scan_id=?", (now, scan_id))
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'TOKEN_REVOKED', ?, ?, ?)
        """, (scan_id, f"admin:{request.headers.get('X-Admin-User', 'unknown')}",
              json.dumps({}), now))
        conn.commit()
    finally:
        conn.close()

    return jsonify(ok=True)


@_require_admin
def api_admin_scan_update_status(scan_id):
    """PATCH /api/admin/scan/<scan_id>/status"""
    data = request.get_json(silent=True) or {}
    new_status = data.get("sales_status", "")
    if new_status not in SALES_STATUSES:
        return jsonify(ok=False, error="Invalid status"), 400

    internal_notes = data.get("internal_notes")

    conn = _scan_db()
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        if internal_notes is not None:
            conn.execute("UPDATE scan_submissions SET sales_status=?, internal_notes=?, updated_at=? WHERE id=?",
                         (new_status, internal_notes, now, scan_id))
        else:
            conn.execute("UPDATE scan_submissions SET sales_status=?, updated_at=? WHERE id=?",
                         (new_status, now, scan_id))

        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'STATUS_CHANGED', ?, ?, ?)
        """, (scan_id, f"admin:{request.headers.get('X-Admin-User', 'unknown')}",
              json.dumps({"new_status": new_status}), now))
        conn.commit()
    finally:
        conn.close()

    return jsonify(ok=True)


@_require_admin
def api_admin_scan_delete(scan_id):
    """DELETE /api/admin/scan/<scan_id>"""
    conn = _scan_db()
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("UPDATE scan_submissions SET status='DELETION_SCHEDULED', updated_at=? WHERE id=?",
                     (now, scan_id))
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'DELETED', ?, ?, ?)
        """, (scan_id, f"admin:{request.headers.get('X-Admin-User', 'unknown')}",
              json.dumps({"trigger": "admin_delete"}), now))
        conn.commit()
    finally:
        conn.close()

    return jsonify(ok=True)


@_require_admin
def api_admin_scan_export():
    """GET /api/admin/scan/export — 导出 CSV"""
    conn = _scan_db()
    try:
        rows = conn.execute("""
            SELECT s.id, s.created_at, s.company_name, s.full_name, s.suburb,
                   s.industry_group, s.employee_band, s.sales_status, s.status,
                   a.deterministic_scores_json
            FROM scan_submissions s
            LEFT JOIN scan_analysis a ON a.scan_id = s.id
            ORDER BY s.created_at DESC
        """).fetchall()

        # 生成 CSV
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Scan ID", "Date", "Company", "Contact", "Suburb",
                         "Industry", "Employees", "Sales Status", "Status", "Lead Fit Score", "Lead Fit Band"])
        for r in rows:
            scores = json.loads(r["deterministic_scores_json"]) if r["deterministic_scores_json"] else {}
            writer.writerow([
                r["id"][:8], r["created_at"][:10], r["company_name"], r["full_name"],
                r["suburb"], r["industry_group"], r["employee_band"],
                r["sales_status"], r["status"],
                scores.get("lead_fit_score", ""), scores.get("lead_fit_band", ""),
            ])

        return output.getvalue(), 200, {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=scan-submissions.csv"
        }
    finally:
        conn.close()


# ──────────────────────────────────────────────
# 输入验证
# ──────────────────────────────────────────────

def _validate_submission(data: dict) -> list:
    """验证提交数据，返回错误列表"""
    errors = []

    # Step 1
    if not data.get("full_name") or len(data["full_name"].strip()) < 2:
        errors.append("Full name is required (2+ characters)")
    if not data.get("work_email") or "@" not in data["work_email"]:
        errors.append("Valid work email is required")
    if not data.get("company_name") or len(data["company_name"].strip()) < 2:
        errors.append("Company name is required (2+ characters)")
    if not data.get("suburb"):
        errors.append("Suburb is required")
    if not data.get("postcode") or not re.match(r"^\d{4}$", str(data["postcode"])):
        errors.append("Valid 4-digit Australian postcode is required")
    if data.get("role") not in ["Owner", "Director", "Partner", "General Manager", "Operations", "IT", "Employee", "Other"]:
        errors.append("Role is required")
    if data.get("decision_authority") not in ["Final decision", "Recommend", "Researching only"]:
        errors.append("Decision authority is required")
    if data.get("employee_band") not in EMPLOYEE_BANDS:
        errors.append("Employee count is required")

    # Step 2
    if data.get("industry_group") not in ["A", "B", "C"]:
        errors.append("Industry group selection is required")

    # Step 4
    pain = data.get("main_pain_process", "")
    if pain and len(pain.strip()) < 20:
        errors.append("Please describe your main pain process in at least 20 characters")

    success = data.get("success_looks_like", "")
    if success and len(success.strip()) < 20:
        errors.append("Please describe what success looks like in at least 20 characters")

    # Step 6: Consents
    if not data.get("consent_report"):
        errors.append("You must agree to the report generation terms")
    if not data.get("consent_no_sensitive"):
        errors.append("You must confirm no sensitive data is submitted")
    if not data.get("consent_privacy"):
        errors.append("You must acknowledge the Privacy Notice")
    if not data.get("consent_email_delivery"):
        errors.append("You must agree to receive the report by email")

    return errors


def _clean_submission(data: dict) -> dict:
    """清洗提交数据，返回安全副本"""
    clean = {}
    for key in [
        "full_name", "work_email", "mobile_number", "company_name", "company_website",
        "suburb", "postcode", "role", "decision_authority", "employee_band",
        "industry_group", "sub_industry", "years_operating", "business_model", "primary_goal",
        "systems_integration", "re_entry_frequency",
        "main_pain_process", "pain_frequency", "people_involved", "weekly_hours",
        "success_looks_like", "top_workflow_priority",
        "process_documented", "process_owner_exists", "pilot_willingness", "automation_level",
        "data_sensitivity", "desired_start_time", "indicative_budget", "onsite_assessment_interest",
        "preferred_contact_method",
        "source", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    ]:
        clean[key] = sanitize_input(str(data.get(key, "")), 300) if key not in ("main_pain_process", "success_looks_like") else data.get(key, "")

    # JSON 数组字段
    for arr_key in ["tools", "industry_tools", "what_goes_wrong", "industry_workflows"]:
        val = data.get(arr_key, [])
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = []
        if not isinstance(val, list):
            val = []
        clean[arr_key] = [sanitize_input(str(v), 100) for v in val[:20]]  # 最多20项

    # 布尔字段
    for bool_key in ["website_review_consent", "consent_report", "consent_no_sensitive",
                      "consent_privacy", "consent_email_delivery", "marketing_opt_in"]:
        clean[bool_key] = bool(data.get(bool_key))

    return clean


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _log_sensitive_event(event_type: str, detection: SensitiveDetectionResult):
    """记录安全事件（不记录敏感原文）"""
    log.warning(f"[scan] Sensitive content detected: type={event_type} flags={detection.flags}")


def _enqueue_processing(scan_id: str):
    """将 scan 加入处理队列"""
    from app import scheduler
    if scheduler:
        scheduler.add_job(
            "scan:process_submission",
            _process_submission,
            args=[scan_id],
            id=f"scan_{scan_id[:8]}",
            replace_existing=True,
        )
    else:
        log.warning(f"[scan] No scheduler; processing {scan_id} synchronously")
        _process_submission(scan_id)


def _process_submission(scan_id: str):
    """异步处理入口：评分 → AI分析 → 验证 → 渲染 → 邮件"""
    from scan_engine import process_scan
    try:
        process_scan(scan_id)
    except Exception as e:
        log.error(f"[scan] Processing failed for {scan_id}: {e}", exc_info=True)
        conn = _scan_db()
        try:
            now = datetime.datetime.utcnow().isoformat() + "Z"
            conn.execute("UPDATE scan_analysis SET pipeline_stage='FAILED', pipeline_error=? WHERE scan_id=?",
                         (str(e)[:500], scan_id))
            conn.execute("UPDATE scan_submissions SET status='REVIEW_FAILED', updated_at=? WHERE id=?",
                         (now, scan_id))
            conn.commit()
        finally:
            conn.close()


def _send_report_email(scan_id: str, public_token: str = None):
    """发送报告就绪邮件给客户。

    public_token：报告生成流程里刚创建的明文 token（只在这一刻可用，库里只存 hash）。
    若为 None（例如管理员手动重发），则轮换一个新 token 再发——旧链接随之失效，
    避免为"能重发"而把明文 token 落库，从而不削弱原有的哈希存储安全模型。
    """
    conn = _scan_db()
    try:
        sub = conn.execute("SELECT * FROM scan_submissions WHERE id=?", (scan_id,)).fetchone()
        report = conn.execute("SELECT * FROM scan_reports WHERE scan_id=?", (scan_id,)).fetchone()
        if not sub or not report:
            log.error(f"[scan] Cannot send email: submission or report not found for {scan_id[:8]}")
            return

        # 邮件通道未配置：直接跳过，不轮换 token（否则会白白作废客户手上仍有效的链接）
        if not GMAIL_APP_PASSWORD:
            log.info(f"[scan] GMAIL_APP_PASSWORD not set; skipping report email for {scan_id[:8]}")
            return

        if not public_token:
            # 重发场景：轮换 token（旧链接失效），不落库明文
            public_token = generate_public_token()
            now_iso = datetime.datetime.utcnow().isoformat() + "Z"
            expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat() + "Z"
            conn.execute(
                "UPDATE scan_reports SET secure_token_hash=?, expires_at=?, updated_at=? WHERE scan_id=?",
                (hash_token(public_token), expires_at, now_iso, scan_id))
            conn.execute("""
                INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
                VALUES (?, 'TOKEN_ROTATED', 'system', ?, ?)
            """, (scan_id, json.dumps({"reason": "email_resend"}), now_iso))

        # 报告链接：友好的前台路径（/api/scan/report/<token> 仍保留为兼容别名）
        report_url = f"https://snailai.ai/business-ai-scan/report/{public_token}"
        pdf_url = f"https://snailai.ai/api/scan/report/{public_token}/pdf"

        to_email = sub["work_email"]
        company = sub["company_name"]

        subject = "Your Snail AI Business Opportunity Report is ready"

        html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1A1A2E;max-width:600px;margin:0 auto;padding:20px;">

<div style="text-align:center;margin-bottom:24px;">
  <img src="https://snailai.ai/assets/snailai_logo.png" alt="Snail AI" style="width:100px;">
</div>

<h1 style="font-size:22px;font-weight:800;">Your Business Opportunity Report is Ready</h1>

<p>Hi {_esc(sub['full_name'].split()[0] if sub['full_name'] else 'there')},</p>

<p>Thank you for completing the Snail AI Business Opportunity Scan for <strong>{_esc(company)}</strong>.</p>

<p>Your preliminary AI Opportunity Report has been generated. It includes:</p>
<ul>
  <li>Top automation opportunities for your business</li>
  <li>Risk assessment and human approval requirements</li>
  <li>A recommended first pilot scope</li>
</ul>

<div style="text-align:center;margin:24px 0;">
  <a href="{report_url}" style="display:inline-block;background:#FF5B1F;color:white;padding:14px 32px;border-radius:100px;font-weight:700;text-decoration:none;font-size:16px;">View Your Report</a>
</div>

<p style="color:#6A6A85;font-size:14px;">This link is unique to you and expires in 30 days. Prefer a copy? <a href="{pdf_url}" style="color:#FF5B1F;">Download the PDF</a>.</p>

<p style="color:#6A6A85;font-size:14px;">If you would like to talk it through, you can request a short 10-minute call directly from the report page.</p>

<p style="color:#6A6A85;font-size:14px;">If you did not request this report, you can safely ignore this email.</p>

<hr style="border:none;border-top:1px solid rgba(26,26,46,0.08);margin:24px 0;">

<p style="font-size:14px;">We don't begin with software. We begin by visiting your business, meeting your people, and seeing how the work actually gets done.</p>

<p style="font-size:13px;color:#6A6A85;">
Snail AI<br>
Suite 404, 53 Walker Street, North Sydney NSW 2060<br>
robin@snailai.ai · 0417 993 551
</p>

<p style="font-size:12px;color:#6A6A85;">This is a service email related to your Business Opportunity Scan. Marketing emails require separate consent.</p>

</body></html>"""

        _send_smtp(to_email, subject, html_body)

        # 更新状态
        now = datetime.datetime.utcnow().isoformat() + "Z"
        conn.execute("UPDATE scan_submissions SET status='EMAIL_SENT', updated_at=? WHERE id=?", (now, scan_id))
        conn.execute("UPDATE scan_reports SET emailed_at=? WHERE scan_id=?", (now, scan_id))
        conn.execute("""
            INSERT INTO scan_activities (scan_id, event_type, actor, safe_metadata, created_at)
            VALUES (?, 'EMAIL_SENT', 'system', ?, ?)
        """, (scan_id, json.dumps({"to_prefix": to_email[:3] + "***"}), now))
        conn.commit()

        log.info(f"[scan] Report email sent to {to_email[:3]}*** for {scan_id[:8]}")

    except Exception as e:
        log.error(f"[scan] Failed to send report email for {scan_id}: {e}")
    finally:
        conn.close()


def _send_smtp(to_addr: str, subject: str, html_body: str):
    """通过 Gmail SMTP 发送邮件"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Snail AI <scan@snailai.ai>"
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as srv:
        srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        srv.sendmail(msg["From"], [to_addr], msg.as_string())


def _esc(text: str) -> str:
    """HTML 转义"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;") if text else ""


def _notify_robin_call_request(scan_id, company, email, data):
    """通知 Robin 有电话申请"""
    _send_wechat_notification(
        f"📞 New Call Request\nCompany: {company}\nScan: {scan_id[:8]}"
    )


def _notify_robin_onsite_application(scan_id, company, employees, suburb):
    """通知 Robin 有现场评估申请"""
    _send_wechat_notification(
        f"🏠 On-site Assessment Application\nCompany: {company}\nEmployees: {employees}\nSuburb: {suburb}\nScan: {scan_id[:8]}"
    )


def _notify_robin_high_fit(scan_id, company, industry, employees, lead_fit_score, pain, budget, timing, onsite_interest):
    """通知 Robin High-Fit 客户"""
    _send_wechat_notification(
        f"🔥 HIGH FIT (Score: {lead_fit_score})\n"
        f"Company: {company}\n"
        f"Industry: {industry}\n"
        f"Employees: {employees}\n"
        f"Top Pain: {pain[:80]}\n"
        f"Budget: {budget}\n"
        f"Timing: {timing}\n"
        f"On-site Interest: {onsite_interest}\n"
        f"Scan: {scan_id[:8]}"
    )


def _send_wechat_notification(message: str):
    """发送企微通知"""
    if not WECHAT_WEBHOOK_URL:
        log.warning("[scan] WECHAT_WEBHOOK_URL not set; skipping notification")
        return
    try:
        import requests as http
        http.post(WECHAT_WEBHOOK_URL, json={
            "msgtype": "text",
            "text": {"content": message}
        }, timeout=10)
    except Exception as e:
        log.error(f"[scan] WeChat notification failed: {e}")


# ──────────────────────────────────────────────
# 注册路由到 Flask app
# ──────────────────────────────────────────────

def register_scan_routes(app):
    """在 app.py 中调用此函数注册所有 scan 路由"""
    # 公开 API
    app.add_url_rule("/api/scan/submit", "scan_submit", api_scan_submit, methods=["POST"])
    app.add_url_rule("/api/scan/<scan_id>/status", "scan_status", api_scan_status, methods=["GET"])
    app.add_url_rule("/api/scan/report/<public_token>", "scan_report", api_scan_report, methods=["GET"])
    app.add_url_rule("/api/scan/report/<public_token>/pdf", "scan_report_pdf", api_scan_report_pdf, methods=["GET"])
    app.add_url_rule("/api/scan/report/<public_token>/call-request", "scan_call_request", api_scan_call_request, methods=["POST"])
    app.add_url_rule("/api/scan/report/<public_token>/onsite-application", "scan_onsite_application", api_scan_onsite_application, methods=["POST"])

    # 友好报告页（邮件里的链接用这个；/api/scan/report/<token> 保留为兼容别名）
    # 必须比 catch-all `serve()` 更具体：静态段更多，Werkzeug 排序优先，不会被静态托管吃掉。
    app.add_url_rule("/business-ai-scan/report/<public_token>", "scan_report_page",
                     api_scan_report, methods=["GET"])

    # Admin API
    app.add_url_rule("/api/admin/scan/list", "admin_scan_list", api_admin_scan_list, methods=["GET"])
    app.add_url_rule("/api/admin/scan/<scan_id>", "admin_scan_detail", api_admin_scan_detail, methods=["GET"])
    app.add_url_rule("/api/admin/scan/<scan_id>/regenerate", "admin_scan_regenerate", api_admin_scan_regenerate, methods=["POST"])
    app.add_url_rule("/api/admin/scan/<scan_id>/resend", "admin_scan_resend", api_admin_scan_resend, methods=["POST"])
    app.add_url_rule("/api/admin/scan/<scan_id>/revoke", "admin_scan_revoke", api_admin_scan_revoke, methods=["POST"])
    app.add_url_rule("/api/admin/scan/<scan_id>/status", "admin_scan_update_status", api_admin_scan_update_status, methods=["PATCH"])
    app.add_url_rule("/api/admin/scan/<scan_id>", "admin_scan_delete", api_admin_scan_delete, methods=["DELETE"])
    app.add_url_rule("/api/admin/scan/export", "admin_scan_export", api_admin_scan_export, methods=["GET"])
