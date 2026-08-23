# -*- coding: utf-8 -*-
"""
SnailAI Internal Task System — Blueprint
==========================================
内部任务管理系统：Robin 分配任务给助教，助教提交进度/报告/文件，
后台自动发邮件通知 Robin。

路由前缀：/api/internal-tasks/
  助教端：login, logout, me, my-tasks, task-detail, submit-progress, upload-file
  管理端：admin/create-task, admin/tasks, admin/task-detail, admin/update-task,
          admin/guide, admin/approve, admin/close, admin/create-assistant,
          admin/assistants, admin/delete-file

版本：internal-tasks-v1.0.0
"""

import os
import json
import sqlite3
import hashlib
import secrets
import datetime
import smtplib
import uuid
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

# ── Admin Token ───────────────────────────────────────────
ADMIN_TOKEN = os.environ.get("QUOTE_ADMIN_TOKEN", "admin-dev-token")

bp = Blueprint("internal_tasks", __name__, url_prefix="/api/internal-tasks")


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
    """把 internal_tasks 行转成可 JSON 化的 dict"""
    d = dict(row)
    return d


def _activity_to_dict(row):
    d = dict(row)
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
# 邮件发送
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


def _notify_task_created(task, assigned_to_name, assigned_to_email):
    """通知助教：新任务分配"""
    subject = f"[SnailAI Task] New Task: {task['title']}"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#FF5B1F;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">New Task Assigned</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        <p>Hi {assigned_to_name},</p>
        <p>Robin has assigned you a new task:</p>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:8px;font-weight:bold;width:120px">Title</td><td style="padding:8px">{task['title']}</td></tr>
          <tr><td style="padding:8px;font-weight:bold">Priority</td><td style="padding:8px">{task.get('priority','normal').upper()}</td></tr>
          <tr><td style="padding:8px;font-weight:bold">Deadline</td><td style="padding:8px">{task.get('deadline') or 'Not set'}</td></tr>
        </table>
        <div style="margin-top:16px;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
          <p style="margin:0"><strong>Description:</strong></p>
          <p style="margin:8px 0 0">{task.get('description') or 'No description'}</p>
        </div>
        <p style="margin-top:20px">Please log in to the task system to view details and start working.</p>
      </div>
    </div>
    """
    _send_email([assigned_to_email], subject, html)


def _notify_progress_submitted(task, assistant_name, progress_text, attachment_names=None):
    """通知 Robin：助教提交了进度"""
    subject = f"[SnailAI Task] Progress Update: {task['title']}"
    att_html = ""
    if attachment_names:
        att_html = f"<p><strong>Attachments:</strong> {', '.join(attachment_names)}</p>"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#D4A547;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">Progress Update</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        <p><strong>{assistant_name}</strong> submitted a progress update on:</p>
        <h3 style="color:#FF5B1F">{task['title']}</h3>
        <div style="margin:16px 0;padding:12px;background:#FDF6E3;border-left:4px solid #D4A547">
          <p style="margin:0;white-space:pre-wrap">{progress_text or '(no text)'}</p>
        </div>
        {att_html}
        <p style="margin-top:16px;color:#888">Log in to the admin panel to review and provide guidance.</p>
      </div>
    </div>
    """
    _send_email([NOTIFY_TO], subject, html)


def _notify_guidance(task, guidance_text, assistant_email, assistant_name):
    """通知助教：Robin 给了指导"""
    subject = f"[SnailAI Task] New Guidance: {task['title']}"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#FF5B1F;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">New Guidance from Robin</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        <p>Hi {assistant_name},</p>
        <p>Robin has provided guidance on: <strong>{task['title']}</strong></p>
        <div style="margin:16px 0;padding:12px;background:#FFF5EE;border-left:4px solid #FF5B1F">
          <p style="margin:0;white-space:pre-wrap">{guidance_text}</p>
        </div>
      </div>
    </div>
    """
    _send_email([assistant_email], subject, html)


def _notify_status_change(task, new_status, assistant_email, assistant_name):
    """通知助教：任务状态变更"""
    subject = f"[SnailAI Task] Status Update: {task['title']} → {new_status}"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;color:#1A1A2E">
      <div style="background:#22C55E;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">Task Status Updated</h2>
      </div>
      <div style="padding:20px;border:1px solid #eee">
        <p>Hi {assistant_name},</p>
        <p>Task <strong>{task['title']}</strong> has been updated to: <strong>{new_status}</strong></p>
      </div>
    </div>
    """
    _send_email([assistant_email], subject, html)


