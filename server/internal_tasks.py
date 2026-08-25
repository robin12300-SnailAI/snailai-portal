# -*- coding: utf-8 -*-
"""
SnailAI Internal Task System — Blueprint (Bilingual)
=====================================================
内部任务管理系统（双语版）：Robin 分配任务给助教，助教提交进度/报告/文件，
后台自动翻译+发双版邮件通知。

- 中文输入 → 自动翻译英文
- 英文输入 → 自动翻译中文
- 邮件中英双版

路由前缀：/api/internal-tasks/

版本：internal-tasks-v1.1.0 (bilingual)
"""

import os
import json
import sqlite3
import hashlib
import secrets
import datetime
import smtplib
import uuid
import re
import urllib.request
import urllib.error
from pathlib import Path
from functools import wraps
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from flask import Blueprint, request, jsonify, g

# ── 路径常量 ──────────────────────────────────────────────
if os.environ.get("DB_PATH"):
    DB_PATH = Path(os.environ["DB_PATH"])
elif os.path.exists("/data"):
    DB_PATH = Path("/data/snailai.db")
else:
    DB_PATH = Path(Path(__file__).resolve().parent / "snailai.db")

# 文件上传目录
if os.path.exists("/data"):
    UPLOAD_DIR = Path("/data/task-files")
else:
    UPLOAD_DIR = Path(Path(__file__).resolve().parent / "task-files")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TTL_HOURS = 24 * 7
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# ── Gmail 配置 ────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "robin12300@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_TO = os.environ.get("ITASK_NOTIFY_TO", "robin@snailai.ai")

# ── 翻译配置：MyMemory 免费主力 + 原文兜底 ─────────────────
# MyMemory: 免费 ~5000字/天，无需 API key

# ── Admin Token ───────────────────────────────────────────
ADMIN_TOKEN = os.environ.get("QUOTE_ADMIN_TOKEN", "admin-dev-token")

bp = Blueprint("internal_tasks", __name__, url_prefix="/api/internal-tasks")


# ═══════════════════════════════════════════════════════════
# 双语翻译
# ═══════════════════════════════════════════════════════════

# 中文字符正则（含 CJK 统一表意文字 + 标点）
_ZH_RE = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')


def _is_chinese(text: str) -> bool:
    """判断文本是否主要是中文"""
    if not text:
        return False
    zh_count = len(_ZH_RE.findall(text))
    return zh_count / max(len(text), 1) > 0.2


def _translate_mymemory(text: str, source_lang: str, target_lang: str) -> str:
    """用 MyMemory 免费翻译 API 翻译，失败返回 None"""
    lang_map = {"zh": "zh-CN", "en": "en"}
    src = lang_map.get(source_lang, source_lang)
    tgt = lang_map.get(target_lang, target_lang)
    lang_pair = f"{src}|{tgt}"

    try:
        import urllib.parse as _up
        url = f"https://api.mymemory.translated.net/get?q={_up.quote(text)}&langpair={lang_pair}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            translated = result["responseData"]["translatedText"]
            # MyMemory 对匹配太高的原文会返回全大写警告，过滤
            if translated.isupper() and len(translated) > 20:
                return None
            return translated
    except Exception as e:
        print(f"[internal-tasks] MyMemory translate error: {e}")
        return None


def _translate(text: str, target_lang: str) -> str:
    """
    两层翻译：MyMemory → 原文兜底
    target_lang: 'en' 或 'zh'
    """
    if not text or not text.strip():
        return text

    # MyMemory — 免费，无需 key，每天 ~5000 字
    source_lang = "zh" if target_lang == "en" else "en"
    result = _translate_mymemory(text, source_lang, target_lang)
    if result:
        return result

    # 兜底：返回原文
    print(f"[internal-tasks] MyMemory translate failed, using original text")
    return text


def _auto_translate(text: str) -> dict:
    """
    自动检测语言，返回双语结果。
    返回 {"en": "...", "zh": "..."}
    """
    if not text or not text.strip():
        return {"en": text or "", "zh": text or ""}

    if _is_chinese(text):
        # 中文输入 → 翻译英文
        en = _translate(text, "en")
        return {"en": en, "zh": text}
    else:
        # 英文输入 → 翻译中文
        zh = _translate(text, "zh")
        return {"en": text, "zh": zh}


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               salt.encode("utf-8"), 100000).hex()


def _create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    conn = _db_conn()
    conn.execute("INSERT INTO sessions(token, username, expires_at) VALUES(?,?,?)",
                 (token, username, expires))
    conn.commit()
    conn.close()
    return token


def _get_session(token):
    if not token:
        return None
    conn = _db_conn()
    s = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not s:
        conn.close()
        return None
    exp = datetime.datetime.fromisoformat(s["expires_at"])
    if exp < datetime.datetime.utcnow():
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
        return None
    u = conn.execute("SELECT * FROM users WHERE username=?",
                     (s["username"],)).fetchone()
    conn.close()
    return dict(u) if u else None


def _token_from_req():
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Bearer "):
        return ah[7:]
    return (request.headers.get("X-Auth-Token")
            or (request.get_json(silent=True) or {}).get("token"))


def _current_user():
    token = _token_from_req()
    return _get_session(token)


def _require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _current_user()
        if not user:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated


