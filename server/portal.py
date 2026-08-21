# -*- coding: utf-8 -*-
"""
SnailAI Client Portal — Blueprint
==================================
客户中心后端，独立于报价系统（quote-andrew），复用同一 users/sessions 表。

路由前缀：/api/portal/
  客户端：/api/portal/login, logout, me, overview, quotation, agreement, tasks, progress, change-password
  管理端：/api/portal/admin/*

版本：portal-v1.0.0（Phase 1）
"""

import os
import re
import json
import sqlite3
import hashlib
import secrets
import datetime
from pathlib import Path
from functools import wraps

from flask import Blueprint, request, jsonify, g

# ── 路径常量（与 app.py 一致）───────────────────────────────
if os.environ.get("DB_PATH"):
    DB_PATH = Path(os.environ["DB_PATH"])
elif os.path.exists("/data"):
    DB_PATH = Path("/data/snailai.db")
else:
    DB_PATH = Path(Path(__file__).resolve().parent / "snailai.db")

SESSION_TTL_HOURS = 24 * 7

# demo 全景用户名单
_DEMO_RAW = os.environ.get("PORTAL_DEMO_USERS", "demo")
PORTAL_DEMO_USERS = {u.strip().lower() for u in _DEMO_RAW.split(",") if u.strip()}

bp = Blueprint("portal", __name__, url_prefix="/api/portal")


# ═══════════════════════════════════════════════════════════
# 工具函数（复用 app.py 同款逻辑，避免循环 import）
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
    return _get_session(_token_from_req())


def _client_ip():
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _is_demo(username: str) -> bool:
    return username.lower() in PORTAL_DEMO_USERS


def _portal_url():
    """返回 Portal 客户端入口 URL（用于凭据三件套）。"""
    return "https://snailai.ai/portal/"


# ── 限流 ───────────────────────────────────────────────────
import time as _time

_RL_LOGIN_LIMIT = 10
_RL_LOGIN_WINDOW = 60
_RL_QUERY_LIMIT = 60
_RL_QUERY_WINDOW = 60


def _rate_check(key, limit, window):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        now = _time.time()
        cutoff = now - window
        conn.execute("DELETE FROM rate_limits WHERE hit_at < ?", (cutoff,))
        cur = conn.execute("SELECT COUNT(*) AS n FROM rate_limits WHERE rl_key=? AND hit_at >= ?",
                           (key, cutoff))
        cnt = cur.fetchone()[0]
        if cnt >= limit:
            return False
        conn.execute("INSERT INTO rate_limits(rl_key, hit_at) VALUES(?,?)", (key, now))
        conn.commit()
        return True
    finally:
        conn.close()


def _rate_limit_deco(limit, window=60, by_user=True):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            path = request.path
            key = None
            if by_user:
                u = _current_user()
                if u:
                    key = "u:" + u["username"] + ":" + path
            if not key:
                key = "ip:" + _client_ip() + ":" + path
            if not _rate_check(key, limit, window):
                return jsonify(ok=False, error="Too many requests. Please try again later."), 429
            return fn(*a, **k)
        return wrapper
    return deco


# ── 鉴权装饰器 ────────────────────────────────────────────

def _require_customer(f):
    """客户端接口：需登录 + role=customer（含 demo）。"""
    @wraps(f)
    def wrapper(*a, **k):
        user = _current_user()
        if not user:
            return jsonify(ok=False, error="Not authenticated"), 401
        if user["role"] != "customer":
            return jsonify(ok=False, error="Access denied"), 403
        g.user = user
        return f(*a, **k)
    return wrapper


def _require_admin(f):
    """管理端接口：需登录 + role=admin + 非 demo 用户。"""
    @wraps(f)
    def wrapper(*a, **k):
        user = _current_user()
        if not user:
            return jsonify(ok=False, error="Not authenticated"), 401
        if user["role"] != "admin":
            return jsonify(ok=False, error="Access denied"), 403
        if _is_demo(user["username"]):
            return jsonify(ok=False, error="Demo accounts cannot access admin"), 403
        g.user = user
        return f(*a, **k)
    return wrapper


def _org_id_for(user):
    """返回客户的 organisation_id；demo 返回 None（后续跳过隔离）。"""
    if _is_demo(user["username"]):
        return None
    return user.get("organisation_id")


def _visible_project_ids(user):
    """返回客户可见的 project_id 列表。demo 看全部；普通客户按组织隔离。"""
    conn = _db_conn()
    org_id = _org_id_for(user)
    if org_id is None:
        # demo: 全部项目
        rows = conn.execute("SELECT id FROM portal_projects WHERE status='active'").fetchall()
    else:
        rows = conn.execute("SELECT id FROM portal_projects WHERE organisation_id=? AND status='active'",
                            (org_id,)).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def _project_belong_check(project_id, user):
    """普通客户：project 必须属于自己组织，否则 404。demo 放行。"""
    if _is_demo(user["username"]):
        return True
    conn = _db_conn()
    row = conn.execute(
        "SELECT p.id FROM portal_projects p WHERE p.id=? AND p.organisation_id=?",
        (project_id, user.get("organisation_id"))).fetchone()
    conn.close()
    return row is not None


# ═══════════════════════════════════════════════════════════
# 数据库迁移（幂等）
# ═══════════════════════════════════════════════════════════