# ═══════════════════════════════════════════════════════════
# 数据库迁移（幂等）
# ═══════════════════════════════════════════════════════════

def init_internal_tasks_db():
    """建表。每次服务启动调用，幂等。"""
    conn = _db_conn()
    c = conn.cursor()

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

    # users 表加 role=assistant 支持（无需 ALTER，role 本身是 TEXT 自由字段）
    # 确保 robin 账号存在（admin 角色）— 如果 users 表还没创建则跳过（由 app.py 主迁移创建）
    try:
        robin = c.execute("SELECT id FROM users WHERE username='robin'").fetchone()
        if not robin:
            salt = secrets.token_hex(8)
            c.execute("INSERT INTO users(username,name,role,password_hash,salt,must_change_pw) VALUES(?,?,?,?,?,0)",
                      ("robin", "Robin Luo", "admin", _hash_pw("12345", salt), salt))
            conn.commit()
    except sqlite3.OperationalError:
        pass  # users 表还不存在，由 app.py 主迁移创建

    conn.commit()
    conn.close()


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

    # 只允许 assistant 和 admin 登录
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
    conn.close()

    tasks = []
    for r in rows:
        d = _task_to_dict(r)
        # 助教名
        conn2 = _db_conn()
        au = conn2.execute("SELECT name FROM users WHERE username=?", (d["assigned_to"],)).fetchone()
        conn2.close()
        d["assigned_to_name"] = au["name"] if au else d["assigned_to"]
        tasks.append(d)

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

    task = dict(task)
    # 权限：助教只能看自己的
    if u["role"] != "admin" and task["assigned_to"] != u["username"]:
        conn.close()
        return jsonify({"ok": False, "error": "Access denied"}), 403

    # 助教名
    au = conn.execute("SELECT name FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    task["assigned_to_name"] = au["name"] if au else task["assigned_to"]

    # 时间线
    activities = conn.execute(
        "SELECT * FROM itask_activities WHERE task_id=? ORDER BY created_at ASC",
        (task_id,)
    ).fetchall()
    activity_list = [_activity_to_dict(a) for a in activities]

    # 文件
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
    """助教提交进度报告（文字+可选文件），后台自动发邮件给 Robin"""
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

    now = datetime.datetime.utcnow().isoformat()

    # 写活动记录
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, created_at) VALUES(?,?,?,?,?)",
        (task_id, u["username"], "submit", content, now)
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
        # 助教再次提交，回到 in_progress
        conn.execute("UPDATE itask_tasks SET status='in_progress', updated_at=? WHERE id=?",
                     (now, task_id))

    conn.commit()

    # 重新获取任务（状态可能变了）
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()

    # 自动发邮件给 Robin（失败不影响接口）
    try:
        _notify_progress_submitted(dict(task), u["name"], content)
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

    # 检查大小
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        conn.close()
        return jsonify({"ok": False, "error": f"File too large (max {MAX_FILE_SIZE//1024//1024}MB)"}), 400

    # 保存文件
    task_dir = UPLOAD_DIR / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    # 防重名：加 UUID 前缀
    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = task_dir / safe_name
    file.save(str(filepath))

    now = datetime.datetime.utcnow().isoformat()

    # 写文件记录
    conn.execute(
        "INSERT INTO itask_files(task_id, filename, filepath, uploaded_by, filesize, uploaded_at) VALUES(?,?,?,?,?,?)",
        (task_id, file.filename, str(filepath), u["username"], size, now)
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 写活动记录（带附件标记）
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, attachment_paths, created_at) VALUES(?,?,?,?,?,?)",
        (task_id, u["username"], "upload", f"Uploaded file: {file.filename}", json.dumps([str(filepath)]), now)
    )

    conn.commit()
    conn.close()

    # 同时发邮件通知 Robin（失败不影响接口）
    task_dict = dict(task)
    try:
        _notify_progress_submitted(task_dict, u["name"],
                                   f"[File Upload] {file.filename} ({size//1024}KB)",
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
    """创建任务并分配给助教"""
    try:
        data = request.get_json(force=True)
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        priority = data.get("priority") or "normal"
        deadline = data.get("deadline")
        assigned_to = (data.get("assigned_to") or "").strip().lower()

        if not title:
            return jsonify({"ok": False, "error": "Title is required"}), 400
        if not assigned_to:
            return jsonify({"ok": False, "error": "Assigned to is required"}), 400

        conn = _db_conn()
        # 验证助教存在
        au = conn.execute("SELECT * FROM users WHERE username=? AND role IN ('assistant','admin')",
                          (assigned_to,)).fetchone()
        if not au:
            conn.close()
            return jsonify({"ok": False, "error": f"User '{assigned_to}' not found or not an assistant"}), 400

        now = datetime.datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO itask_tasks(title, description, priority, deadline, assigned_to, created_by, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title, description, priority, deadline, assigned_to, g.user["username"], "todo", now, now)
        )
        task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 写活动记录
        conn.execute(
            "INSERT INTO itask_activities(task_id, author, type, content, created_at) VALUES(?,?,?,?,?)",
            (task_id, g.user["username"], "created", f"Task created and assigned to {au['name']}", now)
        )
        conn.commit()
        conn.close()

        # 邮件通知助教（失败不影响接口）
        task_dict = {"title": title, "description": description, "priority": priority, "deadline": deadline}
        try:
            _notify_task_created(task_dict, au["name"], au.get("email") or GMAIL_USER)
        except Exception as e:
            print(f"[internal-tasks] notify_task_created error: {e}")

        return jsonify({"ok": True, "task_id": task_id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/admin/task/<int:task_id>", methods=["PUT"])
@_require_admin
def api_admin_update_task(task_id):
    """更新任务属性"""
    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    data = request.get_json(force=True)
    now = datetime.datetime.utcnow().isoformat()

    updates = []
    params = []
    for field in ("title", "description", "priority", "deadline", "assigned_to"):
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])

    if updates:
        params.append(now)
        params.append(task_id)
        conn.execute(f"UPDATE itask_tasks SET {', '.join(updates)}, updated_at=? WHERE id=?", params)

        # 活动记录
        changes = ", ".join(f"{k}={v}" for k, v in data.items() if k in ("title","description","priority","deadline","assigned_to"))
        conn.execute(
            "INSERT INTO itask_activities(task_id, author, type, content, created_at) VALUES(?,?,?,?,?)",
            (task_id, g.user["username"], "updated", f"Task updated: {changes}", now)
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/admin/task/<int:task_id>/guide", methods=["POST"])
@_require_admin
def api_admin_guide(task_id):
    """Robin 给指导/意见"""
    data = request.get_json(force=True)
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Content is required"}), 400

    conn = _db_conn()
    task = conn.execute("SELECT * FROM itask_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({"ok": False, "error": "Task not found"}), 404

    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, created_at) VALUES(?,?,?,?,?)",
        (task_id, g.user["username"], "guide", content, now)
    )
    # 状态变为待助教处理
    if task["status"] == "in_review":
        conn.execute("UPDATE itask_tasks SET status='in_progress', updated_at=? WHERE id=?",
                     (now, task_id))

    conn.commit()

    # 查助教邮箱
    au = conn.execute("SELECT * FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    conn.close()

    # 邮件通知助教
    if au:
        try:
            _notify_guidance(dict(task), content,
                             au.get("email") or GMAIL_USER, au["name"])
        except Exception as e:
            print(f"[internal-tasks] notify_guidance error: {e}")

    return jsonify({"ok": True})


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

    # 活动记录
    status_label = note or f"Status changed to {new_status}"
    conn.execute(
        "INSERT INTO itask_activities(task_id, author, type, content, created_at) VALUES(?,?,?,?,?)",
        (task_id, g.user["username"], "status_change", status_label, now)
    )
    conn.commit()

    # 查助教
    au = conn.execute("SELECT * FROM users WHERE username=?", (task["assigned_to"],)).fetchone()
    conn.close()

    # 邮件通知助教
    if au:
        try:
            _notify_status_change(dict(task), new_status,
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
    existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"ok": False, "error": f"Username '{username}' already exists"}), 400

    salt = secrets.token_hex(8)
    conn.execute("INSERT INTO users(username,name,role,password_hash,salt,must_change_pw) VALUES(?,?,?,?,?,0)",
                 (username, name, "assistant", _hash_pw(password, salt), salt))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "username": username, "password": password, "name": name})


@bp.route("/admin/delete-file/<int:file_id>", methods=["DELETE"])
@_require_admin
def api_admin_delete_file(file_id):
    """管理员删除文件"""
    conn = _db_conn()
    f = conn.execute("SELECT * FROM itask_files WHERE id=?", (file_id,)).fetchone()
    if not f:
        conn.close()
        return jsonify({"ok": False, "error": "File not found"}), 404

    # 删除物理文件
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