def _require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _current_user()
        if not user or user.get("role") != "admin":
            return jsonify({"ok": False, "error": "Admin only"}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def _require_assistant(f):
    """助教或管理员均可访问"""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _current_user()
        if not user:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        if user.get("role") not in ("admin", "assistant"):
            return jsonify({"ok": False, "error": "Assistant/Admin only"}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated


def _task_to_dict(row):
    """把 internal_tasks 行转成可 JSON 化的 dict，含双语字段"""
    d = dict(row)
    # 确保双语字段存在（向后兼容旧数据）
    if "title_zh" not in d:
        d["title_zh"] = d.get("title", "")
    if "title_en" not in d:
        d["title_en"] = d.get("title", "")
    if "description_zh" not in d:
        d["description_zh"] = d.get("description", "")
    if "description_en" not in d:
        d["description_en"] = d.get("description", "")
    # 费用与工时字段（向后兼容旧数据）
    for field in ("estimated_hours", "hourly_rate_aud", "total_budget_aud"):
        if field not in d or d.get(field) is None:
            d[field] = None
    if "requirements" not in d:
        d["requirements"] = ""
    if "requirements_zh" not in d:
        d["requirements_zh"] = d.get("requirements", "")
    if "requirements_en" not in d:
        d["requirements_en"] = d.get("requirements", "")
    return d


def _activity_to_dict(row):
    d = dict(row)
    # 确保双语字段存在
    if "content_zh" not in d:
        d["content_zh"] = d.get("content", "")
    if "content_en" not in d:
        d["content_en"] = d.get("content", "")
    # attachment_paths 是 JSON 数组字符串
    if d.get("attachment_paths"):
        try:
            d["attachments"] = json.loads(d["attachment_paths"])
        except (json.JSONDecodeError, TypeError):
            d["attachments"] = []
    else:
        d["attachments"] = []
    return d


# ═══════════════════════════════════════════════════════════
# 双语邮件模板
# ═══════════════════════════════════════════════════════════

def _send_email(to_addrs, subject, html_body, attachments=None):
    """发送 HTML 邮件，可选附件"""
    if not GMAIL_APP_PASSWORD:
        return False
    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"SnailAI Internal Tasks <{GMAIL_USER}>"
        msg["To"] = ", ".join(to_addrs)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if attachments:
            for filepath in attachments:
                fp = Path(filepath)
                if not fp.exists():
                    continue
                part = MIMEBase("application", "octet-stream")
                with open(fp, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition",
                                f"attachment; filename={fp.name}")
                msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as srv:
            srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            srv.sendmail(GMAIL_USER, to_addrs, msg.as_string())
        return True
    except Exception as e:
        print(f"[internal-tasks] email send error: {e}")
        return False


# ── 状态映射 ──
STATUS_LABELS = {
    "todo": {"en": "To Do", "zh": "待开始"},
    "in_progress": {"en": "In Progress", "zh": "进行中"},
    "in_review": {"en": "In Review", "zh": "待审批"},
    "done": {"en": "Done", "zh": "已完成"},
    "closed": {"en": "Closed", "zh": "已关闭"},
}

PRIORITY_LABELS = {
    "urgent": {"en": "URGENT", "zh": "紧急"},
    "high": {"en": "HIGH", "zh": "高"},
    "normal": {"en": "NORMAL", "zh": "普通"},
    "low": {"en": "LOW", "zh": "低"},
}


def _bilingual_email_section(title_en, title_zh, body_en, body_zh):
    """生成双语邮件区块"""
    return f"""
    <div style="margin-bottom:24px">
      <div style="background:#F8F9FA;border-left:4px solid #FF5B1F;padding:8px 12px;margin-bottom:4px">
        <strong style="color:#1A1A2E">🇬🇧 {title_en}</strong>
      </div>
      <div style="padding:12px;background:#FFFFFF;border:1px solid #E5E7EB">
        {body_en}
      </div>
    </div>
    <div style="margin-bottom:24px">
      <div style="background:#FEF3C7;border-left:4px solid #D4A547;padding:8px 12px;margin-bottom:4px">
        <strong style="color:#1A1A2E">🇨🇳 {title_zh}</strong>
      </div>
      <div style="padding:12px;background:#FFFFFF;border:1px solid #E5E7EB">
        {body_zh}
      </div>
    </div>
    """


def _notify_task_created(task, assigned_to_name, assigned_to_email):
    """通知助教：新任务分配（双版邮件）"""
    title_zh = task.get("title_zh") or task.get("title", "")
    title_en = task.get("title_en") or task.get("title", "")
    desc_zh = task.get("description_zh") or task.get("description", "") or ""
    desc_en = task.get("description_en") or task.get("description", "") or ""
    priority = task.get("priority", "normal")
    deadline = task.get("deadline") or ""
    pri_en = PRIORITY_LABELS.get(priority, {}).get("en", priority.upper())
    pri_zh = PRIORITY_LABELS.get(priority, {}).get("zh", priority)

    est_h = task.get("estimated_hours")
    rate = task.get("hourly_rate_aud")
    budget = task.get("total_budget_aud")
    req_zh = task.get("requirements_zh") or task.get("requirements", "") or ""
    req_en = task.get("requirements_en") or task.get("requirements", "") or ""

    budget_row_en = ""
    budget_row_zh = ""
    if budget is not None or est_h is not None or rate is not None:
        hours_txt = f"{est_h} hrs" if est_h is not None else "-"
        rate_txt = f"AUD ${rate}/hr" if rate is not None else "-"
        budget_txt = f"AUD ${budget}" if budget is not None else "-"
        budget_row_en = f"""<tr><td style="padding:8px;font-weight:bold;width:140px">Budget</td><td style="padding:8px">{budget_txt} &nbsp;|&nbsp; Est. {hours_txt} &nbsp;|&nbsp; {rate_txt}</td></tr>"""
        budget_row_zh = f"""<tr><td style="padding:8px;font-weight:bold;width:140px">费用</td><td style="padding:8px">{budget_txt} &nbsp;|&nbsp; 预计 {hours_txt} &nbsp;|&nbsp; {rate_txt}</td></tr>"""

    subject = f"[SnailAI Task] New Task / 新任务: {title_en}"

    body_en = f"""
      <p>Hi {assigned_to_name},</p>
      <p>Robin has assigned you a new task:</p>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold;width:120px">Title</td><td style="padding:8px">{title_en}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Priority</td><td style="padding:8px">{pri_en}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Deadline</td><td style="padding:8px">{deadline or 'Not set'}</td></tr>
        {budget_row_en}
      </table>
      <div style="margin-top:12px;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
        <p style="margin:0"><strong>Description:</strong></p>
        <p style="margin:8px 0 0;white-space:pre-wrap">{desc_en or 'No description'}</p>
      </div>
      {f'<div style="margin-top:12px;padding:12px;background:#F0F7FF;border-left:4px solid #2E6CF6"><p style="margin:0"><strong>Requirements / 工作要求:</strong></p><p style="margin:8px 0 0;white-space:pre-wrap">{req_en or "No specific requirements"}</p></div>' if req_en else ''}
      <p style="margin-top:16px">Please log in to the task system to view details and start working.</p>
    """

    body_zh = f"""
      <p>{assigned_to_name}，你好！</p>
      <p>Robin 给你分配了一个新任务：</p>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold;width:120px">标题</td><td style="padding:8px">{title_zh}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">优先级</td><td style="padding:8px">{pri_zh}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">截止日期</td><td style="padding:8px">{deadline or '未设定'}</td></tr>
        {budget_row_zh}
      </table>
      <div style="margin-top:12px;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
        <p style="margin:0"><strong>描述：</strong></p>
        <p style="margin:8px 0 0;white-space:pre-wrap">{desc_zh or '无描述'}</p>
      </div>
      {f'<div style="margin-top:12px;padding:12px;background:#F0F7FF;border-left:4px solid #2E6CF6"><p style="margin:0"><strong>工作要求：</strong></p><p style="margin:8px 0 0;white-space:pre-wrap">{req_zh or "无特殊要求"}</p></div>' if req_zh else ''}
      <p style="margin-top:16px">请登录任务系统查看详情并开始工作。</p>
    """

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#FF5B1F;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">New Task Assigned / 新任务分配</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        {_bilingual_email_section("Task Details", "任务详情", body_en, body_zh)}
      </div>
    </div>
    """
    _send_email([assigned_to_email], subject, html)


def _notify_progress_submitted(task, assistant_name, progress_en, progress_zh, attachment_names=None):
    """通知 Robin：助教提交了进度（双版邮件）"""
    title_zh = task.get("title_zh") or task.get("title", "")
    title_en = task.get("title_en") or task.get("title", "")
    att_html = ""
    if attachment_names:
        att_html = f"<p><strong>Attachments / 附件:</strong> {', '.join(attachment_names)}</p>"

    subject = f"[SnailAI Task] Progress Update / 进度更新: {title_en}"

    body_en = f"""
      <p><strong>{assistant_name}</strong> submitted a progress update on:</p>
      <h3 style="color:#FF5B1F">{title_en}</h3>
      <div style="margin:16px 0;padding:12px;background:#FDF6E3;border-left:4px solid #D4A547">
        <p style="margin:0;white-space:pre-wrap">{progress_en or '(no text)'}</p>
      </div>
      {att_html}
      <p style="margin-top:16px;color:#888">Log in to the admin panel to review and provide guidance.</p>
    """

    body_zh = f"""
      <p><strong>{assistant_name}</strong> 提交了任务进度：</p>
      <h3 style="color:#FF5B1F">{title_zh}</h3>
      <div style="margin:16px 0;padding:12px;background:#FDF6E3;border-left:4px solid #D4A547">
        <p style="margin:0;white-space:pre-wrap">{progress_zh or '（无文字）'}</p>
      </div>
      {att_html}
      <p style="margin-top:16px;color:#888">请登录管理后台审阅并给出指导。</p>
    """

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#D4A547;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">Progress Update / 进度更新</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        {_bilingual_email_section("Report", "报告", body_en, body_zh)}
      </div>
    </div>
    """
    _send_email([NOTIFY_TO], subject, html)


def _notify_guidance(task, guidance_en, guidance_zh, assistant_email, assistant_name):
    """通知助教：Robin 给了指导（双版邮件）"""
    title_zh = task.get("title_zh") or task.get("title", "")
    title_en = task.get("title_en") or task.get("title", "")

    subject = f"[SnailAI Task] New Guidance / 新指导: {title_en}"

    body_en = f"""
      <p>Hi {assistant_name},</p>
      <p>Robin has provided guidance on: <strong>{title_en}</strong></p>
      <div style="margin:16px 0;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
        <p style="margin:0;white-space:pre-wrap">{guidance_en}</p>
      </div>
    """

    body_zh = f"""
      <p>{assistant_name}，你好！</p>
      <p>Robin 对任务 <strong>{title_zh}</strong> 给出了指导：</p>
      <div style="margin:16px 0;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
        <p style="margin:0;white-space:pre-wrap">{guidance_zh}</p>
      </div>
    """

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#FF5B1F;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">New Guidance from Robin / Robin 的新指导</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        {_bilingual_email_section("Guidance", "指导", body_en, body_zh)}
      </div>
    </div>
    """
    _send_email([assistant_email], subject, html)


def _notify_status_change(task, new_status, assistant_email, assistant_name):
    """通知助教：任务状态变更（双版邮件）"""
    title_zh = task.get("title_zh") or task.get("title", "")
    title_en = task.get("title_en") or task.get("title", "")
    status_en = STATUS_LABELS.get(new_status, {}).get("en", new_status)
    status_zh = STATUS_LABELS.get(new_status, {}).get("zh", new_status)

    subject = f"[SnailAI Task] Status Update / 状态更新: {title_en} → {status_en}"

    body_en = f"""
      <p>Hi {assistant_name},</p>
      <p>Task <strong>{title_en}</strong> has been updated to: <strong>{status_en}</strong></p>
    """

    body_zh = f"""
      <p>{assistant_name}，你好！</p>
      <p>任务 <strong>{title_zh}</strong> 状态已更新为：<strong>{status_zh}</strong></p>
    """

    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#22C55E;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">Task Status Updated / 任务状态更新</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        {_bilingual_email_section("Status", "状态", body_en, body_zh)}
      </div>
    </div>
    """
    _send_email([assistant_email], subject, html)


# ═══════════════════════════════════════════════════════════
# 数据库迁移（幂等，含双语字段升级）
# ═══════════════════════════════════════════════════════════

def init_internal_tasks_db():
    """建表+双语字段迁移。每次服务启动调用，幂等。"""
    conn = _db_conn()
    c = conn.cursor()

    # 1. 创建基础表（如果不存在）
    c.executescript("""
    CREATE TABLE IF NOT EXISTS itask_tasks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      priority TEXT NOT NULL DEFAULT 'normal',
      deadline TEXT,
      assigned_to TEXT NOT NULL,
      created_by TEXT NOT NULL DEFAULT 'robin',
      status TEXT NOT NULL DEFAULT 'todo',
      progress_percent INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS itask_activities(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id INTEGER NOT NULL,
      author TEXT NOT NULL,
      type TEXT NOT NULL,
      content TEXT,
      attachment_paths TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS itask_files(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id INTEGER NOT NULL,
      activity_id INTEGER,
      filename TEXT NOT NULL,
      filepath TEXT NOT NULL,
      uploaded_by TEXT NOT NULL,
      filesize INTEGER DEFAULT 0,
      uploaded_at TEXT DEFAULT (datetime('now'))
    );
    """)

    # 2. 双语字段迁移（幂等 ALTER）
    _safe_add_column(c, "itask_tasks", "title_zh", "TEXT")
    _safe_add_column(c, "itask_tasks", "title_en", "TEXT")
    _safe_add_column(c, "itask_tasks", "description_zh", "TEXT")
    _safe_add_column(c, "itask_tasks", "description_en", "TEXT")
    _safe_add_column(c, "itask_activities", "content_zh", "TEXT")
    _safe_add_column(c, "itask_activities", "content_en", "TEXT")

    # 2b. 费用与工时字段迁移（幂等 ALTER）
    _safe_add_column(c, "itask_tasks", "estimated_hours", "REAL")
    _safe_add_column(c, "itask_tasks", "hourly_rate_aud", "REAL")
    _safe_add_column(c, "itask_tasks", "total_budget_aud", "REAL")
    _safe_add_column(c, "itask_tasks", "requirements", "TEXT")
    _safe_add_column(c, "itask_tasks", "requirements_zh", "TEXT")
    _safe_add_column(c, "itask_tasks", "requirements_en", "TEXT")

    # 2c. 项目看板字段迁移（幂等 ALTER）
    _safe_add_column(c, "itask_tasks", "project_id", "INTEGER REFERENCES itask_projects(id)")
    _safe_add_column(c, "itask_tasks", "workstream", "TEXT")

    # 2d. 项目表（如果不存在）
    c.execute("""
    CREATE TABLE IF NOT EXISTS itask_projects(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      name_en TEXT,
      target_date TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      description TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    )
    """)

    # 3. 回填旧数据（把旧 title/description/content 复制到双语字段）
    conn.execute("UPDATE itask_tasks SET title_zh=title WHERE title_zh IS NULL AND title IS NOT NULL")
    conn.execute("UPDATE itask_tasks SET title_en=title WHERE title_en IS NULL AND title IS NOT NULL")
    conn.execute("UPDATE itask_tasks SET description_zh=description WHERE description_zh IS NULL AND description IS NOT NULL")
    conn.execute("UPDATE itask_tasks SET description_en=description WHERE description_en IS NULL AND description IS NOT NULL")
    conn.execute("UPDATE itask_activities SET content_zh=content WHERE content_zh IS NULL AND content IS NOT NULL")
    conn.execute("UPDATE itask_activities SET content_en=content WHERE content_en IS NULL AND content IS NOT NULL")

    # 4. users 表 seed
    try:
        robin = c.execute("SELECT id FROM users WHERE username='robin'").fetchone()
        if not robin:
            salt = secrets.token_hex(8)
            c.execute("INSERT INTO users(username,name,role,password_hash,salt,must_change_pw) VALUES(?,?,?,?,?,0)",
                      ("robin", "Robin Luo", "admin", _hash_pw("12345", salt), salt))
            conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def _safe_add_column(cursor, table, column, col_type):
    """安全地添加列（已存在则忽略）"""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # 列已存在


def _to_float(value):
    """把任意输入转成 float，空/非法返回 None"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════
# 助教端 API
# ═══════════════════════════════════════════════════════════

@bp.route("/login", methods=["POST"])
def api_login():
    """助教登录"""
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400

    conn = _db_conn()
    u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()

    if not u:
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401

    if u["role"] not in ("assistant", "admin"):
        return jsonify({"ok": False, "error": "Access denied"}), 403

    if _hash_pw(password, u["salt"]) != u["password_hash"]:
        return jsonify({"ok": False, "error": "Invalid credentials"}), 401

    token = _create_session(username)
    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "username": u["username"],
            "name": u["name"],
            "role": u["role"],
        }
    })


@bp.route("/logout", methods=["POST"])
@_require_auth
def api_logout():
    token = _token_from_req()
    conn = _db_conn()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/me", methods=["GET"])
@_require_assistant
def api_me():
    u = g.user
    return jsonify({
        "ok": True,
        "user": {
            "username": u["username"],
            "name": u["name"],
            "role": u["role"],
        }
    })


@bp.route("/my-tasks", methods=["GET"])
@_require_assistant
def api_my_tasks():
    """助教视角：只看分配给自己的任务"""
    u = g.user
    conn = _db_conn()
    if u["role"] == "admin":
        rows = conn.execute(
            "SELECT * FROM itask_tasks ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, created_at DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM itask_tasks WHERE assigned_to=? ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, created_at DESC",
            (u["username"],)
        ).fetchall()

    tasks = []
    for r in rows:
        d = _task_to_dict(r)
        au = conn.execute("SELECT name FROM users WHERE username=?", (d["assigned_to"],)).fetchone()
        d["assigned_to_name"] = au["name"] if au else d["assigned_to"]
        tasks.append(d)

    conn.close()
    return jsonify({"ok": True, "tasks": tasks})


@bp.route("/task/<int:task_id>", methods=["GET"])
@_require_assistant
def api_task_detail(task_id):
    """任务详情 + 完整时间线"""
    u = g.user
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    task = _task_to_dict(task)
    if u["role"] != "admin" and task["assigned_to"] != u["username"]:
        conn.close()
        return jsonify({"ok": False, "error": "Access denied"}), 403

    au = conn.execute("SELECT name FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    task["assigned_to_name"] = au["name"] if au else task["assigned_to"]

    activities = conn.execute(
        "SELECT * FROM itask_activities WHERE task_id=? ORDER BY created_at ASC",
        (task_id,)
    ).fetchall()
    activity_list = [_activity_to_dict(a) for a in activities]

    files = conn.execute(
        "SELECT * FROM itask_files WHERE task_id=? ORDER BY uploaded_at DESC",
        (task_id,)
    ).fetchall()
    file_list = [dict(f) for f in files]

    conn.close()
    return jsonify({
        "ok": True,
        "task": task,
        "activities": activity_list,
        "files": file_list,
    })


@bp.route("/task/<int:task_id>/submit", methods=["POST"])
@_require_assistant
def api_submit_progress(task_id):
    """助教提交进度报告，后台自动翻译+发双版邮件给 Robin"""
    u = g.user
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    if u["role"] != "admin" and task["assigned_to"] != u["username"]:
        conn.close()
        return jsonify({"ok": False, "error": "Access denied"}), 403

    data = request.get_json(force=True) if request.is_json else {}
    content = (data.get("content") or "").strip()
    progress_percent = data.get("progress_percent")

    if not content:
        conn.close()
        return jsonify({"ok": False, "error": "Content is required"}), 400

    # 自动翻译
    bilingual = _auto_translate(content)
    content_en = bilingual["en"]
    content_zh = bilingual["zh"]

    now = datetime.datetime.utcnow().isoformat()

    # 写活动记录（双语）
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
        (task_id, u["username"], "submit", content, content_en, content_zh, now)
    )
    activity_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 更新进度
    if progress_percent is not None:
        progress_percent = max(0, min(100, int(progress_percent)))
        conn.execute("UPDATE itask_tasks SET progress_percent=?, updated_at=? WHERE id=?",
                     (progress_percent, now, task_id))

    # 自动更新状态
    if task["status"] == "todo":
        conn.execute("UPDATE itask_tasks SET status='in_progress', updated_at=? WHERE id=?",
                     (now, task_id))
    elif task["status"] == "in_review":
        conn.execute("UPDATE itask_tasks SET status='in_progress', updated_at=? WHERE id=?",
                     (now, task_id))

    conn.commit()

    # 重新获取任务
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()

    # 自动发双版邮件给 Robin
    try:
        _notify_progress_submitted(_task_to_dict(task), u["name"], content_en, content_zh)
    except Exception as e:
        print(f"[internal-tasks] notify_progress error: {e}")

    return jsonify({"ok": True, "activity_id": activity_id})


@bp.route("/task/<int:task_id>/upload", methods=["POST"])
@_require_assistant
def api_upload_file(task_id):
    """助教上传文件到任务"""
    u = g.user
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    if u["role"] != "admin" and task["assigned_to"] != u["username"]:
        conn.close()
        return jsonify({"ok": False, "error": "Access denied"}), 403

    if "file" not in request.files:
        conn.close()
        return jsonify({"ok": False, "error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename:
        conn.close()
        return jsonify({"ok": False, "error": "Empty filename"}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        conn.close()
        return jsonify({"ok": False, "error": f"File too large (max {MAX_FILE_SIZE//1024//1024}MB)"}), 400

    task_dir = UPLOAD_DIR / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = task_dir / safe_name
    file.save(str(filepath))

    now = datetime.datetime.utcnow().isoformat()

    upload_msg = f"Uploaded file: {file.filename}"
    bilingual = _auto_translate(upload_msg)

    conn.execute(
        "INSERT INTO itask_files(task_id, filename, filepath, uploaded_by, filesize, uploaded_at) VALUES(?,?,?,?,?,?)",
        (task_id, file.filename, str(filepath), u["username"], size, now)
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, attachment_paths, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (task_id, u["username"], "upload", upload_msg, bilingual["en"], bilingual["zh"], json.dumps([str(filepath)]), now)
    )

    conn.commit()
    conn.close()

    # 发邮件通知 Robin
    task_dict = _task_to_dict(task)
    try:
        _notify_progress_submitted(task_dict, u["name"],
                                   bilingual["en"], bilingual["zh"],
                                   [file.filename])
    except Exception as e:
        print(f"[internal-tasks] notify_upload error: {e}")

    return jsonify({"ok": True, "file_id": file_id, "filename": file.filename})


@bp.route("/file/<int:file_id>/download", methods=["GET"])
@_require_auth
def api_download_file(file_id):
    """下载文件"""
    from flask import send_file
    conn = _db_conn()
    f = conn.execute("SELECT * FROM itask_files WHERE id=?", (file_id,)).fetchone()
    conn.close()
    if not f:
        return jsonify({"ok": False, "error": "File not found"}), 404

    return send_file(f["filepath"], as_attachment=True, download_name=f["filename"])


# ═══════════════════════════════════════════════════════════
# 管理端 API（Robin 专用）
# ═══════════════════════════════════════════════════════════

@bp.route("/admin/tasks", methods=["GET"])
@_require_admin
def api_admin_tasks():
    """管理视角：所有任务"""
    conn = _db_conn()
    status_filter = request.args.get("status")
    assigned_filter = request.args.get("assigned_to")

    query = "SELECT * FROM itask_tasks WHERE 1=1"
    params = []
    if status_filter:
        query += " AND status=?"
        params.append(status_filter)
    if assigned_filter:
        query += " AND assigned_to=?"
        params.append(assigned_filter)
    query += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, created_at DESC"

    rows = conn.execute(query, params).fetchall()
    tasks = []
    for r in rows:
        d = _task_to_dict(r)
        au = conn.execute("SELECT name FROM users WHERE username=?", (d["assigned_to"],)).fetchone()
        d["assigned_to_name"] = au["name"] if au else d["assigned_to"]
        tasks.append(d)

    conn.close()
    return jsonify({"ok": True, "tasks": tasks})


@bp.route("/admin/task/<int:task_id>", methods=["GET"])
@_require_admin
def api_admin_task_detail(task_id):
    """管理视角：任务详情+时间线+文件"""
    return api_task_detail(task_id)


@bp.route("/admin/create-task", methods=["POST"])
@_require_admin
def api_admin_create_task():
    """创建任务并分配给助教（自动翻译为双语）"""
    try:
        data = request.get_json(force=True)
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        priority = data.get("priority") or "normal"
        deadline = data.get("deadline")
        assigned_to = (data.get("assigned_to") or "").strip().lower()
        requirements = (data.get("requirements") or "").strip()

        # 费用与工时
        estimated_hours = _to_float(data.get("estimated_hours"))
        hourly_rate_aud = _to_float(data.get("hourly_rate_aud"))
        total_budget_aud = _to_float(data.get("total_budget_aud"))
        # 未手动填总金额时，自动算 estimated_hours × hourly_rate_aud
        if total_budget_aud is None and estimated_hours is not None and hourly_rate_aud is not None:
            total_budget_aud = round(estimated_hours * hourly_rate_aud, 2)

        if not title:
            return jsonify({"ok": False, "error": "Title is required"}), 400
        if not assigned_to:
            return jsonify({"ok": False, "error": "Assigned to is required"}), 400

        conn = _db_conn()
        au = conn.execute("SELECT * FROM users WHERE username=? AND role IN ('assistant','admin')",
                          (assigned_to,)).fetchone()
        if not au:
            conn.close()
            return jsonify({"ok": False, "error": f"User '{assigned_to}' not found or not an assistant"}), 400

        # 自动翻译 title 和 description
        title_bi = _auto_translate(title)
        desc_bi = _auto_translate(description) if description else {"en": "", "zh": ""}
        req_bi = _auto_translate(requirements) if requirements else {"en": "", "zh": ""}

        now = datetime.datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO itask_tasks(title, description, title_zh, title_en, description_zh, description_en, priority, deadline, assigned_to, created_by, status, created_at, updated_at, estimated_hours, hourly_rate_aud, total_budget_aud, requirements, requirements_zh, requirements_en) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, description, title_bi["zh"], title_bi["en"], desc_bi["zh"], desc_bi["en"],
             priority, deadline, assigned_to, g.user["username"], "todo", now, now,
             estimated_hours, hourly_rate_aud, total_budget_aud, requirements, req_bi["zh"], req_bi["en"])
        )
        task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 活动记录（双语）
        created_msg = f"Task created and assigned to {au['name']}"
        created_bi = _auto_translate(created_msg)
        conn.execute(
            "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
            (task_id, g.user["username"], "created", created_msg, created_bi["en"], created_bi["zh"], now)
        )
        conn.commit()
        conn.close()

        # 双版邮件通知助教
        task_dict = {
            "title": title, "title_zh": title_bi["zh"], "title_en": title_bi["en"],
            "description": description, "description_zh": desc_bi["zh"], "description_en": desc_bi["en"],
            "priority": priority, "deadline": deadline,
            "estimated_hours": estimated_hours, "hourly_rate_aud": hourly_rate_aud,
            "total_budget_aud": total_budget_aud,
            "requirements": requirements, "requirements_zh": req_bi["zh"], "requirements_en": req_bi["en"],
        }
        try:
            _notify_task_created(task_dict, au["name"], au.get("email") or GMAIL_USER)
        except Exception as e:
            print(f"[internal-tasks] notify_task_created error: {e}")

        return jsonify({
            "ok": True,
            "task_id": task_id,
            "title_zh": title_bi["zh"],
            "title_en": title_bi["en"],
            "description_zh": desc_bi["zh"],
            "description_en": desc_bi["en"],
            "estimated_hours": estimated_hours,
            "hourly_rate_aud": hourly_rate_aud,
            "total_budget_aud": total_budget_aud,
            "requirements_zh": req_bi["zh"],
            "requirements_en": req_bi["en"],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/admin/task/<int:task_id>", methods=["PUT"])
@_require_admin
def api_admin_update_task(task_id):
    """更新任务属性（双语翻译）"""
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    data = request.get_json(force=True)
    now = datetime.datetime.utcnow().isoformat()

    updates = []
    params = []

    # 基本字段
    for field in ("priority", "deadline", "assigned_to", "project_id", "workstream"):
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])

    # 双语字段：title 更新时同步翻译
    if "title" in data:
        title_bi = _auto_translate(data["title"])
        updates.extend(["title=?", "title_zh=?", "title_en=?"])
        params.extend([data["title"], title_bi["zh"], title_bi["en"]])

    if "description" in data:
        desc_bi = _auto_translate(data["description"])
        updates.extend(["description=?", "description_zh=?", "description_en=?"])
        params.extend([data["description"], desc_bi["zh"], desc_bi["en"]])

    # 工作要求：更新时同步翻译
    if "requirements" in data:
        req_bi = _auto_translate(data["requirements"] or "")
        updates.extend(["requirements=?", "requirements_zh=?", "requirements_en=?"])
        params.extend([data["requirements"], req_bi["zh"], req_bi["en"]])

    # 费用与工时字段
    for field in ("estimated_hours", "hourly_rate_aud", "total_budget_aud"):
        if field in data:
            val = _to_float(data[field])
            updates.append(f"{field}=?")
            params.append(val)
            # 若清空 total_budget 但 hours×rate 都有，自动重算
            if field in ("estimated_hours", "hourly_rate_aud") and "total_budget_aud" not in data:
                eh = _to_float(data.get("estimated_hours")) if field != "estimated_hours" else val
                hr = _to_float(data.get("hourly_rate_aud")) if field != "hourly_rate_aud" else val
                if eh is not None and hr is not None:
                    updates.append("total_budget_aud=?")
                    params.append(round(eh * hr, 2))

    if updates:
        params.extend([now, task_id])
        conn.execute(f"UPDATE itask_tasks SET {', '.join(updates)}, updated_at=? WHERE id=?", params)

        changed_keys = ("title","description","priority","deadline","assigned_to","requirements",
                        "estimated_hours","hourly_rate_aud","total_budget_aud")
        changes = ", ".join(f"{k}={v}" for k, v in data.items() if k in changed_keys)
        changes_bi = _auto_translate(f"Task updated: {changes}")
        conn.execute(
            "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
            (task_id, g.user["username"], "updated", f"Task updated: {changes}", changes_bi["en"], changes_bi["zh"], now)
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/admin/task/<int:task_id>/guide", methods=["POST"])
@_require_admin
def api_admin_guide(task_id):
    """Robin 给指导/意见（自动翻译为双语）"""
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Content is required"}), 400

    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    # 自动翻译指导内容
    bi = _auto_translate(content)

    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
        (task_id, g.user["username"], "guide", content, bi["en"], bi["zh"], now)
    )

    if task["status"] == "in_review":
        conn.execute("UPDATE itask_tasks SET status='in_progress', updated_at=? WHERE id=?",
                     (now, task_id))

    conn.commit()

    au = conn.execute("SELECT * FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    conn.close()

    # 双版邮件通知助教
    if au:
        try:
            task_dict = _task_to_dict(task)
            _notify_guidance(task_dict, bi["en"], bi["zh"],
                             au.get("email") or GMAIL_USER, au["name"])
        except Exception as e:
            print(f"[internal-tasks] notify_guidance error: {e}")

    return jsonify({"ok": True, "content_zh": bi["zh"], "content_en": bi["en"]})


@bp.route("/admin/task/<int:task_id>/status", methods=["POST"])
@_require_admin
def api_admin_change_status(task_id):
    """变更任务状态"""
    data = request.get_json(force=True)
    new_status = (data.get("status") or "").strip()
    note = (data.get("note") or "").strip()

    valid = ("todo", "in_progress", "in_review", "done", "closed")
    if new_status not in valid:
        return jsonify({"ok": False, "error": f"Invalid status. Must be one of: {valid}"}), 400

    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    now = datetime.datetime.utcnow().isoformat()
    conn.execute("UPDATE itask_tasks SET status=?, updated_at=? WHERE id=?",
                 (new_status, now, task_id))

    if new_status == "done":
        conn.execute("UPDATE itask_tasks SET progress_percent=100, updated_at=? WHERE id=?",
                     (now, task_id))

    status_label = note or f"Status changed to {new_status}"
    bi = _auto_translate(status_label)
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
        (task_id, g.user["username"], "status_change", status_label, bi["en"], bi["zh"], now)
    )
    conn.commit()

    au = conn.execute("SELECT * FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    conn.close()

    if au:
        try:
            _notify_status_change(_task_to_dict(task), new_status,
                                  au.get("email") or GMAIL_USER, au["name"])
        except Exception as e:
            print(f"[internal-tasks] notify_status_change error: {e}")

    return jsonify({"ok": True})


@bp.route("/admin/assistants", methods=["GET"])
@_require_admin
def api_admin_assistants():
    """获取所有助教列表"""
    conn = _db_conn()
    rows = conn.execute("SELECT username, name, role FROM users WHERE role IN ('assistant','admin') ORDER BY role, name").fetchall()
    conn.close()
    return jsonify({"ok": True, "assistants": [dict(r) for r in rows]})


@bp.route("/admin/create-assistant", methods=["POST"])
@_require_admin
def api_admin_create_assistant():
    """创建助教账号"""
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip().lower()
    name = (data.get("name") or "").strip()
    password = data.get("password") or secrets.token_urlsafe(8)

    if not username or not name:
        return jsonify({"ok": False, "error": "Username and name are required"}), 400

    conn = _db_conn()
    existing = conn.execute("SELECT id, role FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        if existing["role"] != "assistant":
            salt = secrets.token_hex(8)
            conn.execute("UPDATE users SET role='assistant', name=?, password_hash=?, salt=?, must_change_pw=0 WHERE username=?",
                         (name, _hash_pw(password, salt), salt, username))
            conn.commit()
            conn.close()
            return jsonify({"ok": True, "username": username, "password": password, "name": name, "action": "upgraded", "previous_role": existing["role"]})
        else:
            salt = secrets.token_hex(8)
            conn.execute("UPDATE users SET name=?, password_hash=?, salt=?, must_change_pw=0 WHERE username=?",
                         (name, _hash_pw(password, salt), salt, username))
            conn.commit()
            conn.close()
            return jsonify({"ok": True, "username": username, "password": password, "name": name, "action": "password_reset"})
    salt = secrets.token_hex(8)
    conn.execute("INSERT INTO users(username,name,role,password_hash,salt,must_change_pw) VALUES(?,?,?,?,?,0)",
                 (username, name, "assistant", _hash_pw(password, salt), salt))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "username": username, "password": password, "name": name, "action": "created"})


@bp.route("/admin/delete-file/<int:file_id>", methods=["DELETE"])
@_require_admin
def api_admin_delete_file(file_id):
    """管理员删除文件"""
    conn = _db_conn()
    f = conn.execute("SELECT * FROM itask_files WHERE id=?", (file_id,)).fetchone()
    if not f:
        conn.close()
        return jsonify({"ok": False, "error": "File not found"}), 404

    filepath = Path(f["filepath"])
    if filepath.exists():
        filepath.unlink()

    conn.execute("DELETE FROM itask_files WHERE id=?", (file_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/admin/stats", methods=["GET"])
@_require_admin
def api_admin_stats():
    """管理面板统计"""
    conn = _db_conn()
    total = conn.execute("SELECT COUNT(*) AS n FROM itask_tasks").fetchone()["n"]
    by_status = {}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM itask_tasks GROUP BY status"):
        by_status[row["status"]] = row["n"]
    by_person = {}
    for row in conn.execute("SELECT assigned_to, COUNT(*) AS n FROM itask_tasks GROUP BY assigned_to"):
        au = conn.execute("SELECT name FROM users WHERE username=?", (row["assigned_to"],)).fetchone()
        by_person[row["assigned_to"]] = {"name": au["name"] if au else row["assigned_to"], "count": row["n"]}
    conn.close()
    return jsonify({"ok": True, "total": total, "by_status": by_status, "by_person": by_person})


# ═══════════════════════════════════════════════════════════
# 项目看板 API（协同看板模块 V1.0）
# ═══════════════════════════════════════════════════════════

@bp.route("/projects", methods=["GET"])
@_require_assistant
def api_list_projects():
    """列出所有项目"""
    conn = _db_conn()
    rows = conn.execute("SELECT * FROM itask_projects ORDER BY id DESC").fetchall()
    projects = []
    for p in rows:
        d = dict(p)
        # 每个项目的任务统计
        stats = conn.execute(
            "SELECT status, COUNT(*) AS n, AVG(progress_percent) AS avg_progress FROM itask_tasks WHERE project_id=? GROUP BY status",
            (d["id"],)
        ).fetchall()
        total = sum(s["n"] for s in stats)
        done = sum(s["n"] for s in stats if s["status"] == "done")
        d["total_tasks"] = total
        d["done_tasks"] = done
        d["progress"] = round(done / total * 100) if total else 0
        projects.append(d)
    conn.close()
    return jsonify({"ok": True, "projects": projects})


@bp.route("/projects", methods=["POST"])
@_require_admin
def api_create_project():
    """创建新项目"""
    data = request.get_json(force=True)
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    name_en = (data.get("name_en") or "").strip()
    target_date = data.get("target_date")
    description = (data.get("description") or "").strip()

    if not code or not name:
        return jsonify({"ok": False, "error": "code and name are required"}), 400

    conn = _db_conn()
    existing = conn.execute("SELECT id FROM itask_projects WHERE code=?", (code,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"ok": False, "error": f"Project code '{code}' already exists"}), 400

    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO itask_projects(code, name, name_en, target_date, status, description, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (code, name, name_en, target_date, "active", description, now, now)
    )
    project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "project_id": project_id})


@bp.route("/projects/<int:project_id>", methods=["GET"])
@_require_assistant
def api_get_project(project_id):
    """获取项目详情 + 按工作线分组的任务"""
    conn = _db_conn()
    proj = conn.execute("SELECT * FROM itask_projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return jsonify({"ok": False, "error": "Project not found"}), 404
    proj = dict(proj)

    rows = conn.execute(
        "SELECT * FROM itask_tasks WHERE project_id=? ORDER BY workstream, id",
        (project_id,)
    ).fetchall()
    tasks = []
    for r in rows:
        d = _task_to_dict(r)
        au = conn.execute("SELECT name FROM users WHERE username=?", (d["assigned_to"],)).fetchone()
        d["assigned_to_name"] = au["name"] if au else d["assigned_to"]
        tasks.append(d)

    # 按 workstream 分组
    workstreams = {}
    for t in tasks:
        ws = t.get("workstream") or "未分类"
        if ws not in workstreams:
            workstreams[ws] = []
        workstreams[ws].append(t)

    # 统计
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "done")
    proj["total_tasks"] = total
    proj["done_tasks"] = done
    proj["progress"] = round(done / total * 100) if total else 0

    conn.close()
    return jsonify({"ok": True, "project": proj, "workstreams": workstreams, "tasks": tasks})


@bp.route("/projects/<int:project_id>/public", methods=["GET"])
def api_get_project_public(project_id):
    """公开只读 API：不需登录，返回项目进度 + 任务清单（用于公开看板）"""
    conn = _db_conn()
    proj = conn.execute("SELECT * FROM itask_projects WHERE id=? AND status='active'", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return jsonify({"ok": False, "error": "Project not found"}), 404
    proj = dict(proj)

    rows = conn.execute(
        "SELECT id, title, description, status, priority, deadline, assigned_to, workstream, progress_percent, created_at FROM itask_tasks WHERE project_id=? ORDER BY workstream, id",
        (project_id,)
    ).fetchall()
    tasks = []
    for r in rows:
        d = dict(r)
        au = conn.execute("SELECT name FROM users WHERE username=?", (d["assigned_to"],)).fetchone()
        d["assigned_to_name"] = au["name"] if au else d["assigned_to"]
        tasks.append(d)

    # 按 workstream 分组
    workstreams = {}
    for t in tasks:
        ws = t.get("workstream") or "未分类"
        if ws not in workstreams:
            workstreams[ws] = []
        workstreams[ws].append(t)

    # 统计
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "done")
    proj["total_tasks"] = total
    proj["done_tasks"] = done
    proj["progress"] = round(done / total * 100) if total else 0

    conn.close()
    return jsonify({"ok": True, "project": proj, "workstreams": workstreams})


@bp.route("/projects/<int:project_id>/tasks/<int:task_id>/status", methods=["POST"])
@_require_assistant
def api_board_update_status(project_id, task_id):
    """看板模式：参与者更新自己负责的任务状态"""
    u = g.user
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=? AND project_id=?", (task_id, project_id)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    data = request.get_json(force=True)
    new_status = (data.get("status") or "").strip()
    progress_percent = data.get("progress_percent")

    valid = ("todo", "in_progress", "in_review", "done", "closed")
    if new_status and new_status not in valid:
        conn.close()
        return jsonify({"ok": False, "error": f"Invalid status"}), 400

    now = datetime.datetime.utcnow().isoformat()
    updates = []
    params = []

    # 权限：admin 可改任何任务，assistant 只能改自己的
    if u["role"] != "admin" and task["assigned_to"] != u["username"]:
        conn.close()
        return jsonify({"ok": False, "error": "You can only update your own tasks"}), 403

    if new_status:
        updates.append("status=?")
        params.append(new_status)
        if new_status == "done":
            updates.append("progress_percent=100")

    if progress_percent is not None and new_status != "done":
        progress_percent = max(0, min(100, int(progress_percent)))
        updates.append("progress_percent=?")
        params.append(progress_percent)

    if updates:
        updates.append("updated_at=?")
        params.append(now)
        params.append(task_id)
        conn.execute(f"UPDATE itask_tasks SET {', '.join(updates)} WHERE id=?", params)

        # 活动记录
        change_desc = f"Status: {new_status}" if new_status else f"Progress: {progress_percent}%"
        bi = _auto_translate(change_desc)
        conn.execute(
            "INSERT INTO itask_activities(task_id, author, type, content, content_en, content_zh, created_at) VALUES(?,?,?,?,?,?,?)",
            (task_id, u["username"], "status_change", change_desc, bi["en"], bi["zh"], now)
        )
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


@bp.route("/projects/<int:project_id>/tasks/<int:task_id>/workstream", methods=["POST"])
@_require_admin
def api_board_set_workstream(project_id, task_id):
    """设置任务所属工作线"""
    data = request.get_json(force=True)
    workstream = (data.get("workstream") or "").strip()
    conn = _db_conn()
    conn.execute("UPDATE itask_tasks SET workstream=? WHERE id=? AND project_id=?",
                 (workstream, task_id, project_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/projects/<int:project_id>", methods=["PUT"])
@_require_admin
def api_update_project(project_id):
    """更新项目信息"""
    data = request.get_json(force=True)
    conn = _db_conn()
    proj = conn.execute("SELECT * FROM itask_projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return jsonify({"ok": False, "error": "Project not found"}), 404

    now = datetime.datetime.utcnow().isoformat()
    updates = []
    params = []
    for field in ("name", "name_en", "target_date", "status", "description"):
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])
    if updates:
        updates.append("updated_at=?")
        params.append(now)
        params.append(project_id)
        conn.execute(f"UPDATE itask_projects SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
    conn.close()
    return jsonify({"ok": True})
