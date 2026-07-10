# -*- coding: utf-8 -*-
"""
蜗牛AI 学员门户 — 后端（SQLite + Flask）
========================================
统一存储：用户(学员/助教/总讲师)、能力清单勾选、登录会话、蜗牛问答。
纯前端站点由本服务一并托管（同源，免 CORS）；同时开放 CORS 以便
GitHub Pages 版门户也能调用本 API。

表结构
------
users(id, username UNIQUE, name, role, password_hash, salt)
  role ∈ {student, ta, instructor, admin}
capabilities(id PK, title, description, category)
checks(student_username, cap_id, self, ta, final, updated_at, updated_by)
  PK(student_username, cap_id)
sessions(token PK, username, created_at, expires_at)
qa_threads(id PK, author_type, author_username, author_name, title, body, pinned, deleted)
qa_replies(id PK, thread_id, parent_id, author_type, author_username, author_name, body, deleted)

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
import re
import fcntl
import requests
from apscheduler.schedulers.background import BackgroundScheduler

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


# ---------------------------------------------------------------- 限流 / 防爆破 (SQLite 持久化，跨 worker 可靠)
import time as _time
from functools import wraps as _wraps

_RL_QUERY_LIMIT = 60             # 查询类 GET：每分钟 60 次
_RL_QUERY_WINDOW = 60
_RL_LOGIN_LIMIT = 10             # 登录 POST：每分钟 10 次
_RL_LOGIN_WINDOW = 60
_LOGIN_MAX_FAILS = 5             # 连续失败 5 次
_LOGIN_LOCK_SEC = 15 * 60        # 锁定 15 分钟


def _rl_db():
    c = db_conn()
    c.execute("ATTACH DATABASE ? AS _rl", (DB_PATH,))
    return c


def _rate_check(key, limit, window):
    """SQLite 滑动窗口限流：原子 INSERT/COUNT/DELETE，跨 worker 一致。"""
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
        @_wraps(fn)
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
                return jsonify(ok=False, error="请求过于频繁，请稍后再试 (rate limit)"), 429
            return fn(*a, **k)
        return wrapper
    return deco


def _login_lock_check(username):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        row = conn.execute(
            "SELECT fail_count, locked_until FROM login_fail_locks WHERE username=?",
            (username,)).fetchone()
        if not row:
            return (False, 0)
        fail_count, locked_until = row
        if locked_until and _time.time() < locked_until:
            return (True, int(locked_until - _time.time()))
        if locked_until and _time.time() >= locked_until:
            conn.execute("DELETE FROM login_fail_locks WHERE username=?", (username,))
            conn.commit()
        return (False, 0)
    finally:
        conn.close()


def _login_fail_incr(username):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        row = conn.execute("SELECT fail_count FROM login_fail_locks WHERE username=?",
                           (username,)).fetchone()
        cnt = (row[0] if row else 0) + 1
        locked_until = _time.time() + _LOGIN_LOCK_SEC if cnt >= _LOGIN_MAX_FAILS else None
        conn.execute(
            "INSERT INTO login_fail_locks(username, fail_count, locked_until) VALUES(?,?,?) "
            "ON CONFLICT(username) DO UPDATE SET fail_count=excluded.fail_count, locked_until=excluded.locked_until",
            (username, cnt, locked_until))
        conn.commit()
    finally:
        conn.close()


def _login_fail_clear(username):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM login_fail_locks WHERE username=?", (username,))
        conn.commit()
    finally:
        conn.close()


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
    CREATE TABLE IF NOT EXISTS login_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      ip TEXT,
      ua TEXT,
      country TEXT,
      region TEXT,
      city TEXT,
      login_at TEXT DEFAULT (datetime('now')),
      logout_at TEXT,
      last_activity_at TEXT
    );
    CREATE TABLE IF NOT EXISTS page_views(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      visitor_id TEXT,
      username TEXT,
      path TEXT NOT NULL,
      referrer TEXT,
      entered_at TEXT,
      duration_sec INTEGER,
      is_login INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS qa_threads(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      author_type TEXT NOT NULL,        -- 'student' | 'anon'
      author_username TEXT,             -- NULL for anon
      author_name TEXT NOT NULL,        -- 显示名（学员=真实姓名；匿名=自取昵称）
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      pinned INTEGER DEFAULT 0,
      deleted INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS qa_replies(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      thread_id INTEGER NOT NULL,
      parent_id INTEGER,                -- NULL=顶层回答；否则=对某回复的追问
      author_type TEXT NOT NULL,
      author_username TEXT,
      author_name TEXT NOT NULL,
      body TEXT NOT NULL,
      deleted INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY(thread_id) REFERENCES qa_threads(id)
    );
    CREATE TABLE IF NOT EXISTS rate_limits(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      rl_key TEXT NOT NULL,
      hit_at REAL NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_rate_limits_key_time ON rate_limits(rl_key, hit_at);
    CREATE TABLE IF NOT EXISTS login_fail_locks(
      username TEXT PRIMARY KEY,
      fail_count INTEGER DEFAULT 0,
      locked_until REAL DEFAULT 0
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
    # 空库时先 seed 全部账号（学员/助教/总讲师/管理员）。必须在提升 robin 与 _ensure_ta_accounts 之前，
    # 否则后者先插入助教会让 users 表非空导致 _seed_users 被跳过；且 seed 会把 robin 写成 instructor，
    # 故提升 robin 为 admin 必须放在 seed 之后执行。
    c.execute("SELECT COUNT(*) AS n FROM users")
    if c.fetchone()["n"] == 0:
        _seed_users(c)
    # 角色迁移：Robin 提为总管理员（admin 角色，继承 instructor 全部权限）
    c.execute("UPDATE users SET role='admin' WHERE username='robin'")
    # 助教账号保障：确保助教角色 + 创建缺失的助教账号（幂等，每次启动执行，作用于已有生产库）
    _ensure_ta_accounts(c)
    conn.commit()
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


def _ensure_ta_accounts(c):
    """确保指定助教账号角色为 ta，并为缺失账号创建初始密码 12345。
    幂等：每次服务启动都执行，因此对已在运行的生产库也生效（种子仅在空库时跑）。"""
    TA_ACCOUNTS = {
        "jiangpei": "Jiang Pei",
        "luoyajuan": "Luo Yajuan",
        "wuqing": "Wu Qing",
        "xiejing": "Xie Jing",
        "zhangruirui": "Zhang Ruirui",
    }
    for username, name in TA_ACCOUNTS.items():
        salt = secrets.token_hex(16)
        pw_hash = _hash_pw("12345", salt)
        # 若该账号已存在且是 student，重置密码并提升为 ta
        c.execute(
            "UPDATE users SET password_hash=?, salt=?, role='ta' WHERE username=? AND role='student'",
            (pw_hash, salt, username),
        )
        # 若该账号已存在且 role 不是 ta，也提升为 ta（不重置密码，保留用户可能已改的密码）
        c.execute(
            "UPDATE users SET role='ta' WHERE username=? AND role != 'ta'",
            (username,),
        )
        # 若不存在，创建为 ta / 初始密码 12345
        c.execute(
            "INSERT OR IGNORE INTO users(username, name, role, password_hash, salt) "
            "VALUES(?,?,'ta',?,?)",
            (username, name, pw_hash, salt),
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


# ---------------------------------------------------------------- 访问分析：工具函数
def _client_ip():
    """取真实客户端 IP（Render 反向代理下必须读 X-Forwarded-For）。"""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or ""


def _geo_lookup(ip):
    """免费接口 ip-api.com 解析 国家/地区/城市（登录量小，性能无感）。"""
    if not ip:
        return ("", "", "")
    try:
        r = requests.get(
            "http://ip-api.com/json/%s?fields=country,regionName,city&lang=zh-CN" % ip,
            timeout=3)
        if r.ok:
            d = r.json()
            return (d.get("country") or "", d.get("regionName") or "",
                    d.get("city") or "")
    except Exception:
        pass
    return ("", "", "")


_UA_DEVICE_RE = [
    (r"iPad", "iPad"), (r"iPhone", "iPhone"), (r"Android", "Android"),
    (r"Macintosh", "Mac"), (r"Windows", "Windows"), (r"Linux", "Linux"),
]
_UA_BROWSER_RE = [
    (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"),
    (r"Chrome/|CriOS", "Chrome"), (r"Firefox/|FxiOS", "Firefox"),
    (r"Safari/", "Safari"),
]


def _parse_ua(ua):
    if not ua:
        return ("未知", "未知")
    device = browser = "其他"
    for pat, name in _UA_DEVICE_RE:
        if re.search(pat, ua, re.I):
            device = name
            break
    for pat, name in _UA_BROWSER_RE:
        if re.search(pat, ua, re.I):
            browser = name
            break
    return (device, browser)


def _classify_referrer(ref):
    if not ref:
        return "直接访问"
    r = ref.lower()
    if "weixin.qq.com" in r or "qq.com" in r:
        return "微信"
    if "google" in r:
        return "谷歌"
    if "youtube" in r or "youtu.be" in r:
        return "YouTube"
    if "facebook" in r or "fb." in r:
        return "Facebook"
    if "twitter" in r or "t.co" in r:
        return "Twitter"
    if "linkedin" in r:
        return "LinkedIn"
    return "其他外链"


def _date_filter(date_col, from_date, to_date):
    where, params = "1=1", []
    if from_date:
        where += " AND DATE(%s) >= ?" % date_col
        params.append(from_date)
    if to_date:
        where += " AND DATE(%s) <= ?" % date_col
        params.append(to_date)
    return where, params


def _login_duration_sec(row):
    end = row["logout_at"] or row["last_activity_at"] or row["login_at"]
    try:
        d = (datetime.datetime.fromisoformat(end)
             - datetime.datetime.fromisoformat(row["login_at"])).total_seconds()
        return max(0, int(d))
    except Exception:
        return 0


def _fmt_dur(sec):
    sec = int(sec)
    if sec < 60:
        return "%d秒" % sec
    m, s = divmod(sec, 60)
    if m < 60:
        return "%d分%d秒" % (m, s)
    h, m = divmod(m, 60)
    return "%d时%d分" % (h, m)


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
@_rate_limit_deco(_RL_LOGIN_LIMIT, _RL_LOGIN_WINDOW, by_user=False)
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    # 失败锁定（防爆破弱密码账号，如 test/12345）
    locked, retry = _login_lock_check(username)
    if locked:
        return jsonify(ok=False, error=f"尝试次数过多，请 {retry} 秒后再试"), 429
    user = _auth_user(username, password)
    if not user:
        _login_fail_incr(username)
        return jsonify(ok=False, error="用户名或密码错误"), 401
    _login_fail_clear(username)
    token = _create_session(username)
    ip = _client_ip()
    ua = request.headers.get("User-Agent", "")
    country, region, city = _geo_lookup(ip)
    conn = db_conn()
    conn.execute(
        "INSERT INTO login_events(username, ip, ua, country, region, city, login_at) "
        "VALUES(?,?,?,?,?,?, datetime('now'))",
        (username, ip, ua, country, region, city))
    conn.commit()
    conn.close()
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


@app.route("/api/activity", methods=["POST"])
def api_activity():
    """已登录用户心跳：更新其最近一次登录的活跃时间（用于计算停留时长）。"""
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    now = datetime.datetime.utcnow().isoformat()
    conn = db_conn()
    conn.execute(
        "UPDATE login_events SET last_activity_at=? "
        "WHERE id=(SELECT MAX(id) FROM login_events WHERE username=?)",
        (now, user["username"]))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/track/pageview", methods=["POST"])
def api_track_pageview():
    """前端离开页面时上报停留（匿名也可，token 在 body 中）。"""
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify(ok=False, error="missing path"), 400
    try:
        dur = int(data.get("duration_sec") or 0)
    except (ValueError, TypeError):
        dur = 0
    ref = (data.get("referrer") or "")[:500]
    vid = (data.get("visitor_id") or "")[:128]
    token = data.get("token") or _token_from_req()
    username = None
    if token:
        u = _get_session(token)
        if u:
            username = u["username"]
    conn = db_conn()
    conn.execute(
        "INSERT INTO page_views(visitor_id, username, path, referrer, entered_at, "
        "duration_sec, is_login) VALUES(?,?,?,?, datetime('now'), ?, ?)",
        (vid, username, path, ref, dur, int(bool(username))))
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
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_me():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    return jsonify(ok=True, user=_public_user(user))


@app.route("/api/me/token", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_me_token():
    """返回当前用户一个 guaranteed-valid 的 API token。
    若已有未过期 token 则复用，否则新发一个（默认 7 天有效）。
    学员拿它交给 WorkBuddy 等助手，即可代查本人能力清单与成长点数。"""
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    username = user["username"]
    conn = db_conn()
    now = datetime.datetime.utcnow().isoformat()
    row = conn.execute(
        "SELECT token, expires_at FROM sessions "
        "WHERE username=? AND expires_at > ? ORDER BY expires_at DESC LIMIT 1",
        (username, now)).fetchone()
    if row:
        token, expires_at = row["token"], row["expires_at"]
    else:
        token = _create_session(username)
        r2 = conn.execute("SELECT expires_at FROM sessions WHERE token=?",
                          (token,)).fetchone()
        expires_at = r2["expires_at"] if r2 else None
    conn.close()
    return jsonify(ok=True, token=token, expires_at=expires_at)


@app.route("/api/capabilities", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_capabilities():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    rows = conn.execute("SELECT id, title, description, category, points FROM capabilities "
                        "ORDER BY id").fetchall()
    conn.close()
    return jsonify(ok=True, capabilities=[dict(r) for r in rows])


@app.route("/api/capabilities", methods=["POST"])
@_rate_limit_deco(20, 60)
def api_create_capability():
    """助教/讲师/管理员可新增 AI 能力项。"""
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    category = (data.get("category") or "").strip()
    points = data.get("points", 10)
    if not title:
        return jsonify(ok=False, error="标题不能为空"), 400
    if not category:
        return jsonify(ok=False, error="分类不能为空"), 400
    try:
        points = int(points)
        if points < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(ok=False, error="点数必须为非负整数"), 400

    conn = db_conn()
    # 生成新 id：取当前最大数字后缀 +1
    row = conn.execute(
        "SELECT id FROM capabilities WHERE id GLOB 'c[0-9]*' ORDER BY CAST(SUBSTR(id,2) AS INT) DESC LIMIT 1"
    ).fetchone()
    if row:
        next_num = int(row["id"][1:]) + 1
    else:
        next_num = 1
    new_id = f"c{next_num:02d}"

    # 防重复标题
    dup = conn.execute("SELECT id FROM capabilities WHERE title=?", (title,)).fetchone()
    if dup:
        conn.close()
        return jsonify(ok=False, error="已存在同名能力项"), 409

    conn.execute(
        "INSERT INTO capabilities(id, title, description, category, points) VALUES(?,?,?,?,?)",
        (new_id, title, description, category, points),
    )
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=new_id, title=title, description=description,
                   category=category, points=points)


@app.route("/api/capabilities/<cap_id>/points", methods=["PUT"])
def api_set_cap_points(cap_id):
    """助教/讲师/管理员可设置单项能力点数（用于成长点数配置）。"""
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    try:
        pts = int(data.get("points", 0))
    except (ValueError, TypeError):
        return jsonify(ok=False, error="点数必须为整数"), 400
    if pts < 0:
        return jsonify(ok=False, error="点数不能为负"), 400
    conn = db_conn()
    cap = conn.execute("SELECT id FROM capabilities WHERE id=?", (cap_id,)).fetchone()
    if not cap:
        conn.close()
        return jsonify(ok=False, error="能力项不存在"), 404
    conn.execute("UPDATE capabilities SET points=? WHERE id=?", (pts, cap_id))
    conn.commit()
    conn.close()
    return jsonify(ok=True, cap_id=cap_id, points=pts)


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
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
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


# ---------------------------------------------------------------- 蜗牛问答 (Q&A Board)
def _qa_author(user, anon_name):
    """解析发帖身份：登录学员→实名；否则匿名（需昵称）。
    返回 (author_type, author_username, author_name) 或 None（匿名未给昵称）。"""
    if user:
        return ("student", user["username"], user["name"])
    name = (anon_name or "").strip()
    if not name:
        return None
    return ("anon", None, name[:40])


def _can_delete_qa(user, author_username):
    """作者本人（学员）或助教/讲师/管理员可删。"""
    if not user:
        return False
    if _is_staff(user):
        return True
    return user["role"] == "student" and user["username"] == author_username


@app.route("/api/qa/threads", methods=["GET"])
def api_qa_list_threads():
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "new")  # new | old
    conn = db_conn()
    sql = (
        "SELECT t.id, t.author_type, t.author_username, t.author_name, t.title, "
        "t.body, t.pinned, t.created_at, "
        "(SELECT COUNT(*) FROM qa_replies r WHERE r.thread_id=t.id AND r.deleted=0) AS replies "
        "FROM qa_threads t WHERE t.deleted=0"
    )
    params = []
    if q:
        sql += " AND (t.title LIKE ? OR t.body LIKE ?)"
        like = "%" + q + "%"
        params += [like, like]
    if sort == "old":
        sql += " ORDER BY t.pinned DESC, t.id ASC"
    else:
        sql += " ORDER BY t.pinned DESC, t.id DESC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["body"] = (d["body"] or "")[:160]  # 列表只显示摘要
        out.append(d)
    conn.close()
    return jsonify(ok=True, threads=out)


@app.route("/api/qa/threads", methods=["POST"])
def api_qa_create_thread():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    auth = _qa_author(user, data.get("anon_name"))
    if not auth:
        return jsonify(ok=False, error="匿名发言需填写昵称"), 400
    author_type, author_username, author_name = auth
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    if not title:
        return jsonify(ok=False, error="标题不能为空"), 400
    if not body:
        return jsonify(ok=False, error="内容不能为空"), 400
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO qa_threads(author_type, author_username, author_name, title, body) "
        "VALUES(?,?,?,?,?)",
        (author_type, author_username, author_name, title[:200], body[:5000]))
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=tid)


@app.route("/api/qa/threads/<int:tid>", methods=["GET"])
def api_qa_thread_detail(tid):
    conn = db_conn()
    t = conn.execute("SELECT * FROM qa_threads WHERE id=? AND deleted=0", (tid,)).fetchone()
    if not t:
        conn.close()
        return jsonify(ok=False, error="问题不存在"), 404
    rows = conn.execute(
        "SELECT * FROM qa_replies WHERE thread_id=? AND deleted=0 ORDER BY id ASC",
        (tid,)).fetchall()
    conn.close()
    nodes = {}
    for r in rows:
        d = dict(r)
        d["children"] = []
        nodes[d["id"]] = d
    roots = []
    for d in nodes.values():
        if d["parent_id"] and d["parent_id"] in nodes:
            nodes[d["parent_id"]]["children"].append(d)
        else:
            roots.append(d)
    return jsonify(ok=True, thread=dict(t), replies=roots)


@app.route("/api/qa/replies", methods=["POST"])
def api_qa_create_reply():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    auth = _qa_author(user, data.get("anon_name"))
    if not auth:
        return jsonify(ok=False, error="匿名发言需填写昵称"), 400
    author_type, author_username, author_name = auth
    try:
        thread_id = int(data.get("thread_id") or 0)
    except (ValueError, TypeError):
        return jsonify(ok=False, error="缺少问题 ID"), 400
    parent_id = data.get("parent_id")
    parent_id = int(parent_id) if parent_id else None
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify(ok=False, error="内容不能为空"), 400
    conn = db_conn()
    t = conn.execute("SELECT id FROM qa_threads WHERE id=? AND deleted=0",
                     (thread_id,)).fetchone()
    if not t:
        conn.close()
        return jsonify(ok=False, error="问题不存在"), 404
    if parent_id:
        p = conn.execute(
            "SELECT id FROM qa_replies WHERE id=? AND thread_id=? AND deleted=0",
            (parent_id, thread_id)).fetchone()
        if not p:
            conn.close()
            return jsonify(ok=False, error="父回复不存在"), 404
    cur = conn.execute(
        "INSERT INTO qa_replies(thread_id, parent_id, author_type, author_username, "
        "author_name, body) VALUES(?,?,?,?,?,?)",
        (thread_id, parent_id, author_type, author_username, author_name, body[:3000]))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=rid)


@app.route("/api/qa/threads/<int:tid>", methods=["DELETE"])
def api_qa_delete_thread(tid):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    t = conn.execute("SELECT * FROM qa_threads WHERE id=?", (tid,)).fetchone()
    if not t:
        conn.close()
        return jsonify(ok=False, error="问题不存在"), 404
    if not _can_delete_qa(user, t["author_username"]):
        conn.close()
        return jsonify(ok=False, error="无权限"), 403
    conn.execute("UPDATE qa_threads SET deleted=1 WHERE id=?", (tid,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


@app.route("/api/qa/replies/<int:rid>", methods=["DELETE"])
def api_qa_delete_reply(rid):
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    r = conn.execute("SELECT * FROM qa_replies WHERE id=?", (rid,)).fetchone()
    if not r:
        conn.close()
        return jsonify(ok=False, error="回复不存在"), 404
    if not _can_delete_qa(user, r["author_username"]):
        conn.close()
        return jsonify(ok=False, error="无权限"), 403
    conn.execute("UPDATE qa_replies SET deleted=1 WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify(ok=True)


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


@app.route("/api/admin/users", methods=["GET"])
def api_admin_list_users():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    if user["role"] == "admin":
        rows = conn.execute(
            "SELECT username, name, role, must_change_pw FROM users ORDER BY role, username"
        ).fetchall()
    else:
        # 助教/讲师仅可见学员账号，不泄露 staff 名单
        rows = conn.execute(
            "SELECT username, name, role, must_change_pw FROM users WHERE role='student' ORDER BY username"
        ).fetchall()
    conn.close()
    return jsonify(ok=True, rows=[dict(r) for r in rows])


@app.route("/api/admin/users", methods=["POST"])
def api_admin_create_user():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    role = (data.get("role") or "student").strip()
    must_change = int(bool(data.get("must_change_pw", 1)))
    if not re.match(r"^[A-Za-z0-9_]{2,32}$", username):
        return jsonify(ok=False, error="账号名仅限字母/数字/下划线，2-32位"), 400
    if len(password) < 4:
        return jsonify(ok=False, error="密码至少 4 位"), 400
    if role not in ("student", "ta", "instructor", "admin"):
        return jsonify(ok=False, error="角色非法"), 400
    # 角色创建白名单：调用者只能创建授权范围内的账号
    # admin 可建全部；讲师/助教仅可建学员（两者都只能建 student）
    _CREATEABLE = {
        "admin": ("student", "ta", "instructor", "admin"),
        "instructor": ("student",),
        "ta": ("student",),
    }
    if role not in _CREATEABLE.get(user["role"], ()):
        return jsonify(ok=False, error="无权创建该角色账号"), 403
    if not name:
        name = username
    conn = db_conn()
    exists = conn.execute("SELECT username FROM users WHERE username=?",
                          (username,)).fetchone()
    if exists:
        conn.close()
        return jsonify(ok=False, error="账号已存在"), 409
    salt = secrets.token_hex(16)
    conn.execute(
        "INSERT INTO users(username, name, role, password_hash, salt, must_change_pw) "
        "VALUES(?,?,?,?,?,?)",
        (username, name, role, _hash_pw(password, salt), salt, must_change))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM users WHERE username=?",
                             (username,)).fetchone())
    conn.close()
    return jsonify(ok=True, user=_public_user(row))


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
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
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


@app.route("/api/me/growth", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_me_growth():
    """学员成长总览：能力清单 + 本人勾选 + 各能力已得点数 + 总分。

    - 学员只能看自己；助教/总讲师/管理员可带 ?username= 看他人。
    - 用于支持学员通过 API 程序化查询自己的能力清单与蜗牛成长点数。
    """
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    target = user["username"]
    if user["role"] in ("ta", "instructor", "admin"):
        req_user = (request.args.get("username") or "").strip()
        if req_user:
            target = req_user
    t = conn.execute("SELECT username, name FROM users WHERE username=?",
                     (target,)).fetchone()
    if not t:
        conn.close()
        return jsonify(ok=False, error="用户不存在"), 404

    caps = conn.execute(
        "SELECT id, title, description, category, points "
        "FROM capabilities ORDER BY id").fetchall()
    checks = conn.execute(
        "SELECT cap_id, self, ta, final FROM checks "
        "WHERE student_username=?", (target,)).fetchall()
    chk_map = {r["cap_id"]: r for r in checks}
    earned = conn.execute(
        "SELECT ref_id, COALESCE(SUM(points),0) AS pts FROM points_log "
        "WHERE username=? AND source='capability' GROUP BY ref_id",
        (target,)).fetchall()
    earn_map = {r["ref_id"]: r["pts"] for r in earned}
    total_row = conn.execute(
        "SELECT COALESCE(SUM(points),0) AS total FROM points_log WHERE username=?",
        (target,)).fetchone()
    total = total_row["total"] if total_row else 0
    conn.close()

    out_caps = []
    for c in caps:
        ck = chk_map.get(c["id"])
        out_caps.append({
            "id": c["id"],
            "title": c["title"],
            "description": c["description"],
            "category": c["category"],
            "max_points": c["points"],
            "self": bool(ck["self"]) if ck else False,
            "ta": bool(ck["ta"]) if ck else False,
            "final": bool(ck["final"]) if ck else False,
            "earned_points": earn_map.get(c["id"], 0),
        })
    return jsonify(ok=True, username=target, name=t["name"],
                   total_points=total, capabilities=out_caps)


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
                 "points_log", "points_config", "assistant_assignments",
                 "qa_threads", "qa_replies"]
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


# ---------------------------------------------------------------- 访问分析：聚合 + 看板 + 报告
def _agg_summary(from_date=None, to_date=None):
    conn = db_conn()
    w1, p1 = _date_filter("login_at", from_date, to_date)
    logins = conn.execute("SELECT COUNT(*) n FROM login_events WHERE " + w1, p1).fetchone()["n"]
    rows = conn.execute(
        "SELECT login_at, logout_at, last_activity_at FROM login_events WHERE " + w1, p1).fetchall()
    durs = [_login_duration_sec(r) for r in rows]
    avg_dur = int(sum(durs) / len(durs)) if durs else 0
    w2, p2 = _date_filter("created_at", from_date, to_date)
    pv = conn.execute(
        "SELECT COUNT(*) n, COUNT(DISTINCT visitor_id) v, "
        "COALESCE(SUM(duration_sec),0) s FROM page_views WHERE " + w2, p2).fetchone()
    conn.close()
    return {"logins": logins, "avg_duration_sec": avg_dur,
            "pageviews": pv["n"], "unique_visitors": pv["v"],
            "total_dwell_sec": int(pv["s"])}


@app.route("/api/admin/analytics/summary", methods=["GET"])
def api_an_summary():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    return jsonify(ok=True, **_agg_summary(request.args.get("from"), request.args.get("to")))


@app.route("/api/admin/analytics/logins", methods=["GET"])
def api_an_logins():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    w, p = _date_filter("login_at", request.args.get("from"), request.args.get("to"))
    conn = db_conn()
    trend = conn.execute(
        "SELECT DATE(login_at) d, COUNT(*) n FROM login_events WHERE " + w
        + " GROUP BY d ORDER BY d", p).fetchall()
    detail = conn.execute(
        "SELECT username, ip, country, region, city, login_at, logout_at, "
        "last_activity_at FROM login_events WHERE " + w
        + " ORDER BY login_at DESC LIMIT 50", p).fetchall()
    conn.close()
    recent = [{"username": r["username"], "ip": r["ip"], "country": r["country"],
               "region": r["region"], "city": r["city"], "login_at": r["login_at"],
               "duration_sec": _login_duration_sec(r)} for r in detail]
    return jsonify(ok=True, trend=[dict(r) for r in trend], recent=recent)


@app.route("/api/admin/analytics/geo", methods=["GET"])
def api_an_geo():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    w, p = _date_filter("login_at", request.args.get("from"), request.args.get("to"))
    conn = db_conn()
    rows = conn.execute(
        "SELECT country, COUNT(*) n FROM login_events WHERE " + w
        + " GROUP BY country ORDER BY n DESC LIMIT 15", p).fetchall()
    conn.close()
    return jsonify(ok=True, geo=[dict(r) for r in rows])


@app.route("/api/admin/analytics/pages", methods=["GET"])
def api_an_pages():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    w, p = _date_filter("created_at", request.args.get("from"), request.args.get("to"))
    conn = db_conn()
    rows = conn.execute(
        "SELECT path, COUNT(*) views, COALESCE(SUM(duration_sec),0) total, "
        "COALESCE(AVG(duration_sec),0) avg FROM page_views WHERE " + w
        + " GROUP BY path ORDER BY total DESC LIMIT 15", p).fetchall()
    conn.close()
    return jsonify(ok=True, pages=[dict(r) for r in rows])


@app.route("/api/admin/analytics/extra", methods=["GET"])
def api_an_extra():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    f, t = request.args.get("from"), request.args.get("to")
    w1, p1 = _date_filter("login_at", f, t)
    w2, p2 = _date_filter("created_at", f, t)
    conn = db_conn()
    ua_rows = conn.execute("SELECT ua FROM login_events WHERE " + w1, p1).fetchall()
    dev_counter, br_counter = {}, {}
    for r in ua_rows:
        d, b = _parse_ua(r["ua"])
        dev_counter[d] = dev_counter.get(d, 0) + 1
        br_counter[b] = br_counter.get(b, 0) + 1
    ref_rows = conn.execute("SELECT referrer FROM page_views WHERE " + w2, p2).fetchall()
    ref_counter = {}
    for r in ref_rows:
        k = _classify_referrer(r["referrer"])
        ref_counter[k] = ref_counter.get(k, 0) + 1
    hrs = conn.execute(
        "SELECT strftime('%H', created_at) h, COUNT(*) n FROM page_views WHERE " + w2
        + " GROUP BY h", p2).fetchall()
    vis = conn.execute(
        "SELECT visitor_id, MIN(created_at) first FROM page_views GROUP BY visitor_id").fetchall()
    active = conn.execute(
        "SELECT DISTINCT visitor_id FROM page_views WHERE " + w2, p2).fetchall()
    active_set = {r["visitor_id"] for r in active}
    new_v = ret_v = 0
    for r in vis:
        if r["visitor_id"] not in active_set:
            continue
        if f and r["first"] >= f:
            new_v += 1
        else:
            ret_v += 1
    conn.close()
    return jsonify(ok=True, devices=dev_counter, browsers=br_counter,
                   referrers=ref_counter, hours=[dict(r) for r in hrs],
                   new_visitors=new_v, returning_visitors=ret_v)


def _build_report(range_type):
    today = datetime.date.today()
    if range_type == "daily":
        from_d = (today - datetime.timedelta(days=1)).isoformat()
        to_d = from_d
        title = "蜗牛AI 每日访问报告 · " + from_d
    else:
        from_d = (today - datetime.timedelta(days=7)).isoformat()
        to_d = (today - datetime.timedelta(days=1)).isoformat()
        title = "蜗牛AI 每周访问报告 · " + from_d + " ~ " + to_d
    s = _agg_summary(from_d, to_d)
    conn = db_conn()
    w1, p1 = _date_filter("login_at", from_d, to_d)
    geo = conn.execute(
        "SELECT country, COUNT(*) n FROM login_events WHERE " + w1
        + " GROUP BY country ORDER BY n DESC LIMIT 5", p1).fetchall()
    w2, p2 = _date_filter("created_at", from_d, to_d)
    pages = conn.execute(
        "SELECT path, COALESCE(SUM(duration_sec),0) total, COUNT(*) views "
        "FROM page_views WHERE " + w2 + " GROUP BY path ORDER BY total DESC LIMIT 5", p2).fetchall()
    conn.close()
    lines = ["> " + title, "",
             "> 🔑 登录人数：**%d**" % s["logins"],
             "> 👀 页面访问：**%d** 次（独立访客 %d）" % (s["pageviews"], s["unique_visitors"]),
             "> ⏱ 平均停留：**%s**" % _fmt_dur(s["avg_duration_sec"]), "",
             "**国家/地区 Top5**"]
    for r in geo:
        lines.append("- %s：%d" % (r["country"] or "未知", r["n"]))
    lines.append("")
    lines.append("**页面停留 Top5**")
    for r in pages:
        lines.append("- %s：%s（%d 次）" % (r["path"], _fmt_dur(int(r["total"])), r["views"]))
    return "\n".join(lines)


def _send_wechat(markdown_text):
    url = os.environ.get("WECHAT_WEBHOOK_URL")
    if not url:
        return False, "WECHAT_WEBHOOK_URL 未配置"
    try:
        r = requests.post(url, json={"msgtype": "markdown",
                                     "markdown": {"content": markdown_text}}, timeout=10)
        return r.ok, r.text
    except Exception as e:
        return False, str(e)


def _send_capability_congrats(markdown_text):
    """发送 AI 能力恭喜通知到学员群（专用 webhook）。
    优先读 CAPABILITY_WEBHOOK_URL；未配置时回退到 WECHAT_WEBHOOK_URL。"""
    url = os.environ.get("CAPABILITY_WEBHOOK_URL") or os.environ.get("WECHAT_WEBHOOK_URL")
    if not url:
        return False, "CAPABILITY_WEBHOOK_URL 未配置（请在 Render 控制台添加该变量）"
    try:
        r = requests.post(url, json={"msgtype": "markdown",
                                     "markdown": {"content": markdown_text}}, timeout=10)
        return r.ok, r.text
    except Exception as e:
        return False, str(e)


@app.route("/api/congrats/<username>", methods=["POST"])
def api_congrats(username):
    """助教/讲师/管理员：向学员群发送「恭喜获得 AI 能力」通知。
    自动汇总该学员 self=1 AND ta=1 的能力项，构造企业微信 markdown 消息。"""
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    t = conn.execute("SELECT name, role FROM users WHERE username=?",
                     (username,)).fetchone()
    if not t or t["role"] != "student":
        conn.close()
        return jsonify(ok=False, error="目标用户不是学员"), 404
    rows = conn.execute(
        "SELECT c.id, c.title FROM checks ck "
        "JOIN capabilities c ON c.id=ck.cap_id "
        "WHERE ck.student_username=? AND ck.self=1 AND ck.ta=1 ORDER BY c.id",
        (username,)).fetchall()
    conn.close()
    if not rows:
        return jsonify(ok=False, error="该学员暂无可恭喜的能力项（需自查与助教审核均通过）"), 400
    lines = ["恭喜🎉 **%s** 学员获得以下 AI 能力：" % (t["name"] or username)]
    for i, r in enumerate(rows, 1):
        lines.append("%d. %s" % (i, r["title"]))
    lines.append("继续努力哦😄！")
    content = "\n".join(lines)
    ok, msg = _send_capability_congrats(content)
    return jsonify(ok=ok, sent=ok, message=msg, content=content, count=len(rows))


@app.route("/api/admin/analytics/report", methods=["GET"])
def api_an_report():
    user = _current_user()
    if not _is_staff(user):
        return jsonify(ok=False, error="无权限"), 403
    rt = request.args.get("range", "daily")
    if rt not in ("daily", "weekly"):
        rt = "daily"
    text = _build_report(rt)
    ok, msg = _send_wechat(text)
    return jsonify(ok=True, sent=ok, message=msg, content=text)


_sched = BackgroundScheduler(timezone="Australia/Sydney")

def _start_scheduler():
    # gunicorn -w 4 多 worker：用文件锁保证仅一个进程启动定时任务，避免重复推送
    if os.environ.get("ANALYTICS_SCHEDULER_DISABLE") == "1":
        return
    lock_path = "/data/.scheduler.lock" if os.path.exists("/data") else "/tmp/.scheduler.lock"
    try:
        fd = open(lock_path, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    _sched.add_job(lambda: _send_wechat(_build_report("daily")),
                   "cron", hour=9, minute=0, id="daily_report")
    _sched.add_job(lambda: _send_wechat(_build_report("weekly")),
                   "cron", day_of_week="mon", hour=9, minute=0, id="weekly_report")
    _sched.start()


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
_start_scheduler()
print(f"[蜗牛AI Portal] 数据库: {DB_PATH}")
if not os.environ.get("WECHAT_WEBHOOK_URL"):
    print("[蜗牛AI Portal] ⚠️  警告：WECHAT_WEBHOOK_URL 未配置，日报/周报不会推送。"
          "请在 Render 控制台 → snailai-portal-1 → Environment 中添加该变量（值即企业微信 webhook 地址）。")

if __name__ == "__main__":
    print(f"[蜗牛AI Portal] 监听: http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