def init_portal_db():
    """建表 + 加列 + 种子数据。每次服务启动调用，幂等。"""
    conn = _db_conn()
    c = conn.cursor()

    # ── 新建 8 张表 ─────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS portal_organisations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      legal_name TEXT NOT NULL,
      display_name TEXT,
      abn TEXT,
      address TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      primary_contact_name TEXT,
      primary_contact_email TEXT,
      primary_contact_phone TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portal_projects(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      organisation_id INTEGER NOT NULL,
      name TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      current_phase TEXT,
      progress_percent INTEGER DEFAULT 0,
      next_action_text TEXT,
      materials_email TEXT,
      google_drive_url TEXT,
      start_date TEXT,
      target_launch_date TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portal_quotations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      quote_id TEXT,
      title TEXT NOT NULL,
      version TEXT,
      status TEXT NOT NULL DEFAULT 'sent',
      currency TEXT DEFAULT 'AUD',
      total_ex_gst REAL,
      total_gst REAL,
      total_incl_gst REAL,
      monthly_ex_gst REAL,
      monthly_incl_gst REAL,
      show_amount_to_client INTEGER DEFAULT 1,
      items_json TEXT,
      document_url TEXT,
      issued_at TEXT,
      viewed_at TEXT,
      accepted_at TEXT,
      superseded_by_id INTEGER,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portal_tasks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      description TEXT,
      client_action TEXT,
      status TEXT NOT NULL DEFAULT 'action_required',
      priority TEXT DEFAULT 'normal',
      delivery_method TEXT DEFAULT 'none',
      delivery_destination TEXT,
      client_note TEXT,
      due_date TEXT,
      completed_at TEXT,
      sort_order INTEGER DEFAULT 0,
      visible_to_client INTEGER DEFAULT 1,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portal_milestones(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      code TEXT,
      title TEXT NOT NULL,
      client_summary TEXT,
      status TEXT NOT NULL DEFAULT 'not_started',
      weight INTEGER DEFAULT 1,
      phase_progress_percent INTEGER DEFAULT 0,
      client_action_required INTEGER DEFAULT 0,
      target_date TEXT,
      completed_at TEXT,
      sort_order INTEGER DEFAULT 0,
      visible_to_client INTEGER DEFAULT 1,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS portal_activity_logs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      organisation_id INTEGER,
      project_id INTEGER,
      actor_username TEXT,
      event_type TEXT NOT NULL,
      summary TEXT,
      client_visible INTEGER DEFAULT 0,
      metadata TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS portal_password_resets(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      token TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      used INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS portal_agreements(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_id INTEGER NOT NULL,
      agreement_id INTEGER,
      title TEXT NOT NULL,
      version TEXT,
      portal_status TEXT NOT NULL DEFAULT 'preparing',
      document_url TEXT,
      sign_url TEXT,
      signed_by_client_at TEXT,
      countersigned_at TEXT,
      fully_executed_at TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT
    );
    """)

    # ── users 表加列（幂等 ALTER）──────────────────────
    for col_def in [
        ("organisation_id", "INTEGER"),
        ("job_title", "TEXT"),
        ("status", "TEXT DEFAULT 'active'"),
        ("last_login_at", "TEXT"),
    ]:
        col_name = col_def[0]
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def[1]}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    # ── agreements 表加列（幂等 ALTER）──────────────────
    for col_def in [
        ("project_id", "INTEGER"),
        ("portal_status", "TEXT"),
        ("superseded_by_id", "INTEGER"),
        ("doc_hash", "TEXT"),
    ]:
        col_name = col_def[0]
        try:
            c.execute(f"ALTER TABLE agreements ADD COLUMN {col_name} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    conn.commit()

    # ── 种子数据（幂等：按需补灌）───────────────────────

    # 组织：Andrew Li & Co — 若不存在则创建
    org_row = c.execute("SELECT id FROM portal_organisations WHERE legal_name LIKE '%Andrew Li%'").fetchone()
    if not org_row:
        c.execute("""
            INSERT INTO portal_organisations(legal_name, display_name, abn, address, status,
                primary_contact_name, primary_contact_email, primary_contact_phone)
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            "Andrew Li & Co Pty Ltd",
            "Andrew Li & Co",
            "11111416481",
            "Suite 12 / 50 Victoria Road, Drummoyne NSW 2047",
            "active",
            "Dr Andrew Li",
            "qf14@hotmail.com",
            "0412823924",
        ))
        conn.commit()
        org_row = c.execute("SELECT id FROM portal_organisations WHERE legal_name LIKE '%Andrew Li%'").fetchone()

    # andrew 的 organisation_id 关联
    org_row = c.execute("SELECT id FROM portal_organisations WHERE legal_name LIKE '%Andrew Li%'").fetchone()
    if org_row:
        org_id = org_row["id"]
        c.execute("UPDATE users SET organisation_id=? WHERE username='andrew' AND organisation_id IS NULL",
                  (org_id,))
        # demo 用户不关联组织
        conn.commit()

    # 项目：Andrew Clinic Website — 若不存在则创建
    proj_row = c.execute("SELECT id FROM portal_projects WHERE name LIKE '%Andrew Clinic%'").fetchone()
    if not proj_row and org_row:
        c.execute("""
            INSERT INTO portal_projects(organisation_id, name, description, status, current_phase,
                progress_percent, next_action_text, materials_email, google_drive_url)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            org_id,
            "Andrew Clinic Website Project",
            "Skin Cancer Laser Centre — professional website development and digital services",
            "active",
            "Contracting",
            0,
            "Sign the Digital Services Agreement to commence the project",
            "robin@snailai.ai",
            "",
        ))
        conn.commit()

    # 报价：Andrew 确认的真实数据 — 若不存在则灌入
    proj_row = c.execute("SELECT id FROM portal_projects WHERE name LIKE '%Andrew Clinic%'").fetchone()
    q_count = c.execute("SELECT COUNT(*) AS n FROM portal_quotations WHERE project_id=?", (proj_row["id"],)).fetchone()["n"] if proj_row else 1
    if q_count == 0 and proj_row:
        items = [
            {"code": "W1", "name": "Website Strategy & Planning", "price": 850, "payment_schedule": "50/50"},
            {"code": "W2", "name": "UI/UX Design", "price": 1500, "payment_schedule": "50/50"},
            {"code": "W3", "name": "Website Build & Development", "price": 3000, "payment_schedule": "30/40/30"},
            {"code": "W4", "name": "Booking System Integration", "price": 1350, "payment_schedule": "50/50"},
            {"code": "W5", "name": "Payment Gateway Integration", "price": 950, "payment_schedule": "50/50"},
            {"code": "W6", "name": "SEO & Google Business Setup", "price": 1650, "payment_schedule": "50/50"},
            {"code": "W7", "name": "Staff Training & Documentation", "price": 650, "payment_schedule": "50/50"},
            {"code": "W8", "name": "Controlled Deployment & Go-Live", "price": 1000, "payment_schedule": "50/50"},
            {"code": "M1", "name": "Website Care Standard", "price": 290, "payment_schedule": "monthly"},
        ]
        c.execute("""
            INSERT INTO portal_quotations(project_id, quote_id, title, version, status,
                currency, total_ex_gst, total_gst, total_incl_gst,
                monthly_ex_gst, monthly_incl_gst,
                show_amount_to_client, items_json, issued_at, accepted_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            proj_row["id"],
            "SCLC-QUOTE-2026-001",
            "Website Development Quotation",
            "Rev 1",
            "accepted",
            "AUD",
            10950.0,
            1095.0,
            12045.0,
            290.0,
            319.0,
            1,
            json.dumps(items),
            "2026-08-18",
            "2026-08-20",
        ))
        conn.commit()

    # 任务：17 项真实任务 — 若不存在则灌入
    t_count = c.execute("SELECT COUNT(*) AS n FROM portal_tasks WHERE project_id=?", (proj_row["id"],)).fetchone()["n"] if proj_row else 1
    if t_count == 0 and proj_row:
        tasks = [
            ("Create your Render account (website hosting)", "Register a free account at render.com for website hosting. We will guide you through the setup.", "Sign up at render.com and share the account email with us", "high", "none", None, 1),
            ("Create your GitHub account (website code repository)", "Register a free account at github.com for the website source code repository.", "Sign up at github.com and share your username with us", "high", "none", None, 2),
            ("Confirm ownership of domain www.skincancerlasercentre.com.au", "Domain renewal is approx. A$20–40/year, paid directly by you. We need confirmation that you own or can access this domain.", "Verify domain registrar access and confirm ownership", "high", "none", None, 3),
            ("Prepare a Google account for Search Console, GA4 and Google Business Profile", "A Google account is needed for SEO tools: Search Console, Google Analytics 4, and Google Business Profile.", "Create or designate a Google account and share the email address", "normal", "none", None, 4),
            ("Select and sign up with a booking provider (e.g. AutoMed / HotDoc) and provide test access", "Choose your preferred online booking system. We will integrate it into your website.", "Research options, sign up, and provide us with test-mode credentials", "high", "email", None, 5),
            ("Select and sign up with a payment provider (e.g. Tyro / Stripe) and provide test-mode access", "Choose your preferred payment gateway for online payments. We will integrate it into your website.", "Research options, sign up, and provide us with test-mode credentials", "high", "email", None, 6),
            ("Confirm your MedicalDirector Helix contract status", "We only handle the website-side integration with Helix. Please confirm whether Helix is active and any API access details.", "Confirm Helix contract status and share any API documentation", "normal", "none", None, 7),
            ("Provide the clinic logo and brand assets", "We need your official clinic logo (high-resolution) and any brand guidelines (colours, fonts, style).", "Send your logo files and any brand guidelines", "high", "email", None, 8),
            ("Provide your licensed/purchased images", "Any stock photos or images you have purchased/licensed for the website.", "Upload images to the shared Google Drive folder", "normal", "google_drive", None, 9),
            ("Confirm the final page list (up to 38 public pages)", "Review and confirm the complete list of website pages to be built.", "Review the proposed page list and confirm or suggest changes", "normal", "email", None, 10),
            ("Provide clinical facts — treatments, fees, doctor qualifications — and give final written approval", "All clinical content (treatment descriptions, pricing, doctor bios) must be provided and approved by you. Advertising rules: no 'guaranteed cure' style claims.", "Draft and approve all clinical content for the website", "high", "email", None, 11),
            ("Confirm the main contact phone and email for the website", "The primary phone number and email address to display on the website.", "Provide the preferred contact details", "normal", "email", None, 12),
            ("Provide or approve legal texts: privacy policy, website terms, disclaimer", "Legal texts required for the website. You can provide your own or approve our drafts.", "Review and approve privacy policy, terms, and disclaimer texts", "normal", "email", None, 13),
            ("Nominate one authorised decision-maker and a single feedback channel", "One person will be the key contact for project decisions. All feedback should go through one channel.", "Nominate the decision-maker and preferred communication channel", "high", "none", None, 14),
            ("Approve the design direction (one presentation + up to two revision rounds)", "We will present the design direction. You get one presentation and up to two rounds of revisions.", "Review the design presentation and provide feedback", "normal", "none", None, 15),
            ("Review and approve the staging preview site before launch", "Before going live, you will review the complete website on a staging URL and give formal approval.", "Test the staging site and provide your approval", "normal", "none", None, 16),
            ("Arrange up to two staff for the 90-minute administrator training session", "We will train your staff on how to manage the website content and booking system.", "Nominate staff members and schedule the training session", "low", "none", None, 17),
        ]
        for t in tasks:
            c.execute("""
                INSERT INTO portal_tasks(project_id, title, description, client_action,
                    priority, delivery_method, delivery_destination, sort_order)
                VALUES(?,?,?,?,?,?,?,?)
            """, (proj_row["id"], t[0], t[1], t[2], t[3], t[4], t[5], t[6]))
        conn.commit()

    # 里程碑 — 若不存在则灌入
    ms_count = c.execute("SELECT COUNT(*) AS n FROM portal_milestones WHERE project_id=?", (proj_row["id"],)).fetchone()["n"] if proj_row else 1
    if ms_count == 0 and proj_row:
        milestones = [
            ("contracting", "Contracting", "Quotation confirmed, agreement awaiting signature",
             "in_progress", 1, 0, 0, None, 1),
            ("w1", "W1: Planning & Strategy", "Discovery, planning and project setup",
             "not_started", 1, 0, 0, None, 0),
            ("w2", "W2: UI/UX Design", "Design direction, wireframes and visual design",
             "not_started", 1, 0, 0, None, 0),
            ("w3", "W3: Build & Development", "Core website development and content integration",
             "not_started", 2, 0, 0, None, 0),
            ("w4", "W4: Booking Integration", "Online booking system integration",
             "not_started", 1, 0, 0, None, 0),
            ("w5", "W5: Payment Integration", "Payment gateway setup and testing",
             "not_started", 1, 0, 0, None, 0),
            ("w6", "W6: SEO & Online Presence", "Search engine optimisation and Google Business setup",
             "not_started", 1, 0, 0, None, 0),
            ("w7", "W7: Training & Handover", "Staff training and documentation",
             "not_started", 1, 0, 0, None, 0),
            ("w8", "W8: Controlled Deployment", "Staging review, go-live and post-launch check",
             "not_started", 1, 0, 0, None, 0),
            ("m1", "M1: Website Care", "Ongoing maintenance, updates and support",
             "not_started", 0, 0, 0, None, 0),
        ]
        for m in milestones:
            c.execute("""
                INSERT INTO portal_milestones(project_id, code, title, client_summary,
                    status, weight, phase_progress_percent, client_action_required,
                    target_date, visible_to_client)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (proj_row["id"], m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8]))
        conn.commit()

    # 活动日志：2 条初始 — 若不存在则灌入
    act_count = c.execute("SELECT COUNT(*) AS n FROM portal_activity_logs WHERE project_id=?", (proj_row["id"],)).fetchone()["n"] if proj_row else 1
    if act_count == 0 and org_row and proj_row:
        c.execute("""
            INSERT INTO portal_activity_logs(organisation_id, project_id, actor_username,
                event_type, summary, client_visible)
            VALUES(?,?,?,?,?,?)
        """, (org_row["id"], proj_row["id"], "system", "quotation_accepted",
              "Quotation SCLC-QUOTE-2026-001 accepted", 1))
        c.execute("""
            INSERT INTO portal_activity_logs(organisation_id, project_id, actor_username,
                event_type, summary, client_visible)
            VALUES(?,?,?,?,?,?)
        """, (org_row["id"], proj_row["id"], "system", "project_created",
              "Project created — Andrew Clinic Website", 1))

        conn.commit()

    # ── Andrew 合同框架（preparing 态）— 独立检查 ──────────
    if proj_row:
        agr_count = c.execute("SELECT COUNT(*) FROM portal_agreements WHERE project_id=?", (proj_row["id"],)).fetchone()[0]
        if agr_count == 0:
            c.execute("""
                INSERT INTO portal_agreements(project_id, title, version, portal_status)
                VALUES(?,?,?,?)
            """, (proj_row["id"], "Digital Services Agreement", "Rev 10", "preparing"))
            conn.commit()

    # ── andrew 密码重置（幂等：仅当 hash 仍为 andrew123 时重置为 success888）────
    andrew_row = c.execute("SELECT password_hash, salt FROM users WHERE username='andrew'").fetchone()
    if andrew_row:
        # 检查当前密码是否是 andrew123
        if andrew_row["password_hash"] == _hash_pw("andrew123", andrew_row["salt"]):
            new_salt = secrets.token_hex(16)
            new_hash = _hash_pw("success888", new_salt)
            c.execute("UPDATE users SET password_hash=?, salt=? WHERE username='andrew'",
                      (new_hash, new_salt))
            conn.commit()

    # ── demo 用户：确保 organisation_id 为 NULL ────────
    c.execute("UPDATE users SET organisation_id=NULL WHERE username='demo'")
    conn.commit()

    # ── 同步 app.py 的 andrew 初始密码常量 ─────────────
    # （注意：这里不能直接改 app.py 的源码，但种子数据层面已确保 andrew 密码正确）

    conn.close()


# ═══════════════════════════════════════════════════════════
# 客户端 API
# ═══════════════════════════════════════════════════════════

@bp.route("/login", methods=["POST"])
@_rate_limit_deco(_RL_LOGIN_LIMIT, _RL_LOGIN_WINDOW, by_user=False)
def portal_login():
    """Portal 独立登录端点：复用 _auth_user 但不检查 quote_confirmations。"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify(ok=False, error="Username and password are required"), 400

    # 验证账号密码（复用同一 users 表）
    conn = _db_conn()
    row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE",
                       (username,)).fetchone()
    conn.close()
    if not row:
        return jsonify(ok=False, error="Invalid credentials"), 401

    h = _hash_pw(password, row["salt"])
    if h != row["password_hash"]:
        return jsonify(ok=False, error="Invalid credentials"), 401

    user = dict(row)

    # 只允许 customer 和 admin 登录 Portal
    if user["role"] not in ("customer", "admin"):
        return jsonify(ok=False, error="This account type cannot access the portal"), 403

    # suspended 用户拒绝
    user_status = user.get("status", "active")
    if user_status == "suspended":
        return jsonify(ok=False, error="Account suspended. Please contact SnailAI."), 403

    # 创建 session（不检查 quote_confirmations，与报价页登录不同）
    token = _create_session(user["username"])

    # 更新 last_login_at
    conn = _db_conn()
    conn.execute("UPDATE users SET last_login_at=? WHERE username=?",
                 (datetime.datetime.utcnow().isoformat(), user["username"]))
    conn.commit()
    conn.close()

    # 记录活动
    _log_activity(user["username"], "login", "Logged in to client portal", client_visible=0)

    return jsonify(ok=True, token=token, username=user["username"],
                   name=user["name"], role=user["role"])


@bp.route("/logout", methods=["POST"])
def portal_logout():
    token = _token_from_req()
    if token:
        conn = _db_conn()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    return jsonify(ok=True)


@bp.route("/me", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
@_require_customer
def portal_me():
    """当前用户信息 + 组织 + 可见项目列表。"""
    user = g.user
    conn = _db_conn()

    # 组织信息
    org = None
    org_id = user.get("organisation_id")
    if org_id:
        org_row = conn.execute("SELECT * FROM portal_organisations WHERE id=?", (org_id,)).fetchone()
        if org_row:
            org = dict(org_row)

    # 可见项目
    project_ids = _visible_project_ids(user)
    projects = []
    for pid in project_ids:
        p = conn.execute("SELECT id, name, status, current_phase, progress_percent, next_action_text FROM portal_projects WHERE id=?", (pid,)).fetchone()
        if p:
            projects.append(dict(p))

    conn.close()

    is_demo = _is_demo(user["username"])

    return jsonify(ok=True, user={
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "is_demo": is_demo,
        "organisation": org,
        "projects": projects,
    })


@bp.route("/change-password", methods=["POST"])
@_rate_limit_deco(5, 60)
@_require_customer
def portal_change_password():
    data = request.get_json(silent=True) or {}
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    confirm_pw = data.get("confirm_password") or ""

    if not current_pw or not new_pw or not confirm_pw:
        return jsonify(ok=False, error="All fields are required"), 400

    if new_pw != confirm_pw:
        return jsonify(ok=False, error="New passwords do not match"), 400

    if len(new_pw) < 8 or not any(c.isalpha() for c in new_pw) or not any(c.isdigit() for c in new_pw):
        return jsonify(ok=False, error="Password must be at least 8 characters with letters and numbers"), 400

    user = g.user
    conn = _db_conn()
    row = conn.execute("SELECT password_hash, salt FROM users WHERE username=?", (user["username"],)).fetchone()

    if _hash_pw(current_pw, row["salt"]) != row["password_hash"]:
        conn.close()
        return jsonify(ok=False, error="Current password is incorrect"), 401

    new_salt = secrets.token_hex(16)
    new_hash = _hash_pw(new_pw, new_salt)
    conn.execute("UPDATE users SET password_hash=?, salt=? WHERE username=?",
                 (new_hash, new_salt, user["username"]))

    # 删除其他 session（保留当前）
    current_token = _token_from_req()
    conn.execute("DELETE FROM sessions WHERE username=? AND token != ?",
                 (user["username"], current_token or ""))
    conn.commit()
    conn.close()

    _log_activity(user["username"], "password_changed", "Password changed", client_visible=0)

    return jsonify(ok=True)


# ── 活动日志辅助 ──────────────────────────────────────────

def _log_activity(actor_username, event_type, summary, project_id=None,
                  organisation_id=None, client_visible=0, metadata=None):
    conn = _db_conn()
    conn.execute("""
        INSERT INTO portal_activity_logs(organisation_id, project_id, actor_username,
            event_type, summary, client_visible, metadata)
        VALUES(?,?,?,?,?,?,?)
    """, (organisation_id, project_id, actor_username, event_type, summary,
          client_visible, json.dumps(metadata) if metadata else None))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════
# Phase 2 — Client-facing APIs
# ══════════════════════════════════════════════════════════════

@bp.route("/overview", methods=["GET"])
@_require_customer
def portal_overview():
    """Dashboard overview: project summary + 4-card status + recent activity."""
    user = _current_user()
    pid = request.args.get("project_id", type=int)
    if not pid:
        pids = _visible_project_ids(user)
        if not pids:
            return jsonify(ok=True, overview=None)
        pid = pids[0]
    if not _project_belong_check(pid, user):
        return jsonify(ok=False, error="Project not found"), 404

    conn = _db_conn()

    # Project
    proj = conn.execute("SELECT * FROM portal_projects WHERE id=?", (pid,)).fetchone()

    # Quotation status
    q = conn.execute("SELECT id,quote_id,status,title,version,total_ex_gst,total_gst,total_incl_gst,monthly_ex_gst,monthly_incl_gst,show_amount_to_client,accepted_at FROM portal_quotations WHERE project_id=? AND status!='superseded' ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    q_data = dict(q) if q else None

    # Agreement status (derive from portal_agreements or agreements)
    agr = conn.execute("SELECT id,portal_status FROM portal_agreements WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    agr_status = dict(agr)["portal_status"] if agr else "none"

    # Tasks counts
    t_counts = conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done FROM portal_tasks WHERE project_id=? AND visible_to_client=1", (pid,)).fetchone()
    tasks_total = t_counts["total"] or 0
    tasks_done = t_counts["done"] or 0

    # Current phase / progress
    current_phase = proj["current_phase"] or ""
    progress = proj["progress_percent"] or 0
    next_action = proj["next_action_text"] or ""

    # Recent activity (client_visible)
    acts = conn.execute("SELECT event_type,summary,created_at FROM portal_activity_logs WHERE project_id=? AND client_visible=1 ORDER BY created_at DESC LIMIT 10", (pid,)).fetchall()
    activity = [dict(a) for a in acts]

    conn.close()

    return jsonify(ok=True, overview={
        "project": dict(proj),
        "quotation": q_data,
        "agreement_status": agr_status,
        "tasks": {"total": tasks_total, "completed": tasks_done},
        "progress_percent": progress,
        "current_phase": current_phase,
        "next_action": next_action,
        "milestone_client_action": False,
        "activity": activity,
    })


@bp.route("/quotation", methods=["GET"])
@_require_customer
def portal_quotation():
    """Full quotation detail for the project."""
    user = _current_user()
    pid = request.args.get("project_id", type=int)
    if not pid:
        return jsonify(ok=False, error="project_id required"), 400
    if not _project_belong_check(pid, user):
        return jsonify(ok=False, error="Project not found"), 404

    conn = _db_conn()
    rows = conn.execute("SELECT * FROM portal_quotations WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    quotations = []
    for r in rows:
        q = dict(r)
        if q.get("items_json"):
            try:
                q["items"] = json.loads(q["items_json"])
            except Exception:
                q["items"] = []
        else:
            q["items"] = []
        del q["items_json"]
        quotations.append(q)
    conn.close()
    return jsonify(ok=True, quotations=quotations)


@bp.route("/tasks", methods=["GET"])
@_require_customer
def portal_tasks():
    """List tasks for a project."""
    user = _current_user()
    pid = request.args.get("project_id", type=int)
    if not pid:
        return jsonify(ok=False, error="project_id required"), 400
    if not _project_belong_check(pid, user):
        return jsonify(ok=False, error="Project not found"), 404

    conn = _db_conn()
    proj = conn.execute("SELECT materials_email,google_drive_url FROM portal_projects WHERE id=?", (pid,)).fetchone()
    rows = conn.execute("SELECT * FROM portal_tasks WHERE project_id=? AND visible_to_client=1 ORDER BY sort_order, id", (pid,)).fetchall()
    tasks = [dict(r) for r in rows]
    conn.close()

    return jsonify(ok=True, tasks=tasks,
                   materials_email=proj["materials_email"] if proj else None,
                   google_drive_url=proj["google_drive_url"] if proj else None)


@bp.route("/tasks/<int:task_id>/action", methods=["POST"])
@_require_customer
def portal_task_action(task_id):
    """Client marks a task action: email_sent, drive_placed, note_saved, complete, reopen."""
    user = _current_user()
    conn = _db_conn()

    task = conn.execute("SELECT t.*,p.organisation_id FROM portal_tasks t JOIN portal_projects p ON t.project_id=p.id WHERE t.id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify(ok=False, error="Task not found"), 404

    org_id = _org_id_for(user)
    if not _is_demo(user["username"]) and task["organisation_id"] != org_id:
        conn.close()
        return jsonify(ok=False, error="Access denied"), 404

    data = request.get_json() or {}
    action = data.get("action")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Helper: inline activity log on same connection
    def _inline_log(etype, summary):
        conn.execute("""
            INSERT INTO portal_activity_logs(organisation_id, project_id, actor_username,
                event_type, summary, client_visible, metadata)
            VALUES(?,?,?,?,?,?,?)
        """, (task["organisation_id"], task["project_id"], user["username"],
              etype, summary, 1, None))

    if action == "email_sent":
        conn.execute("UPDATE portal_tasks SET delivery_method='email',updated_at=? WHERE id=?", (now, task_id))
        _inline_log("task_email_sent", f"Marked task '{task['title']}' as sent by email")
    elif action == "drive_placed":
        conn.execute("UPDATE portal_tasks SET delivery_method='google_drive',updated_at=? WHERE id=?", (now, task_id))
        _inline_log("task_drive_placed", f"Marked task '{task['title']}' as placed in Google Drive")
    elif action == "note_saved":
        note = data.get("note", "").strip()[:2000]
        conn.execute("UPDATE portal_tasks SET client_note=?,updated_at=? WHERE id=?", (note, now, task_id))
        _inline_log("task_note", f"Added note to task '{task['title']}'")
    elif action == "complete":
        conn.execute("UPDATE portal_tasks SET status='completed',completed_at=?,updated_at=? WHERE id=?", (now, now, task_id))
        _inline_log("task_completed", f"Completed task '{task['title']}'")
    elif action == "reopen":
        conn.execute("UPDATE portal_tasks SET status='action_required',completed_at=NULL,updated_at=? WHERE id=?", (now, task_id))
        _inline_log("task_reopened", f"Reopened task '{task['title']}'")
    else:
        conn.close()
        return jsonify(ok=False, error="Unknown action"), 400

    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/progress", methods=["GET"])
@_require_customer
def portal_progress():
    """Milestones + progress for a project."""
    user = _current_user()
    pid = request.args.get("project_id", type=int)
    if not pid:
        return jsonify(ok=False, error="project_id required"), 400
    if not _project_belong_check(pid, user):
        return jsonify(ok=False, error="Project not found"), 404

    conn = _db_conn()
    proj = conn.execute("SELECT * FROM portal_projects WHERE id=?", (pid,)).fetchone()
    ms = conn.execute("SELECT id,code,title,client_summary,status,phase_progress_percent,client_action_required,target_date,completed_at,visible_to_client,sort_order FROM portal_milestones WHERE project_id=? ORDER BY sort_order", (pid,)).fetchall()
    milestones = [dict(m) for m in ms]
    conn.close()

    return jsonify(ok=True, progress_percent=proj["progress_percent"] or 0,
                   current_phase=proj["current_phase"] or "",
                   next_action=proj["next_action_text"] or "",
                   milestones=milestones)


# ══════════════════════════════════════════════════════════════
# Phase 3 — Agreement / E-sign integration
# ══════════════════════════════════════════════════════════════

@bp.route("/agreement", methods=["GET"])
@_require_customer
def portal_agreement():
    """Agreement status for the client."""
    user = _current_user()
    pid = request.args.get("project_id", type=int)
    if not pid:
        pids = _visible_project_ids(user)
        pid = pids[0] if pids else None
    if not pid or not _project_belong_check(pid, user):
        return jsonify(ok=False, error="Project not found"), 404

    conn = _db_conn()
    agr = conn.execute("SELECT * FROM portal_agreements WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    conn.close()

    if not agr:
        return jsonify(ok=True, agreement=None, status="none", preview_only=False)

    agr_data = dict(agr)
    is_demo = _is_demo(user["username"])

    # Demo: no sign URL, preview only
    if is_demo and agr_data.get("sign_url"):
        agr_data["sign_url"] = None
        agr_data["preview_only"] = True
    else:
        agr_data["preview_only"] = False

    return jsonify(ok=True, agreement=agr_data, status=agr_data["portal_status"],
                   preview_only=agr_data.get("preview_only", False))


# ══════════════════════════════════════════════════════════════
# Phase 4 — Admin APIs (role=admin only)
# ══════════════════════════════════════════════════════════════

@bp.route("/admin/overview", methods=["GET"])
@_require_admin
def admin_overview():
    """Admin dashboard overview."""
    conn = _db_conn()
    orgs = conn.execute("SELECT COUNT(*) as c FROM portal_organisations WHERE status='active'").fetchone()["c"]
    projs = conn.execute("SELECT COUNT(*) as c FROM portal_projects WHERE status='active'").fetchone()["c"]
    agrs = conn.execute("SELECT COUNT(*) as c FROM portal_agreements WHERE portal_status IN ('ready_to_sign','signed_by_client')").fetchone()["c"]
    tasks_pending = conn.execute("SELECT COUNT(*) as c FROM portal_tasks WHERE status='action_required' AND visible_to_client=1").fetchone()["c"]
    # Recent activity
    acts = conn.execute("SELECT a.*,o.display_name FROM portal_activity_logs a LEFT JOIN portal_organisations o ON a.organisation_id=o.id ORDER BY a.created_at DESC LIMIT 15").fetchall()
    activity = []
    for a in acts:
        d = dict(a)
        d["org_name"] = d.pop("display_name", None)
        activity.append(d)
    conn.close()
    return jsonify(ok=True, stats={"active_clients": orgs, "active_projects": projs,
                                    "pending_agreements": agrs, "pending_tasks": tasks_pending},
                   activity=activity)


@bp.route("/admin/clients", methods=["GET"])
@_require_admin
def admin_clients():
    """List all client organisations."""
    conn = _db_conn()
    rows = conn.execute("""
        SELECT o.*, u.username, u.name as user_name, u.status as user_status, u.last_login_at,
          (SELECT COUNT(*) FROM portal_projects WHERE organisation_id=o.id) as project_count
        FROM portal_organisations o
        LEFT JOIN users u ON u.organisation_id=o.id AND u.role='customer'
        ORDER BY o.created_at DESC
    """).fetchall()
    clients = [dict(r) for r in rows]
    conn.close()
    return jsonify(ok=True, clients=clients)


@bp.route("/admin/clients", methods=["POST"])
@_require_admin
def admin_create_client():
    """Create a new client: organisation + user account. Returns credentials triple."""
    data = request.get_json() or {}
    legal_name = data.get("legal_name", "").strip()
    display_name = data.get("display_name", "").strip()
    contact_name = data.get("contact_name", "").strip()
    contact_email = data.get("contact_email", "").strip()
    contact_phone = data.get("contact_phone", "").strip()
    abn = data.get("abn", "").strip()
    address = data.get("address", "").strip()

    if not legal_name:
        return jsonify(ok=False, error="Company name is required"), 400

    conn = _db_conn()

    # Create organisation
    cur = conn.execute("INSERT INTO portal_organisations(legal_name,display_name,abn,address,primary_contact_name,primary_contact_email,primary_contact_phone) VALUES(?,?,?,?,?,?,?)",
                       (legal_name, display_name or legal_name, abn or None, address or None,
                        contact_name or None, contact_email or None, contact_phone or None))
    org_id = cur.lastrowid

    # Generate username from legal_name
    base_username = re.sub(r'[^a-z0-9]', '', legal_name.lower())[:12]
    if not base_username:
        base_username = "client"
    username = base_username
    n = 1
    while conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        username = base_username + str(n)
        n += 1

    # Generate initial password
    init_pw = secrets.token_urlsafe(8)
    salt = secrets.token_hex(16)
    pw_hash = _hash_pw(init_pw, salt)

    conn.execute("INSERT INTO users(username,name,role,password_hash,salt,organisation_id,status,must_change_pw) VALUES(?,?,?,?,?,?,?,?)",
                 (username, contact_name or legal_name, "customer", pw_hash, salt, org_id, "active", 0))

    conn.commit()
    conn.close()

    portal_url = _portal_url()
    return jsonify(ok=True, credentials={
        "portal_url": portal_url,
        "username": username,
        "initial_password": init_pw
    })


@bp.route("/admin/clients/<int:org_id>", methods=["GET"])
@_require_admin
def admin_client_detail(org_id):
    """Get client org detail + user info + projects."""
    conn = _db_conn()
    org = conn.execute("SELECT * FROM portal_organisations WHERE id=?", (org_id,)).fetchone()
    if not org:
        conn.close()
        return jsonify(ok=False, error="Not found"), 404
    user = conn.execute("SELECT id,username,name,email,role,status,last_login_at,organisation_id FROM users WHERE organisation_id=? AND role='customer'", (org_id,)).fetchone()
    projects = conn.execute("SELECT * FROM portal_projects WHERE organisation_id=? ORDER BY id", (org_id,)).fetchall()
    conn.close()
    return jsonify(ok=True, organisation=dict(org), user=dict(user) if user else None,
                   projects=[dict(p) for p in projects])


@bp.route("/admin/clients/<int:org_id>/reset-password", methods=["POST"])
@_require_admin
def admin_reset_password(org_id):
    """Reset client password. Returns new credentials triple."""
    conn = _db_conn()
    user = conn.execute("SELECT id,username,name FROM users WHERE organisation_id=? AND role='customer'", (org_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify(ok=False, error="User not found"), 404

    new_pw = secrets.token_urlsafe(8)
    new_salt = secrets.token_hex(16)
    new_hash = _hash_pw(new_pw, new_salt)
    conn.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (new_hash, new_salt, user["id"]))
    conn.commit()
    conn.close()

    return jsonify(ok=True, credentials={
        "portal_url": _portal_url(),
        "username": user["username"],
        "initial_password": new_pw
    })


@bp.route("/admin/clients/<int:org_id>/toggle-status", methods=["POST"])
@_require_admin
def admin_toggle_client_status(org_id):
    """Toggle client user between active and suspended."""
    data = request.get_json() or {}
    new_status = data.get("status")  # 'active' or 'suspended'
    if new_status not in ("active", "suspended"):
        return jsonify(ok=False, error="Invalid status"), 400
    conn = _db_conn()
    conn.execute("UPDATE users SET status=? WHERE organisation_id=? AND role='customer'", (new_status, org_id))
    conn.execute("UPDATE portal_organisations SET status=? WHERE id=?", (new_status, org_id))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/projects/<int:project_id>", methods=["GET"])
@_require_admin
def admin_project_detail(project_id):
    """Get project detail with all related data."""
    conn = _db_conn()
    proj = conn.execute("SELECT p.*,o.legal_name as org_name FROM portal_projects p LEFT JOIN portal_organisations o ON p.organisation_id=o.id WHERE p.id=?", (project_id,)).fetchone()
    if not proj:
        conn.close()
        return jsonify(ok=False, error="Not found"), 404

    quotations = conn.execute("SELECT * FROM portal_quotations WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
    agreements = conn.execute("SELECT * FROM portal_agreements WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
    tasks = conn.execute("SELECT * FROM portal_tasks WHERE project_id=? ORDER BY sort_order, id", (project_id,)).fetchall()
    milestones = conn.execute("SELECT * FROM portal_milestones WHERE project_id=? ORDER BY sort_order", (project_id,)).fetchall()
    conn.close()

    return jsonify(ok=True, project=dict(proj),
                   quotations=[dict(q) for q in quotations],
                   agreements=[dict(a) for a in agreements],
                   tasks=[dict(t) for t in tasks],
                   milestones=[dict(m) for m in milestones])


@bp.route("/admin/projects/<int:project_id>", methods=["PATCH"])
@_require_admin
def admin_update_project(project_id):
    """Update project settings (phase, progress, next_action, materials_email, google_drive_url)."""
    data = request.get_json() or {}
    allowed = ["current_phase", "progress_percent", "next_action_text", "materials_email", "google_drive_url", "status", "target_launch_date"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k}=?")
            vals.append(data[k])
    if not sets:
        return jsonify(ok=False, error="No fields to update"), 400
    vals.append(project_id)
    conn = _db_conn()
    conn.execute(f"UPDATE portal_projects SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/projects/<int:project_id>/tasks", methods=["POST"])
@_require_admin
def admin_create_task(project_id):
    """Create a task in a project."""
    data = request.get_json() or {}
    conn = _db_conn()
    max_sort = conn.execute("SELECT MAX(sort_order) FROM portal_tasks WHERE project_id=?", (project_id,)).fetchone()[0] or 0
    conn.execute("""INSERT INTO portal_tasks(project_id,title,description,client_action,status,priority,delivery_method,delivery_destination,sort_order,visible_to_client)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                 (project_id, data.get("title",""), data.get("description"), data.get("client_action"),
                  data.get("status","action_required"), data.get("priority","normal"),
                  data.get("delivery_method","none"), data.get("delivery_destination"),
                  max_sort + 1, data.get("visible_to_client", 1)))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/tasks/<int:task_id>", methods=["PATCH"])
@_require_admin
def admin_update_task(task_id):
    """Update a task."""
    data = request.get_json() or {}
    allowed = ["title", "description", "client_action", "status", "priority", "delivery_method",
               "delivery_destination", "due_date", "visible_to_client", "sort_order"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k}=?")
            vals.append(data[k])
    if not sets:
        return jsonify(ok=False, error="No fields to update"), 400
    vals.append(task_id)
    conn = _db_conn()
    conn.execute(f"UPDATE portal_tasks SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/tasks/<int:task_id>", methods=["DELETE"])
@_require_admin
def admin_delete_task(task_id):
    """Delete a task."""
    conn = _db_conn()
    conn.execute("DELETE FROM portal_tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/projects/<int:project_id>/milestones", methods=["POST"])
@_require_admin
def admin_create_milestone(project_id):
    """Create a milestone."""
    data = request.get_json() or {}
    conn = _db_conn()
    max_sort = conn.execute("SELECT MAX(sort_order) FROM portal_milestones WHERE project_id=?", (project_id,)).fetchone()[0] or 0
    conn.execute("""INSERT INTO portal_milestones(project_id,code,title,client_summary,status,weight,phase_progress_percent,client_action_required,target_date,visible_to_client,sort_order)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                 (project_id, data.get("code"), data.get("title",""), data.get("client_summary"),
                  data.get("status","not_started"), data.get("weight",1), data.get("phase_progress_percent",0),
                  data.get("client_action_required",0), data.get("target_date"),
                  data.get("visible_to_client",0), max_sort + 1))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/milestones/<int:ms_id>", methods=["PATCH"])
@_require_admin
def admin_update_milestone(ms_id):
    """Update a milestone."""
    data = request.get_json() or {}
    allowed = ["code", "title", "client_summary", "status", "weight", "phase_progress_percent",
               "client_action_required", "target_date", "visible_to_client", "sort_order"]
    sets = []
    vals = []
    for k in allowed:
        if k in data:
            sets.append(f"{k}=?")
            vals.append(data[k])
    if not sets:
        return jsonify(ok=False, error="No fields to update"), 400
    vals.append(ms_id)
    conn = _db_conn()
    conn.execute(f"UPDATE portal_milestones SET {', '.join(sets)}, updated_at=datetime('now') WHERE id=?", vals)
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/agreements/link", methods=["POST"])
@_require_admin
def admin_link_agreement():
    """Link an existing agreement (from sign module) to a portal project."""
    data = request.get_json() or {}
    project_id = data.get("project_id")
    agreement_id = data.get("agreement_id")
    title = data.get("title", "Digital Services Agreement")
    version = data.get("version")
    sign_url = data.get("sign_url")

    if not project_id or not agreement_id:
        return jsonify(ok=False, error="project_id and agreement_id required"), 400

    conn = _db_conn()
    # Update or create portal_agreement
    existing = conn.execute("SELECT id FROM portal_agreements WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if existing:
        conn.execute("UPDATE portal_agreements SET agreement_id=?, title=?, version=?, sign_url=?, portal_status='ready_to_sign', updated_at=datetime('now') WHERE id=?",
                     (agreement_id, title, version, sign_url, existing["id"]))
    else:
        conn.execute("INSERT INTO portal_agreements(project_id,agreement_id,title,version,sign_url,portal_status) VALUES(?,?,?,?,?,?)",
                     (project_id, agreement_id, title, version, sign_url, "ready_to_sign"))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@bp.route("/admin/demo-cleanup", methods=["POST"])
@_require_admin
def admin_demo_cleanup():
    """Clean up demo test traces: reset task statuses, clear demo notes, delete demo activity."""
    conn = _db_conn()
    demo_users = os.environ.get("PORTAL_DEMO_USERS", "demo").lower().split(",")

    # Reset tasks touched by demo
    for u in demo_users:
        u = u.strip()
        # Get demo's org projects
        demo_user = conn.execute("SELECT organisation_id FROM users WHERE username=?", (u,)).fetchone()
        if not demo_user or not demo_user["organisation_id"]:
            continue
        # Reset tasks status back to action_required where demo completed them
        conn.execute("""UPDATE portal_tasks SET status='action_required', completed_at=NULL, delivery_method='none', client_note=NULL
                        WHERE project_id IN (SELECT id FROM portal_projects WHERE organisation_id=?)
                        AND status='completed'""", (demo_user["organisation_id"],))
        # Delete demo activity logs
        conn.execute("DELETE FROM portal_activity_logs WHERE actor_username=?", (u,))

    conn.commit()
    conn.close()
    return jsonify(ok=True)
