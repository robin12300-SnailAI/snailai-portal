# -*- coding: utf-8 -*-
"""
蜗牛AI 学员门户 — 后端（SQLite + Flask）
========================================
统一存储：用户(学员/助教/总讲师)、能力清单勾选、登录会话。
纯前端站点由本服务一并托管（同源，免 CORS）；同时开放 CORS 以便
GitHub Pages 版门户也能调用本 API。

表结构
------
users(id, username UNIQUE, name, role, password_hash, salt)
  role ∈ {student, ta, instructor}
capabilities(id PK, title, description, category)
checks(student_username, cap_id, self, ta, final, updated_at, updated_by)
  PK(student_username, cap_id)
sessions(token PK, username, created_at, expires_at)

运行
----
venv/bin/python server/app.py            # 默认 127.0.0.1:5000
PORT=8080 venv/bin/python server/app.py  # 自定义端口
"""
import os
import json
import sqlite3
import hashlib
import secrets
import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

BASE = Path(__file__).resolve().parent.parent          # 官网学生登录/
SERVER_DIR = Path(__file__).resolve().parent           # 官网学生登录/server/
# 数据库路径：Render 上挂 Persistent Disk 时设 DB_PATH=/data/snailai.db，
# 本地开发默认放在 server/ 目录下。确保父目录存在。
DB_PATH = Path(os.environ.get("DB_PATH", str(SERVER_DIR / "snailai.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("PORT", "5000"))
HOST = os.environ.get("HOST", "0.0.0.0")
# 允许跨域的来源（GitHub Pages 主站等）。生产可改为你的域名。
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
SESSION_TTL_HOURS = 24 * 7  # 会话有效期 7 天

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------- 数据库
def db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = db_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      role TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      salt TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS capabilities(
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      category TEXT
    );
    CREATE TABLE IF NOT EXISTS checks(
      student_username TEXT NOT NULL,
      cap_id TEXT NOT NULL,
      self INTEGER DEFAULT 0,
      ta INTEGER DEFAULT 0,
      final INTEGER DEFAULT 0,
      updated_at TEXT,
      updated_by TEXT,
      PRIMARY KEY(student_username, cap_id)
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY,
      username TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL
    );
    """)
    conn.commit()

    c.execute("SELECT COUNT(*) AS n FROM users")
    if c.fetchone()["n"] == 0:
        _seed_users(c)
    c.execute("SELECT COUNT(*) AS n FROM capabilities")
    if c.fetchone()["n"] == 0:
        _seed_capabilities(c)
    conn.commit()
    conn.close()


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               salt.encode("utf-8"), 100000).hex()


def _seed_users(c):
    # (username, name, role, password)
    users = [
        ("serena", "Serena 谢昕言", "student", "12345"),
        ("mandy", "Mandy 曼蒂", "student", "12345"),
        ("jenny", "Jenny", "student", "12345"),
        ("jackie", "Jackie", "student", "12345"),
        ("xianlu", "仙路", "student", "12345"),
        ("coco", "雅雅CoCo", "student", "12345"),
        ("xieyouchen", "谢侑辰", "student", "12345"),
        ("wuqing", "吴清", "student", "12345"),
        ("jiangpei", "蒋培", "student", "12345"),
        ("laoliu", "laoliu", "student", "12345"),
        ("suping", "suping", "student", "12345"),
        ("lucy", "Lucy", "student", "12345"),
        ("step", "step", "student", "12345"),
        ("zilin", "子霖", "student", "12345"),
        ("yuchenguo", "Yuchen Guo", "student", "12345"),
        ("zhangruirui", "张蕊蕊", "student", "12345"),
        ("zhujiao", "蜗牛AI 助教", "ta", "12300"),
        ("robin", "Robin Luo", "instructor", "12300"),
    ]
    for username, name, role, pw in users:
        salt = secrets.token_hex(16)
        c.execute(
            "INSERT OR IGNORE INTO users(username, name, role, password_hash, salt) "
            "VALUES(?,?,?,?,?)",
            (username, name, role, _hash_pw(pw, salt), salt),
        )


def _seed_capabilities(c):
    caps = [
        ("c01", "课前准备", "下载 WorkBuddy", "前往腾讯云下载 WorkBuddy 客户端"),
        ("c02", "课前准备", "微信登录激活", "使用微信账号登录并完成激活"),
        ("c03", "课前准备", "对话与调专家", "确认能正常对话，安装技能，并且调用技能和专家进行简单对话，例如怎么使用你？"),
        ("c04", "课前准备", "成长计划积分", "参加 WorkBuddy 成长计划，赢取越多越好积分（赢积分的同时熟悉功能）"),
        ("c05", "课前准备", "龙虾自我介绍", "给龙虾介绍做自我介绍：姓名，性别，年龄，职业，兴趣爱好，以及做事风格等"),
        ("c06", "课前准备", "龙虾企微微信", "龙虾助理设置：企业微信和微信都要设置好"),
        ("c07", "课前准备", "建龙虾文件夹", "在电脑里面创建一个文件夹，起名《龙虾文件夹》"),
        ("c08", "课前准备", "微信输入法录音", "安装微信输入法：手机和电脑同时安装，然后设置右边 Shift 按键为 AI 录音转文字"),
        ("c09", "课前准备", "Zoom调试", "调试电脑 Zoom 语音和共享成功使用，方便直播课堂分享"),
    ]
    for cid, cat, title, desc in caps:
        c.execute(
            "INSERT OR IGNORE INTO capabilities(id, title, description, category) VALUES(?,?,?,?)",
            (cid, title, desc, cat),
        )


# ---------------------------------------------------------------- 鉴权辅助
def _auth_user(username, password):
    conn = db_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row:
        return None
    h = _hash_pw(password, row["salt"])
    if h != row["password_hash"]:
        return None
    return dict(row)


def _create_session(username):
    token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    conn = db_conn()
    conn.execute("INSERT INTO sessions(token, username, expires_at) VALUES(?,?,?)",
                 (token, username, expires))
    conn.commit()
    conn.close()
    return token


def _get_session(token):
    if not token:
        return None
    conn = db_conn()
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


def _public_user(row):
    return {"username": row["username"], "name": row["name"], "role": row["role"]}


def _role_of(user):
    return user["role"] if user else None


# 列 -> 允许修改的角色
_COLUMN_ROLES = {
    "self": ["student", "ta", "instructor"],   # 学员自查；助教/总讲师可代勾
    "ta": ["ta", "instructor"],                # 助教初审；总讲师可代
    "final": ["instructor"],                   # 仅总讲师最终确认
}


def _can_edit(user, column, target_username):
    role = _role_of(user)
    if role not in _COLUMN_ROLES.get(column, []):
        return False
    # 学员只能改自己的自查
    if role == "student" and column == "self" and user["username"] != target_username:
        return False
    return True


# ---------------------------------------------------------------- 中间件 CORS
@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return resp


@app.route("/api/options", methods=["OPTIONS"])
@app.route("/api/<path:_>", methods=["OPTIONS"])
def _options():
    return ("", 204)


# ---------------------------------------------------------------- API
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = _auth_user(username, password)
    if not user:
        return jsonify(ok=False, error="用户名或密码错误"), 401
    token = _create_session(username)
    return jsonify(ok=True, token=token, user=_public_user(user))


@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = _token_from_req()
    if token:
        conn = db_conn()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    return jsonify(ok=True)


def _token_from_req():
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Bearer "):
        return ah[7:]
    return request.headers.get("X-Auth-Token") or (request.get_json(silent=True) or {}).get("token")


def _current_user():
    return _get_session(_token_from_req())


@app.route("/api/me", methods=["GET"])
def api_me():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    return jsonify(ok=True, user=_public_user(user))


@app.route("/api/capabilities", methods=["GET"])
def api_capabilities():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    rows = conn.execute("SELECT id, title, description, category FROM capabilities "
                        "ORDER BY id").fetchall()
    conn.close()
    return jsonify(ok=True, capabilities=[dict(r) for r in rows])


@app.route("/api/students", methods=["GET"])
def api_students():
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor"):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    rows = conn.execute("SELECT username, name FROM users WHERE role='student' "
                        "ORDER BY username").fetchall()
    conn.close()
    return jsonify(ok=True, students=[dict(r) for r in rows])


@app.route("/api/checks/<username>", methods=["GET"])
def api_get_checks(username):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    # 学员只能看自己；助教/总讲师可看任意学员
    if user["role"] == "student" and user["username"] != username:
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    rows = conn.execute(
        "SELECT cap_id, self, ta, final, updated_at, updated_by "
        "FROM checks WHERE student_username=?", (username,)).fetchall()
    conn.close()
    out = {}
    for r in rows:
        out[r["cap_id"]] = {
            "self": bool(r["self"]), "ta": bool(r["ta"]), "final": bool(r["final"]),
            "updated_at": r["updated_at"], "updated_by": r["updated_by"],
        }
    return jsonify(ok=True, username=username, checks=out)


@app.route("/api/checks/<username>/<cap_id>", methods=["PUT"])
def api_put_check(username, cap_id):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    data = request.get_json(silent=True) or {}
    column = data.get("column")
    value = bool(int(data.get("value", 0)))
    if column not in ("self", "ta", "final"):
        return jsonify(ok=False, error="非法字段"), 400
    if not _can_edit(user, column, username):
        return jsonify(ok=False, error="无权限修改该列"), 403

    conn = db_conn()
    # 校验目标学员存在且确为学员
    t = conn.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
    if not t or t["role"] != "student":
        conn.close()
        return jsonify(ok=False, error="目标用户不是学员"), 404
    # 校验能力项存在
    cap = conn.execute("SELECT id FROM capabilities WHERE id=?", (cap_id,)).fetchone()
    if not cap:
        conn.close()
        return jsonify(ok=False, error="能力项不存在"), 404

    # 读取已有勾选，仅更新目标列，保留其它列
    old = conn.execute(
        "SELECT self, ta, final FROM checks WHERE student_username=? AND cap_id=?",
        (username, cap_id)).fetchone()
    cur = {"self": 0, "ta": 0, "final": 0}
    if old:
        cur = {"self": old["self"], "ta": old["ta"], "final": old["final"]}
    cur[column] = int(value)

    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO checks(student_username, cap_id, self, ta, final, updated_at, updated_by) "
        "VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(student_username, cap_id) DO UPDATE SET "
        "self=excluded.self, ta=excluded.ta, final=excluded.final, "
        "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
        (username, cap_id, cur["self"], cur["ta"], cur["final"],
         now, user["username"]),
    )
    conn.commit()
    conn.close()
    return jsonify(ok=True, column=column, value=value, updated_by=user["username"],
                   updated_at=now)


# ---------------------------------------------------------------- 静态站点托管
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    # 根路径 -> 官网首页（已合并为 repo 根 index.html）
    if not path:
        return send_from_directory(BASE, "index.html")
    target = (BASE / path).resolve()
    # 防目录穿越
    if BASE not in target.parents and target != BASE:
        return send_from_directory(BASE, "index.html")
    # 目录 -> index.html
    if target.is_dir():
        idx = target / "index.html"
        if idx.is_file():
            return send_from_directory(BASE, path.rstrip("/") + "/index.html")
        return send_from_directory(BASE, "404.html"), 404
    # 无扩展名链接自动补 .html（兼容 GitHub Pages 风格，如 /faq/mobile）
    if not target.exists() and target.with_suffix(".html").is_file():
        return send_from_directory(BASE, path + ".html")
    if target.is_file():
        return send_from_directory(BASE, path)
    # 404
    return send_from_directory(BASE, "404.html"), 404


# 模块加载时即初始化数据库：gunicorn 以模块方式导入时也会执行，
# 确保 Render 等生产环境在首次请求前已建好表并灌入种子数据。
init_db()
print(f"[蜗牛AI Portal] 数据库: {DB_PATH}")

if __name__ == "__main__":
    print(f"[蜗牛AI Portal] 监听: http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
