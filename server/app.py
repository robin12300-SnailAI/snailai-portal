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
# 数据库路径优先级：
#   1) 若设置了 DB_PATH 环境变量，遵循它（Render 蓝图/控制台可设）
#   2) 否则若 Persistent Disk 已挂载（/data 存在），用 /data/snailai.db（持久化，重新部署不丢）
#   3) 否则本地开发回退到 server/ 目录
if os.environ.get("DB_PATH"):
    DB_PATH = Path(os.environ["DB_PATH"])
elif os.path.exists("/data"):
    DB_PATH = Path("/data/snailai.db")
else:
    DB_PATH = Path(SERVER_DIR / "snailai.db")
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
      must_change_pw INTEGER DEFAULT 1,
      referrer TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS capabilities(
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      description TEXT,
      category TEXT,
      points INTEGER DEFAULT 10
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
    CREATE TABLE IF NOT EXISTS ai_needs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      seq INTEGER NOT NULL,
      title TEXT NOT NULL,
      content TEXT,
      category TEXT,
      priority TEXT,
      tags TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT,
      UNIQUE(username, seq)
    );
    CREATE TABLE IF NOT EXISTS directory(
      student_no INTEGER PRIMARY KEY,
      name TEXT,
      zoom_id TEXT,
      cpu TEXT,
      ram TEXT,
      storage TEXT,
      github TEXT,
      login_username TEXT,
      email TEXT,
      wechat TEXT,
      phone TEXT,
      online_course INTEGER DEFAULT 0,
      offline_course INTEGER DEFAULT 0,
      tuition_fee INTEGER DEFAULT 0,
      tuition_paid INTEGER DEFAULT 0,
      course_term TEXT,
      identity TEXT
    );
    CREATE TABLE IF NOT EXISTS points_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      source TEXT NOT NULL,
      ref_id TEXT,
      points INTEGER NOT NULL,
      granted_by TEXT,
      note TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS points_config(
      key TEXT PRIMARY KEY,
      value TEXT
    );
    CREATE TABLE IF NOT EXISTS assistant_assignments(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_username TEXT NOT NULL,
      assistant_username TEXT NOT NULL,
      can_edit_directory INTEGER DEFAULT 1,
      can_set_points INTEGER DEFAULT 1,
      can_view_db INTEGER DEFAULT 1,
      UNIQUE(student_username, assistant_username)
    );
    """)
    conn.commit()

    # 迁移：为已存在的旧库补列（全新库已由 CREATE 含列，ALTER 会抛错被忽略）
    for sql in [
        "ALTER TABLE users ADD COLUMN must_change_pw INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN referrer TEXT",
        "ALTER TABLE capabilities ADD COLUMN points INTEGER DEFAULT 10",
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    # 角色迁移：Robin 提为总管理员（admin 角色，继承 instructor 全部权限）
    c.execute("UPDATE users SET role='admin' WHERE username='robin'")
    conn.commit()

    c.execute("SELECT COUNT(*) AS n FROM users")
    if c.fetchone()["n"] == 0:
        _seed_users(c)
    c.execute("SELECT COUNT(*) AS n FROM capabilities")
    if c.fetchone()["n"] == 0:
        _seed_capabilities(c)
    c.execute("SELECT COUNT(*) AS n FROM directory")
    if c.fetchone()["n"] == 0:
        _seed_directory(c)
    c.execute("SELECT COUNT(*) AS n FROM points_config")
    if c.fetchone()["n"] == 0:
        _seed_points_config(c)
    conn.commit()
    conn.close()


def _seed_directory(c):
    """灌入通讯录（源自腾讯智能表格最新 18 条快照，执行日：2026-07-09）。"""
    rows = [
        # student_no, name, zoom_id, cpu, ram, storage, github, login_username, tuition_paid
        (1,  "Serena 谢昕言", "Serena", "I5-12450HX", "16G", "475G", None, "serena", 1),
        (2,  "Mandy 曼蒂", "M Chen", "Intel64 Family 6 Model 170（Core Ultra 系列，GenuineIntel）", "32G", "1T", None, "mandy", 1),
        (3,  "Jenny", "Jenny", "i5双核", "8G", "256G", None, "jenny", 0),
        (4,  "Jackie", "Jackie", "i7-7500u", "16G", "1T", None, "jackie", 0),
        (5,  "仙路", "仙路/金丹", "i5-7Y54", "8G", "128G", None, "xianlu", 0),
        (6,  "雅雅CoCo", "CoCo ", "i7-1165G7", "16G", "512G", None, "coco", 1),
        (7,  "谢侑辰", "jason", "Apple M1", "8G", "460G", "jason918262", "xieyouchen", 0),
        (8,  "吴清", "Sean", "i5-14400", "16G", "512G", "ksiwuqing-cmyk", "wuqing", 0),
        (9,  "蒋培", "James", "i5-14400", "16G", "512G", "jiangpei555", "jiangpei", 0),
        (10, "laoliu", "X.LIU", "Intel Core i5-8250U", "8G", "237G", None, "laoliu", 1),
        (11, "suping", "suping / grace", "i5-1145G7", "16G", "512G", None, "suping", 0),
        (12, "Lucy", "LU shi", "Apple M2", "8G", "256G", None, "lucy", 0),
        (13, "step", "STEPHANIE WANG", "Apple M5", "10G", "62.8G", None, "step", 0),
        (14, "子霖", "zilin sun / Samsungsm-x20", "i7-1255U", "16G", "459G", None, "zilin", 1),
        (15, "Yuchen Guo", None, None, None, None, "mynameisgy", None, 0),
        (16, "Serene电脑", None, None, None, None, "rssz12300", None, 0),
        (17, "Robin", None, None, None, None, "robin12300-snailai", None, 0),
        (18, "张蕊蕊", "zrr", None, None, None, "ZRR168", None, 0),
    ]
    for (no, name, zoom, cpu, ram, storage, github, login, paid) in rows:
        c.execute(
            "INSERT OR IGNORE INTO directory(student_no, name, zoom_id, cpu, ram, storage, "
            "github, login_username, tuition_paid, identity) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (no, name, zoom, cpu, ram, storage, github, login, paid, "学员"))


def _seed_points_config(c):
    c.execute("INSERT OR IGNORE INTO points_config(key, value) VALUES('referral_bonus', '50')")
    c.execute("INSERT OR IGNORE INTO points_config(key, value) VALUES('default_cap_points', '10')")


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
    return {"username": row["username"], "name": row["name"], "role": row["role"],
            "must_change_pw": bool(row.get("must_change_pw", 0))}


def _role_of(user):
    return user["role"] if user else None


def _is_admin(user):
    return bool(user and user["role"] == "admin")


def _is_staff(user):
    return bool(user and user["role"] in ("ta", "instructor", "admin"))


# 列 -> 允许修改的角色
_COLUMN_ROLES = {
    "self": ["student", "ta", "instructor"],   # 学员自查；助教/总讲师可代勾
    "ta": ["ta", "instructor"],                # 助教初审；总讲师可代
    "final": ["instructor"],                   # 仅总讲师最终确认
}


def _can_edit(user, column, target_username):
    role = _role_of(user)
    # 总管理员继承 instructor 全部权限
    if role == "admin":
        return True
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
    if not user or user["role"] not in ("ta", "instructor", "admin"):
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
    # 助教确认（ta=1）即发放能力项成长点数（判重防刷）
    if column == "ta" and value:
        _grant_cap_points(conn, username, cap_id, user["username"])
    conn.commit()
    conn.close()
    return jsonify(ok=True, column=column, value=value, updated_by=user["username"],
                   updated_at=now)


# ---------------------------------------------------------------- 我的 AI 刚需
def _can_manage_need(user, owner_username):
    """学员只能管理自己的；助教/总讲师可管理任意学员的。"""
    if not user:
        return False
    if user["role"] == "student":
        return user["username"] == owner_username
    return user["role"] in ("ta", "instructor", "admin")


@app.route("/api/ai-needs", methods=["GET"])
def api_list_needs():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    # 学员只能看自己的；助教/总讲师可指定 username
    req_user = request.args.get("username")
    if user["role"] == "student":
        target = user["username"]
    else:
        target = req_user or user["username"]
    conn = db_conn()
    rows = conn.execute(
        "SELECT id, username, seq, title, content, category, priority, tags, "
        "created_at, updated_at FROM ai_needs WHERE username=? ORDER BY seq",
        (target,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        except Exception:
            d["tags"] = []
        out.append(d)
    return jsonify(ok=True, username=target, needs=out)


@app.route("/api/ai-needs", methods=["POST"])
def api_create_need():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    data = request.get_json(silent=True) or {}
    # 目标学员：学员只能给自己建；助教/总讲师可指定
    if user["role"] == "student":
        target = user["username"]
    else:
        target = (data.get("username") or "").strip() or user["username"]
    if not target:
        return jsonify(ok=False, error="缺少目标学员"), 400
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(ok=False, error="标题不能为空"), 400
    content = data.get("content") or ""
    category = (data.get("category") or "").strip()
    priority = (data.get("priority") or "中").strip()
    if priority not in ("高", "中", "低"):
        priority = "中"
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.replace("，", ",").split(",") if x.strip()]
    tags_json = json.dumps(tags, ensure_ascii=False)

    conn = db_conn()
    u = conn.execute("SELECT username FROM users WHERE username=?", (target,)).fetchone()
    if not u:
        conn.close()
        return jsonify(ok=False, error="目标学员不存在"), 404
    row = conn.execute("SELECT MAX(seq) AS m FROM ai_needs WHERE username=?",
                       (target,)).fetchone()
    seq = (row["m"] or 0) + 1
    now = datetime.datetime.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO ai_needs(username, seq, title, content, category, priority, "
        "tags, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (target, seq, title, content, category, priority, tags_json, now, now))
    nid = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=nid, seq=seq)


@app.route("/api/ai-needs/<int:need_id>", methods=["PUT"])
def api_update_need(need_id):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    row = conn.execute("SELECT username FROM ai_needs WHERE id=?",
                       (need_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify(ok=False, error="记录不存在"), 404
    if not _can_manage_need(user, row["username"]):
        conn.close()
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        conn.close()
        return jsonify(ok=False, error="标题不能为空"), 400
    content = data.get("content") or ""
    category = (data.get("category") or "").strip()
    priority = (data.get("priority") or "中").strip()
    if priority not in ("高", "中", "低"):
        priority = "中"
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.replace("，", ",").split(",") if x.strip()]
    tags_json = json.dumps(tags, ensure_ascii=False)
    now = datetime.datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE ai_needs SET title=?, content=?, category=?, priority=?, tags=?, "
        "updated_at=? WHERE id=?",
        (title, content, category, priority, tags_json, now, need_id))
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=need_id)


@app.route("/api/ai-needs/<int:need_id>", methods=["DELETE"])
def api_delete_need(need_id):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    row = conn.execute("SELECT username FROM ai_needs WHERE id=?",
                       (need_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify(ok=False, error="记录不存在"), 404
    if not _can_manage_need(user, row["username"]):
        conn.close()
        return jsonify(ok=False, error="无权限"), 403
    conn.execute("DELETE FROM ai_needs WHERE id=?", (need_id,))
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=need_id)


# ---------------------------------------------------------------- 密码管理
@app.route("/api/change-password", methods=["POST"])
def api_change_password():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    data = request.get_json(silent=True) or {}
    old_pw = data.get("old_password") or ""
    new_pw = data.get("new_password") or ""
    if len(new_pw) < 4:
        return jsonify(ok=False, error="新密码至少 4 位"), 400
    conn = db_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?",
                       (user["username"],)).fetchone()
    if _hash_pw(old_pw, row["salt"]) != row["password_hash"]:
        conn.close()
        return jsonify(ok=False, error="原密码错误"), 403
    salt = secrets.token_hex(16)
    conn.execute(
        "UPDATE users SET password_hash=?, salt=?, must_change_pw=0 WHERE username=?",
        (_hash_pw(new_pw, salt), salt, user["username"]))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/admin/reset-password", methods=["POST"])
def api_admin_reset_password():
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    target = (data.get("username") or "").strip()
    if not target:
        return jsonify(ok=False, error="缺少用户名"), 400
    conn = db_conn()
    row = conn.execute("SELECT username FROM users WHERE username=?",
                       (target,)).fetchone()
    if not row:
        conn.close()
        return jsonify(ok=False, error="用户不存在"), 404
    salt = secrets.token_hex(16)
    conn.execute(
        "UPDATE users SET password_hash=?, salt=?, must_change_pw=1 WHERE username=?",
        (_hash_pw("12345", salt), salt, target))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


# ---------------------------------------------------------------- 通讯录 (directory)
_DIR_FIELDS = ["student_no", "name", "zoom_id", "cpu", "ram", "storage", "github",
               "login_username", "email", "wechat", "phone", "online_course",
               "offline_course", "tuition_fee", "tuition_paid", "course_term", "identity"]
_DIR_INT = {"student_no", "online_course", "offline_course", "tuition_fee", "tuition_paid"}


@app.route("/api/directory", methods=["GET"])
def api_dir_list():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    if user["role"] == "student":
        rows = conn.execute("SELECT * FROM directory WHERE login_username=?",
                            (user["username"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM directory ORDER BY student_no").fetchall()
    conn.close()
    return jsonify(ok=True, rows=[dict(r) for r in rows])


@app.route("/api/directory", methods=["POST"])
def api_dir_create():
    user = _current_user()
    if user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    fields = [f for f in _DIR_FIELDS if f in data and f != "student_no"]
    if not fields:
        return jsonify(ok=False, error="无有效字段"), 400
    vals = []
    for f in fields:
        v = data[f]
        vals.append(int(v or 0) if f in _DIR_INT else v)
    cols = ", ".join(fields)
    ph = ", ".join("?" * len(fields))
    conn = db_conn()
    cur = conn.execute(f"INSERT INTO directory({cols}) VALUES({ph})", vals)
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=new_id)


@app.route("/api/directory/<int:no>", methods=["PUT"])
def api_dir_update(no):
    user = _current_user()
    if user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    fields = [f for f in _DIR_FIELDS if f in data and f != "student_no"]
    if not fields:
        return jsonify(ok=False, error="无有效字段"), 400
    sets, vals = [], []
    for f in fields:
        v = data[f]
        sets.append(f"{f}=?")
        vals.append(int(v or 0) if f in _DIR_INT else v)
    vals.append(no)
    conn = db_conn()
    conn.execute(f"UPDATE directory SET {', '.join(sets)} WHERE student_no=?", vals)
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/directory/<int:no>", methods=["DELETE"])
def api_dir_delete(no):
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限（仅总管理员可删除）"), 403
    conn = db_conn()
    conn.execute("DELETE FROM directory WHERE student_no=?", (no,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


# ---------------------------------------------------------------- 成长点数
@app.route("/api/points/adjust", methods=["POST"])
def api_points_adjust():
    user = _current_user()
    if user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    target = (data.get("username") or "").strip()
    try:
        pts = int(data.get("points", 0))
    except (ValueError, TypeError):
        return jsonify(ok=False, error="点数必须为整数"), 400
    if not target or pts == 0:
        return jsonify(ok=False, error="缺少用户名或点数"), 400
    conn = db_conn()
    u = conn.execute("SELECT username FROM users WHERE username=?",
                     (target,)).fetchone()
    if not u:
        conn.close()
        return jsonify(ok=False, error="用户不存在"), 404
    conn.execute(
        "INSERT INTO points_log(username, source, ref_id, points, granted_by, note) "
        "VALUES(?,?,?,?,?,?)",
        (target, "manual", None, pts, user["username"],
         (data.get("note") or "").strip() or "手动调整"))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/points/summary", methods=["GET"])
def api_points_summary():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    if user["role"] == "student":
        rows = conn.execute(
            "SELECT username, COALESCE(SUM(points),0) AS total "
            "FROM points_log WHERE username=? GROUP BY username",
            (user["username"],)).fetchall()
    else:
        target = request.args.get("username")
        if target:
            rows = conn.execute(
                "SELECT username, COALESCE(SUM(points),0) AS total "
                "FROM points_log WHERE username=? GROUP BY username",
                (target,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT username, COALESCE(SUM(points),0) AS total "
                "FROM points_log GROUP BY username").fetchall()
    names = {}
    for r in rows:
        nm = conn.execute("SELECT name FROM users WHERE username=?",
                          (r["username"],)).fetchone()
        names[r["username"]] = (nm["name"] if nm else r["username"])
    conn.close()
    out = [{"username": r["username"],
            "name": names.get(r["username"], r["username"]),
            "points": r["total"]} for r in rows]
    return jsonify(ok=True, summary=out)


def _grant_cap_points(conn, username, cap_id, granted_by):
    """助教确认(ta=1)时发放能力项成长点数；同 cap_id 判重防刷。"""
    exist = conn.execute(
        "SELECT 1 FROM points_log WHERE username=? AND source='capability' AND ref_id=?",
        (username, cap_id)).fetchone()
    if exist:
        return
    row = conn.execute("SELECT points FROM capabilities WHERE id=?",
                       (cap_id,)).fetchone()
    pts = row["points"] if row else 10
    conn.execute(
        "INSERT INTO points_log(username, source, ref_id, points, granted_by, note) "
        "VALUES(?,?,?,?,?,?)",
        (username, "capability", cap_id, pts, granted_by, f"能力项 {cap_id} 确认"))


# ---------------------------------------------------------------- 总管理员：全表浏览 + 权限
_ADMIN_TABLES = ["users", "capabilities", "checks", "ai_needs", "directory",
                 "points_log", "points_config", "assistant_assignments"]
# 助教/讲师只读浏览白名单（不含 users，避免暴露密码哈希与会话）
_TA_BROWSE = ["capabilities", "checks", "ai_needs", "directory",
             "points_log", "points_config"]


@app.route("/api/admin/tables", methods=["GET"])
def api_admin_tables():
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    return jsonify(ok=True, tables=_ADMIN_TABLES)


@app.route("/api/admin/table/<name>", methods=["GET"])
def api_admin_table(name):
    user = _current_user()
    if _is_admin(user):
        allowed = _ADMIN_TABLES
    elif user and user["role"] in ("ta", "instructor"):
        allowed = _TA_BROWSE
    else:
        return jsonify(ok=False, error="无权限"), 403
    if name not in allowed:
        return jsonify(ok=False, error="不允许访问该表"), 400
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit, offset = 100, 0
    conn = db_conn()
    rows = conn.execute(f"SELECT * FROM '{name}' LIMIT ? OFFSET ?",
                        (limit, offset)).fetchall()
    total = conn.execute(f"SELECT COUNT(*) AS n FROM '{name}'").fetchone()["n"]
    conn.close()
    return jsonify(ok=True, name=name, total=total,
                   rows=[dict(r) for r in rows])


@app.route("/api/admin/assistant-assignments", methods=["GET"])
def api_aa_list():
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    rows = conn.execute(
        "SELECT a.id, a.student_username, a.assistant_username, a.can_edit_directory, "
        "a.can_set_points, a.can_view_db, s.name AS student_name, t.name AS assistant_name "
        "FROM assistant_assignments a "
        "LEFT JOIN users s ON s.username=a.student_username "
        "LEFT JOIN users t ON t.username=a.assistant_username "
        "ORDER BY a.student_username").fetchall()
    conn.close()
    return jsonify(ok=True, assignments=[dict(r) for r in rows])


@app.route("/api/admin/assistant-assignments", methods=["POST"])
def api_aa_create():
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    stu = (data.get("student_username") or "").strip()
    ast = (data.get("assistant_username") or "").strip()
    if not stu or not ast:
        return jsonify(ok=False, error="缺少学员或助教"), 400
    conn = db_conn()
    conn.execute(
        "INSERT OR IGNORE INTO assistant_assignments"
        "(student_username, assistant_username, can_edit_directory, can_set_points, can_view_db) "
        "VALUES(?,?,?,?,?)",
        (stu, ast,
         int(bool(data.get("can_edit_directory", True))),
         int(bool(data.get("can_set_points", True))),
         int(bool(data.get("can_view_db", True)))))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/admin/assistant-assignments/<int:aid>", methods=["PUT"])
def api_aa_update(aid):
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    fields, vals = [], []
    for f in ("can_edit_directory", "can_set_points", "can_view_db"):
        if f in data:
            fields.append(f"{f}=?")
            vals.append(int(bool(data[f])))
    if fields:
        vals.append(aid)
        conn = db_conn()
        conn.execute(
            f"UPDATE assistant_assignments SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()
        conn.close()
    return jsonify(ok=True)


@app.route("/api/admin/assistant-assignments/<int:aid>", methods=["DELETE"])
def api_aa_delete(aid):
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    conn.execute("DELETE FROM assistant_assignments WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


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
