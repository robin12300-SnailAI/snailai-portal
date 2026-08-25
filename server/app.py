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
capabilities(id PK, title, description, category, points, sort_order)
  sort_order INTEGER NULL — 显示顺序；NULL/0 时按 id 兜底，新增项追加到末尾
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
    CREATE TABLE IF NOT EXISTS congrats_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_username TEXT NOT NULL,
      granted_by TEXT NOT NULL,
      cap_count INTEGER NOT NULL DEFAULT 0,
      content TEXT,
      created_at TEXT DEFAULT (datetime('now'))
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
    CREATE TABLE IF NOT EXISTS quote_confirmations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      quote_id TEXT NOT NULL,
      client TEXT NOT NULL,
      selections TEXT NOT NULL,
      oneoff_total INTEGER DEFAULT 0,
      monthly_total INTEGER DEFAULT 0,
      deposit_total INTEGER DEFAULT 0,
      payment_schedule TEXT,
      confirmed_at TEXT DEFAULT (datetime('now')),
      email_sent INTEGER DEFAULT 0,
      confirmed_by TEXT
    );
    -- 签合同模块（Agreement Sign V1.0.0）
    CREATE TABLE IF NOT EXISTS agreements(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      agreement_no TEXT NOT NULL,
      rev TEXT NOT NULL,
      pdf_path TEXT NOT NULL,
      final_pdf_path TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS agreement_signers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      agreement_id INTEGER NOT NULL,
      role TEXT NOT NULL,
      name TEXT NOT NULL,
      email TEXT NOT NULL,
      signer_token TEXT UNIQUE NOT NULL,
      sign_rects TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      signed_name TEXT,
      signature_png_path TEXT,
      signed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS agreement_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      agreement_id INTEGER NOT NULL,
      signer_id INTEGER,
      event_type TEXT NOT NULL,
      detail TEXT,
      ip TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()

    # 迁移：为已存在的旧库补列（全新库已由 CREATE 含列，ALTER 会抛错被忽略）
    for sql in [
        "ALTER TABLE users ADD COLUMN must_change_pw INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN referrer TEXT",
        "ALTER TABLE capabilities ADD COLUMN points INTEGER DEFAULT 10",
        "ALTER TABLE capabilities ADD COLUMN sort_order INTEGER",
        "ALTER TABLE quote_confirmations ADD COLUMN confirmed_by TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN company_name TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN abn TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN address TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN contact_person TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN email TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN phone TEXT",
        "ALTER TABLE quote_confirmations ADD COLUMN gst_rate REAL DEFAULT 0.10",
        "ALTER TABLE quote_confirmations ADD COLUMN oneoff_gst INTEGER DEFAULT 0",
        "ALTER TABLE quote_confirmations ADD COLUMN oneoff_incl_gst INTEGER DEFAULT 0",
        "ALTER TABLE quote_confirmations ADD COLUMN monthly_gst INTEGER DEFAULT 0",
        "ALTER TABLE quote_confirmations ADD COLUMN monthly_incl_gst INTEGER DEFAULT 0",
        "ALTER TABLE quote_confirmations ADD COLUMN deposit_incl_gst INTEGER DEFAULT 0",
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
    # 客户账号保障：确保 customer 角色账号存在（幂等，每次启动执行，作用于已有生产库）
    _ensure_customer_accounts(c)
    # 管理员 robin 密码重置保障：仅当当前不是 12345 时重置（幂等，避免覆盖用户自改密码）
    _ensure_admin_pw(c)
    conn.commit()
    c.execute("SELECT COUNT(*) AS n FROM capabilities")
    if c.fetchone()["n"] == 0:
        _seed_capabilities(c)
    # 能力清单排序字段初始化：为尚无 sort_order 的记录按当前 id 顺序补 1..N，
    # 使排序迁移对现有数据无感（旧库首次部署后全部为 NULL，此处一次性补齐）。
    c.execute("SELECT COUNT(*) AS n FROM capabilities WHERE sort_order IS NULL")
    if c.fetchone()["n"] > 0:
        _rows = c.execute("SELECT id FROM capabilities ORDER BY id").fetchall()
        for _i, _r in enumerate(_rows, 1):
            c.execute("UPDATE capabilities SET sort_order=? WHERE id=?", (_i, _r["id"]))
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
        ("andrew", "Andrew Li", "customer", "success888", 0),
    ]
    for u in users:
        username, name, role, pw = u[0], u[1], u[2], u[3]
        mcp = u[4] if len(u) > 4 else 1
        salt = secrets.token_hex(16)
        c.execute(
            "INSERT OR IGNORE INTO users(username, name, role, password_hash, salt, must_change_pw) "
            "VALUES(?,?,?,?,?,?)",
            (username, name, role, _hash_pw(pw, salt), salt, mcp),
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


def _ensure_customer_accounts(c):
    """确保 customer 角色账号存在（幂等：每次服务启动都执行，对已有生产库生效）。
    已存在的账号不改动（保留用户可能已改的密码）；缺失的按初始密码创建。"""
    CUSTOMER_ACCOUNTS = {
        # username: (name, initial_password)
        "andrew": ("Andrew Li", "success888"),
    }
    for username, (name, pw) in CUSTOMER_ACCOUNTS.items():
        salt = secrets.token_hex(16)
        pw_hash = _hash_pw(pw, salt)
        c.execute(
            "INSERT OR IGNORE INTO users(username, name, role, password_hash, salt, must_change_pw) "
            "VALUES(?,?,'customer',?,?,0)",
            (username, name, pw_hash, salt),
        )


def _ensure_admin_pw(c):
    """幂等：仅在 robin 当前密码不是 12345 时重置为 12345。
    部署后首次启动生效；若 robin 已是 12345 或用户自行改过密码则不再覆盖，
    避免每次部署都强制改回 12345。"""
    cur = c.execute("SELECT password_hash, salt FROM users WHERE username='robin'")
    row = cur.fetchone()
    if not row:
        return
    if row["password_hash"] != _hash_pw("12345", row["salt"]):
        salt = secrets.token_hex(16)
        c.execute(
            "UPDATE users SET password_hash=?, salt=?, must_change_pw=0 WHERE username='robin'",
            (_hash_pw("12345", salt), salt),
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
    row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
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

# ===== 品牌邮件体系（V1.8.0） =====
# SMTP 登录账号：robin@snailai.ai（Google Workspace，已挂 esign@/quote@/admin@ 别名）
GMAIL_USER = os.environ.get("GMAIL_USER", "robin@snailai.ai")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
# 三个品牌发件身份（同域别名，send-as 已在 Gmail 注册，From 不再走个人 gmail.com）
FROM_ESIGN = os.environ.get("FROM_ESIGN", "SnailAI.AI e-Sign <esign@snailai.ai>")
FROM_QUOTE = os.environ.get("FROM_QUOTE", "SnailAI.AI Quote <quote@snailai.ai>")
FROM_ADMIN = os.environ.get("FROM_ADMIN", "SnailAI.AI Admin <admin@snailai.ai>")
# 系统通知收件人：Robin 个人 Gmail 兜底（不依赖 snailai.ai 域名投递状态）
QUOTE_NOTIFY_TO = os.environ.get("QUOTE_NOTIFY_TO", "robin12300@gmail.com")
QUOTE_NOTIFY_CC = os.environ.get("QUOTE_NOTIFY_CC", "")
QUOTE_ADMIN_TOKEN = os.environ.get("QUOTE_ADMIN_TOKEN", "")  # 非空才启用管理清理接口

# 一次性确认豁免名单：这些用户即使已确认报价，仍可登录查看（如 demo 测试账号、内部复核账号）
# 环境变量 QUOTE_LOGIN_EXEMPT 逗号分隔，默认 {"demo"}
_QUOTE_EXEMPT_RAW = os.environ.get("QUOTE_LOGIN_EXEMPT", "demo")
QUOTE_LOGIN_EXEMPT = {u.strip().lower() for u in _QUOTE_EXEMPT_RAW.split(",") if u.strip()}


def _fmt_aud(n):
    try:
        return "${:,.2f}".format(float(n))
    except (TypeError, ValueError):
        return "$0"


def _esc(s):
    """HTML 转义。"""
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_quote_email_html(data, confirmed_by):
    """构建报价确认通知邮件的 HTML 正文。"""
    sel = data.get("selections", []) or []
    ci_company = data.get("companyName", "")
    ci_abn = data.get("abn", "")
    ci_addr = data.get("address", "")
    ci_contact = data.get("contactPerson", "")
    ci_email = data.get("email", "")
    ci_phone = data.get("phone", "")
    oneoff_total = data.get("oneoffTotal", 0)
    monthly_total = data.get("monthlyTotal", 0)
    deposit_total = data.get("depositTotal", 0)

    rows = ""
    for it in sel:
        nm = it.get("name", "")
        if isinstance(nm, dict):
            nm = nm.get("en") or nm.get("zh") or ""
        price = it.get("price", 0)
        typ = it.get("type", "oneoff")
        price_str = _fmt_aud(price) + ("/mo" if typ == "monthly" else "")
        rows += (
            '<tr>'
            '<td style="padding:6px 10px;border-bottom:1px solid #eee;">{}</td>'
            '<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{}</td>'
            '</tr>'
        ).format(_esc(nm), _esc(price_str))

    schedule_rows = ""
    for sc in data.get("paymentSchedule", []) or []:
        nm = sc.get("name", "")
        price = sc.get("price", 0)
        if sc.get("type") == "304030":
            parts = "30% {} / 40% {} / 30% {}".format(
                _fmt_aud(sc.get("p30", 0)), _fmt_aud(sc.get("p40", 0)), _fmt_aud(sc.get("p30b", 0)))
        else:
            parts = "50% {} / 50% {}".format(
                _fmt_aud(sc.get("p50a", 0)), _fmt_aud(sc.get("p50b", 0)))
        schedule_rows += (
            '<tr>'
            '<td style="padding:6px 10px;border-bottom:1px solid #eee;">{}</td>'
            '<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{}</td>'
            '<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">{}</td>'
            '</tr>'
        ).format(_esc(nm), _esc(_fmt_aud(price)), _esc(parts))

    gst_rate = data.get("gstRate", 0.10)
    oneoff_gst = data.get("oneoffGst", 0)
    oneoff_incl = data.get("oneoffInclGst", 0)
    monthly_gst = data.get("monthlyGst", 0)
    monthly_incl = data.get("monthlyInclGst", 0)

    html = """<!DOCTYPE html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#1A1A2E;max-width:640px;margin:0 auto;">
<h2 style="color:#FF5B1F;border-bottom:2px solid #FF5B1F;padding-bottom:6px;">SnailAI.AI — Quotation Confirmation</h2>
<p>Quotation <b>{quote_id}</b> has been confirmed by the client.</p>

<h3 style="color:#2A2A40;margin-bottom:4px;">Client Information</h3>
<table style="border-collapse:collapse;font-size:13px;margin-bottom:18px;">
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Company</td><td style="padding:3px 0;"><b>{company}</b></td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">ABN</td><td style="padding:3px 0;">{abn}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Address</td><td style="padding:3px 0;">{addr}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Contact</td><td style="padding:3px 0;">{contact}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Email</td><td style="padding:3px 0;">{email}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Phone</td><td style="padding:3px 0;">{phone}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Confirmed by</td><td style="padding:3px 0;">{confirmed_by}</td></tr>
<tr><td style="padding:3px 10px 3px 0;color:#6A6A85;">Confirmed at</td><td style="padding:3px 0;">{ts}</td></tr>
</table>

<h3 style="color:#2A2A40;margin-bottom:4px;">Selected Modules</h3>
<table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:8px;">
<tr style="background:#F5F4EE;"><th style="padding:8px 10px;text-align:left;">Module</th><th style="padding:8px 10px;text-align:right;">Price (ex GST)</th></tr>
{rows}
</table>
<table style="border-collapse:collapse;font-size:13px;margin-bottom:18px;">
<tr><td style="padding:4px 10px 4px 0;">One-off total (ex GST)</td><td style="padding:4px 0;text-align:right;"><b>{oneoff}</b></td></tr>
<tr><td style="padding:4px 10px 4px 0;">One-off GST ({gst_pct}%)</td><td style="padding:4px 0;text-align:right;">{oneoff_gst}</td></tr>
<tr><td style="padding:4px 10px 4px 0;">One-off total (incl GST)</td><td style="padding:4px 0;text-align:right;"><b>{oneoff_incl}</b></td></tr>
<tr><td style="padding:4px 10px 4px 0;">Monthly total (ex GST)</td><td style="padding:4px 0;text-align:right;"><b>{monthly}</b></td></tr>
<tr><td style="padding:4px 10px 4px 0;">Monthly GST</td><td style="padding:4px 0;text-align:right;">{monthly_gst}</td></tr>
<tr><td style="padding:4px 10px 4px 0;">Monthly total (incl GST)</td><td style="padding:4px 0;text-align:right;"><b>{monthly_incl}</b></td></tr>
</table>

<h3 style="color:#2A2A40;margin-bottom:4px;">Payment Schedule</h3>
<table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:8px;">
<tr style="background:#F5F4EE;"><th style="padding:8px 10px;text-align:left;">Module</th><th style="padding:8px 10px;text-align:right;">Price</th><th style="padding:8px 10px;text-align:right;">Milestones (ex GST)</th></tr>
{schedule_rows}
</table>
<p style="font-size:13px;">Commencement deposit due (ex GST): <b>{deposit}</b></p>

<p style="font-size:12px;color:#6A6A85;margin-top:24px;border-top:1px solid #eee;padding-top:10px;">
This is an automated confirmation from the SnailAI.AI quotation system. Please keep this email for your records.<br>
Sent {sent_at}
</p>
</body></html>""".format(
        quote_id=_esc(data.get("quoteId", "")),
        company=_esc(ci_company), abn=_esc(ci_abn), addr=_esc(ci_addr),
        contact=_esc(ci_contact), email=_esc(ci_email), phone=_esc(ci_phone),
        confirmed_by=_esc(confirmed_by or "client"),
        ts=_esc(str(data.get("timestamp", ""))),
        rows=rows, schedule_rows=schedule_rows,
        oneoff=_fmt_aud(oneoff_total), monthly=_fmt_aud(monthly_total),
        deposit=_fmt_aud(deposit_total),
        gst_pct=int(round(float(gst_rate) * 100)),
        oneoff_gst=_fmt_aud(oneoff_gst), oneoff_incl=_fmt_aud(oneoff_incl),
        monthly_gst=_fmt_aud(monthly_gst), monthly_incl=_fmt_aud(monthly_incl),
        sent_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return html


def _send_quote_email(data, confirmed_by):
    """通过 Gmail SMTP 发送报价确认通知。失败只记日志，不影响确认接口。
    收件：robin@snailai.ai（To）+ robin12300@gmail.com（Cc）+ 客户自己填写的邮箱（Cc，留档）。"""
    if not GMAIL_APP_PASSWORD:
        app.logger.info("[quote-email] GMAIL_APP_PASSWORD not set; skip notification")
        return False
    import re
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject = "Quotation {} confirmed — {} (one-off {})".format(
        data.get("quoteId", "quote"), data.get("companyName", "client"),
        _fmt_aud(data.get("oneoffTotal", 0)))

    # 客户邮箱：格式校验 + 去重（避免与已有收件人重复）
    client_email = (data.get("email") or "").strip()
    if client_email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", client_email):
        client_email = ""
    cc_list = [QUOTE_NOTIFY_CC] if QUOTE_NOTIFY_CC else []
    if client_email:
        known = {QUOTE_NOTIFY_TO.lower()} | {c.lower() for c in cc_list}
        if client_email.lower() not in known:
            cc_list.append(client_email)

    html_body = _build_quote_email_html(data, confirmed_by)
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = FROM_QUOTE
    msg["To"] = QUOTE_NOTIFY_TO
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_html_to_text(html_body), "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as srv:
            srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            recipients = [QUOTE_NOTIFY_TO] + cc_list
            srv.sendmail(GMAIL_USER, recipients, msg.as_string())
        app.logger.info("[quote-email] sent to %s cc %s", QUOTE_NOTIFY_TO, ", ".join(cc_list))
        return True
    except Exception as e:  # noqa: BLE001
        app.logger.warning("[quote-email] send failed: %s", e)
        return False


@app.route("/api/quote/confirm", methods=["POST"])
def api_quote_confirm():
    """Andrew 报价确认 — 存 SQLite 留底（邮件待配密码后补充）。
    若请求带有效 session token，则记录确认人身份（confirmed_by）。"""
    # 可选身份校验：登录 token → username
    confirmed_by = None
    token = _token_from_req()
    if token:
        sess = _get_session(token)
        if sess:
            confirmed_by = sess.get("username")
    data = request.get_json(silent=True) or {}
    quote_id = data.get("quoteId", "")
    client = data.get("client", "")

    # --- 幂等锁：非豁免账号已有确认记录则拒绝（防止 API 绕过重复提交）---
    if confirmed_by and confirmed_by.lower() not in QUOTE_LOGIN_EXEMPT:
        conn_chk = db_conn()
        dup = conn_chk.execute(
            "SELECT 1 FROM quote_confirmations WHERE confirmed_by = ? LIMIT 1",
            (confirmed_by,)).fetchone()
        conn_chk.close()
        if dup:
            return jsonify({"ok": False, "error": "already_confirmed"}), 409

    selections = json.dumps(data.get("selections", []), ensure_ascii=False)
    oneoff_total = data.get("oneoffTotal", 0)
    monthly_total = data.get("monthlyTotal", 0)
    deposit_total = data.get("depositTotal", 0)
    payment_schedule = json.dumps(data.get("paymentSchedule", []), ensure_ascii=False)
    ts = data.get("timestamp") or datetime.datetime.utcnow().isoformat()

    conn = db_conn()
    conn.execute(
        "INSERT INTO quote_confirmations(quote_id, client, selections, oneoff_total, monthly_total, deposit_total, payment_schedule, confirmed_at, confirmed_by, company_name, abn, address, contact_person, email, phone, gst_rate, oneoff_gst, oneoff_incl_gst, monthly_gst, monthly_incl_gst, deposit_incl_gst) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (quote_id, client, selections, oneoff_total, monthly_total, deposit_total, payment_schedule, ts, confirmed_by,
         data.get("companyName",""), data.get("abn",""), data.get("address",""),
         data.get("contactPerson",""), data.get("email",""), data.get("phone",""),
         data.get("gstRate",0.10), data.get("oneoffGst",0), data.get("oneoffInclGst",0),
         data.get("monthlyGst",0), data.get("monthlyInclGst",0), data.get("depositInclGst",0)),
    )
    conn.commit()
    # --- 确认后踢下线：删除该用户所有活跃 session，防止刷新页面继续操作 ---
    if confirmed_by:
        try:
            conn.execute("DELETE FROM sessions WHERE username = ?", (confirmed_by,))
            conn.commit()
        except Exception:
            pass
    conn.close()

    # 邮件通知（失败不影响确认结果）
    try:
        _send_quote_email(data, confirmed_by)
    except Exception as e:  # noqa: BLE001
        app.logger.warning("[quote-email] unexpected error: %s", e)

    return jsonify({"ok": True, "quoteId": quote_id})


# ===== 签合同模块 API（Agreement Sign V1.0.0） =====
AGREEMENTS_DIR = Path("/data/agreements") if os.path.exists("/data") else Path(SERVER_DIR / "agreements")
AGREEMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _html_to_text(html):
    """HTML 邮件降级为纯文本（反垃圾：提供 text/plain 备用部分）。"""
    import re as _re
    txt = _re.sub(r"<br\s*/?>", "\n", html, flags=_re.I)
    txt = _re.sub(r"</p>", "\n\n", txt, flags=_re.I)
    txt = _re.sub(r"<[^>]+>", "", txt)
    txt = txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return _re.sub(r"\n{3,}", "\n\n", txt).strip()


def _send_sign_email(to_addr, subject, html_body, attachments=None, from_addr=None, text_body=None):
    """通用邮件发送。attachments = [(filename, bytes), ...]
    V1.8.0: 品牌发件身份（默认 e-Sign）+ 纯文本备用部分 + PDF 附件正确 Content-Type。"""
    if not GMAIL_APP_PASSWORD:
        app.logger.info("[sign-email] GMAIL_APP_PASSWORD not set; skip")
        return False
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_addr or FROM_ESIGN
    msg["To"] = to_addr

    # text/plain + text/html 双部分（单一 HTML 是垃圾过滤器扣分项）
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body or _html_to_text(html_body), "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt)

    if attachments:
        for fname, fbytes in attachments:
            if str(fname).lower().endswith(".pdf"):
                part = MIMEBase("application", "pdf")
            else:
                part = MIMEBase("application", "octet-stream")
            part.set_payload(fbytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=fname)
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as srv:
            srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            srv.sendmail(GMAIL_USER, [to_addr], msg.as_string())
        app.logger.info("[sign-email] sent to %s from %s", to_addr, from_addr or FROM_ESIGN)
        return True
    except Exception as e:
        app.logger.warning("[sign-email] send failed: %s", e)
        return False


def _embed_signature(pdf_path, sig_png_path, sign_rects, signed_name, signed_at_str):
    """用 PyMuPDF 把签名图 + 打印名 + 日期嵌入 PDF 指定页的指定坐标。
    sign_rects 格式: {"page":N, "signature":[x0,y0,x1,y1], "name":[x0,y0,x1,y1], "date":[x0,y0,x1,y1]}
    坐标为 PDF pt 坐标系（原点左下角）。
    返回修改后的 PDF bytes。"""
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[sign_rects["page"] - 1]  # 0-indexed

    # 嵌入签名图（等比缩放居中，3% 内边距）
    sig_rect = sign_rects.get("signature")
    if sig_rect and sig_png_path and os.path.exists(sig_png_path):
        r = fitz.Rect(sig_rect)
        # 计算内边距后的安全区
        margin_x = (r.x1 - r.x0) * 0.03
        margin_y = (r.y1 - r.y0) * 0.03
        safe = fitz.Rect(r.x0 + margin_x, r.y0 + margin_y, r.x1 - margin_x, r.y1 - margin_y)
        page.insert_image(safe, filename=sig_png_path, keep_proportion=True)

    # 嵌入打印名
    name_rect = sign_rects.get("name")
    if name_rect and signed_name:
        r = fitz.Rect(name_rect)
        fontsize = min(11, (r.y1 - r.y0) * 0.8)
        page.insert_text(
            fitz.Point(r.x0, r.y1 - (r.y1 - r.y0) * 0.15),
            signed_name, fontsize=fontsize, fontname="helv", color=(0.1, 0.1, 0.18)
        )

    # 嵌入日期
    date_rect = sign_rects.get("date")
    if date_rect and signed_at_str:
        r = fitz.Rect(date_rect)
        fontsize = min(10, (r.y1 - r.y0) * 0.8)
        page.insert_text(
            fitz.Point(r.x0, r.y1 - (r.y1 - r.y0) * 0.15),
            signed_at_str, fontsize=fontsize, fontname="helv", color=(0.1, 0.1, 0.18)
        )

    # 写出到 bytes
    import io
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@app.route("/api/sign/admin/create", methods=["POST"])
def api_sign_admin_create():
    """创建合同并发会签邀请邮件。需 X-Admin-Token。
    body: {title, agreement_no, rev, pdf_base64, notify:bool, parties: [{role,name,email,sign_rects:{page,signature,name,date}}]}"""
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify(ok=False, error="unauthorised"), 401
    data = request.get_json(silent=True) or {}
    import base64

    # 校验必填
    title = data.get("title", "").strip()
    agreement_no = data.get("agreement_no", "").strip()
    rev = data.get("rev", "").strip()
    pdf_b64 = data.get("pdf_base64", "").strip()
    parties = data.get("parties", [])
    notify = data.get("notify", False)
    if not title or not agreement_no or not pdf_b64 or len(parties) < 1:
        return jsonify(ok=False, error="missing required fields"), 400

    # 解码 PDF
    try:
        pdf_bytes = base64.b64decode(pdf_b64)
    except Exception:
        return jsonify(ok=False, error="invalid pdf_base64"), 400
    if not pdf_bytes[:5] == b"%PDF-":
        return jsonify(ok=False, error="not a PDF file"), 400

    agreement_token = secrets.token_urlsafe(24)
    now = datetime.datetime.utcnow().isoformat()

    conn = db_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO agreements(token, title, agreement_no, rev, pdf_path, status, created_at) VALUES(?,?,?,?,?,?,?)",
            (agreement_token, title, agreement_no, rev, "", "active", now),
        )
        aid = c.lastrowid

        # 存 PDF 文件
        agr_dir = AGREEMENTS_DIR / str(aid)
        agr_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = agr_dir / "original.pdf"
        pdf_path.write_bytes(pdf_bytes)
        conn.execute("UPDATE agreements SET pdf_path=? WHERE id=?", (str(pdf_path), aid))

        signers_result = []
        for p in parties:
            signer_token = secrets.token_urlsafe(24)
            rects = p.get("sign_rects", {})
            c.execute(
                "INSERT INTO agreement_signers(agreement_id, role, name, email, signer_token, sign_rects, status) VALUES(?,?,?,?,?,?,?)",
                (aid, p.get("role", "client"), p.get("name", ""), p.get("email", ""),
                 signer_token, json.dumps(rects), "pending"),
            )
            sid = c.lastrowid
            base_url = os.environ.get("RENDER_BASE_URL", "https://snailai.ai")
            sign_url = "{}/sign/{}".format(base_url.rstrip("/"), signer_token)
            signers_result.append({
                "role": p.get("role", "client"),
                "name": p.get("name", ""),
                "email": p.get("email", ""),
                "url": sign_url,
                "signer_token": signer_token,
            })

        conn.commit()

        # 发会签邀请邮件
        if notify and GMAIL_APP_PASSWORD:
            invite_ts = datetime.datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
            for sr in signers_result:
                html = (
                    '<div style="font-family:Inter,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px">'
                    '<div style="background:#1A1A2E;padding:16px;border-radius:8px 8px 0 0">'
                    '<span style="color:#D4A547;font-size:20px;font-weight:500">Snail</span>'
                    '<span style="color:#FF5B1F;font-size:20px;font-weight:500">AI</span>'
                    '<span style="color:#fff;font-size:20px;font-weight:500">.AI e-Sign</span></div>'
                    '<div style="padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px">'
                    '<p style="font-size:15px;color:#1A1A2E">Hello {name},</p>'
                    '<p style="font-size:14px;color:#444">Agreement <strong>{no}</strong> ({rev}) is ready for your signature.</p>'
                    '<p style="font-size:14px;color:#444">Click below to review the agreement and sign online:</p>'
                    '<a href="{url}" style="display:inline-block;background:#FF5B1F;color:#fff;padding:12px 24px;'
                    'border-radius:8px;text-decoration:none;font-size:14px;font-weight:500;margin:12px 0">'
                    'Review &amp; Sign</a>'
                    '<p style="font-size:13px;color:#555;word-break:break-all;margin-top:14px">'
                    'If the button does not work, copy and open this link in your browser:<br>'
                    '<span style="color:#1A1A2E">{url}</span></p>'
                    '<p style="font-size:12px;color:#888;margin-top:16px">'
                    'You can also share the draft with relevant parties for review before signing.</p>'
                    '<p style="font-size:11px;color:#aaa;margin-top:12px">Sent: {ts} &middot; Ref: {ref}</p>'
                    '<p style="font-size:12px;color:#888">SnailAI.AI e-Sign — powered by our own e-signature engine</p>'
                    '</div></div>'
                ).format(name=_esc(sr["name"]), no=_esc(agreement_no), rev=_esc(rev),
                         url=sr["url"], ts=invite_ts, ref=sr["signer_token"][:8])
                text_body = (
                    "Hello {name},\n\n"
                    "Agreement {no} ({rev}) is ready for your signature.\n\n"
                    "Open the link below to review and sign online:\n{url}\n\n"
                    "Sent: {ts} UTC / Ref: {ref}\n\n"
                    "SnailAI.AI e-Sign"
                ).format(name=sr["name"], no=agreement_no, rev=rev, url=sr["url"],
                         ts=invite_ts, ref=sr["signer_token"][:8])
                subject = "Agreement {} ({}) is ready for your signature".format(agreement_no, rev)
                try:
                    _send_sign_email(sr["email"], subject, html, text_body=text_body)
                except Exception as e:
                    app.logger.warning("[sign-email] invite failed for %s: %s", sr["email"], e)

        return jsonify(ok=True, agreement_token=agreement_token, signers=signers_result)
    except Exception as e:
        conn.rollback()
        app.logger.error("[sign-create] error: %s", e)
        return jsonify(ok=False, error=str(e)), 500
    finally:
        conn.close()


@app.route("/api/portal/admin/send-portal-email", methods=["POST"])
def api_portal_send_email():
    """V1.8.0: Portal 启用邮件 — 合同签订后向客户发送 Portal 登录网址/账号/密码。
    发件身份 admin@snailai.ai。管理员登录态保护；含明文密码，由管理员核对邮箱后手动发送。"""
    user = _current_user()
    if not user or user.get("role") != "admin":
        return jsonify(ok=False, error="无权限"), 403
    import re as _re
    data = request.get_json(silent=True) or {}
    to_email = (data.get("email") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    portal_url = (data.get("portalUrl") or "").strip() or "https://snailai.ai/login.html"
    if not to_email or not _re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", to_email):
        return jsonify(ok=False, error="客户邮箱格式不正确"), 400
    if not username or not password:
        return jsonify(ok=False, error="账号与密码不能为空"), 400

    subject = "Your SnailAI.AI Portal account is ready"
    html = (
        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px">'
        '<div style="background:#1A1A2E;padding:16px;border-radius:8px 8px 0 0">'
        '<span style="color:#D4A547;font-size:20px;font-weight:500">Snail</span>'
        '<span style="color:#FF5B1F;font-size:20px;font-weight:500">AI</span>'
        '<span style="color:#fff;font-size:20px;font-weight:500">.AI Portal</span></div>'
        '<div style="padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px">'
        '<p style="font-size:15px;color:#1A1A2E">Hello,</p>'
        '<p style="font-size:14px;color:#444">Your agreement with SnailAI.AI is fully signed. '
        'Your client Portal account is now active:</p>'
        '<table style="font-size:14px;color:#1A1A2E;border-collapse:collapse;margin:14px 0">'
        '<tr><td style="padding:6px 12px 6px 0;color:#888">Portal 登录网址 / URL</td>'
        '<td style="padding:6px 0;word-break:break-all"><a href="{url}" style="color:#FF5B1F">{url}</a></td></tr>'
        '<tr><td style="padding:6px 12px 6px 0;color:#888">账号 / Username</td>'
        '<td style="padding:6px 0"><strong>{user}</strong></td></tr>'
        '<tr><td style="padding:6px 12px 6px 0;color:#888">密码 / Password</td>'
        '<td style="padding:6px 0"><strong>{pw}</strong></td></tr></table>'
        '<p style="font-size:14px;color:#444">三步开始使用 / How to start:</p>'
        '<ol style="font-size:13.5px;color:#444;padding-left:20px;line-height:1.9">'
        '<li>打开上方链接，用账号和密码登录 / Open the link above and sign in</li>'
        '<li>首次登录请及时修改密码 / Change your password on first login</li>'
        '<li>在 Portal 内查看您的报价与项目进度 / View your quotation and project progress</li>'
        '</ol>'
        '<p style="font-size:12px;color:#888;margin-top:16px">SnailAI.AI Admin — this message was sent '
        'via your account activation request</p>'
        '</div></div>'
    ).format(url=_esc(portal_url), user=_esc(username), pw=_esc(password))
    text_body = (
        "Hello,\n\n"
        "Your agreement with SnailAI.AI is fully signed. Your client Portal account is now active:\n\n"
        "Portal URL: {url}\nUsername: {user}\nPassword: {pw}\n\n"
        "How to start:\n"
        "1. Open the link above and sign in\n"
        "2. Change your password on first login\n"
        "3. View your quotation and project progress\n\n"
        "SnailAI.AI Admin"
    ).format(url=portal_url, user=username, pw=password)

    sent = _send_sign_email(to_email, subject, html, from_addr=FROM_ADMIN, text_body=text_body)
    if not sent:
        return jsonify(ok=False, error="邮件发送失败，请稍后重试或检查 SMTP 配置"), 500
    app.logger.info("[portal-email] onboarding email sent to %s (user=%s)", to_email, username)
    return jsonify(ok=True, to=to_email, username=username)


@app.route("/api/sign/admin/cleanup", methods=["POST"])
def api_sign_admin_cleanup():
    """删除测试合同数据（交付前清场用）。需 X-Admin-Token。"""
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify(ok=False, error="unauthorised"), 401
    import shutil
    conn = db_conn()
    try:
        # 列出要清理的文件目录
        rows = conn.execute("SELECT id FROM agreements").fetchall()
        for r in rows:
            d = AGREEMENTS_DIR / str(r["id"])
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        before = conn.execute("SELECT COUNT(*) FROM agreements").fetchone()[0]
        conn.execute("DELETE FROM agreement_events")
        conn.execute("DELETE FROM agreement_signers")
        conn.execute("DELETE FROM agreements")
        conn.commit()
        return jsonify(ok=True, deleted=before)
    finally:
        conn.close()


@app.route("/api/sign/admin/lookup", methods=["POST"])
def api_sign_admin_lookup():
    """用 signer_token 查 agreement_id + 关键元数据（供 Portal/Admin 关联用）。需 X-Admin-Token。"""
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify(ok=False, error="unauthorised"), 401
    data = request.get_json(silent=True) or {}
    signer_token = (data.get("signer_token") or "").strip()
    if not signer_token:
        return jsonify(ok=False, error="signer_token required"), 400
    conn = db_conn()
    try:
        signer = conn.execute(
            "SELECT s.agreement_id, s.role, s.name, s.email, s.status AS signer_status, "
            "a.agreement_no, a.rev, a.title, a.status AS agr_status "
            "FROM agreement_signers s JOIN agreements a ON s.agreement_id=a.id "
            "WHERE s.signer_token=?", (signer_token,)
        ).fetchone()
        if not signer:
            return jsonify(ok=False, error="not found"), 404
        return jsonify(ok=True, **dict(signer))
    finally:
        conn.close()


@app.route("/api/sign/info/<signer_token>", methods=["GET"])
def api_sign_info(signer_token):
    """签署方查看合同信息。"""
    conn = db_conn()
    try:
        signer = conn.execute(
            "SELECT s.*, a.title, a.agreement_no, a.rev, a.status AS agr_status, a.final_pdf_path "
            "FROM agreement_signers s JOIN agreements a ON s.agreement_id=a.id "
            "WHERE s.signer_token=?", (signer_token,)
        ).fetchone()
        if not signer:
            return jsonify(ok=False, error="not found"), 404

        # 所有签署方状态
        all_signers = conn.execute(
            "SELECT role, name, status, signed_at FROM agreement_signers WHERE agreement_id=?",
            (signer["agreement_id"],)
        ).fetchall()
        parties = []
        for s in all_signers:
            parties.append({
                "role": s["role"], "name": s["name"],
                "status": s["status"],
                "signed_at": s["signed_at"],
            })

        # 记录查看事件
        conn.execute(
            "INSERT INTO agreement_events(agreement_id, signer_id, event_type, ip, created_at) VALUES(?,?,?,?,?)",
            (signer["agreement_id"], signer["id"], "viewed", _client_ip(), datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()

        return jsonify(ok=True, data={
            "title": signer["title"],
            "agreement_no": signer["agreement_no"],
            "rev": signer["rev"],
            "agr_status": signer["agr_status"],
            "my_role": signer["role"],
            "my_name": signer["name"],
            "my_email": signer["email"],
            "my_status": signer["status"],
            "signed_name": signer["signed_name"],
            "signed_at": signer["signed_at"],
            "parties": parties,
            "finalized": signer["agr_status"] == "finalized",
        })
    finally:
        conn.close()


@app.route("/api/sign/pdf/<signer_token>", methods=["GET"])
def api_sign_pdf(signer_token):
    """返回合同 PDF 文件流：finalized 后返回最终版，否则原始版。"""
    conn = db_conn()
    try:
        signer = conn.execute(
            "SELECT s.agreement_id, a.pdf_path, a.final_pdf_path, a.status AS agr_status "
            "FROM agreement_signers s JOIN agreements a ON s.agreement_id=a.id "
            "WHERE s.signer_token=?", (signer_token,)
        ).fetchone()
        if not signer:
            return jsonify(ok=False, error="not found"), 404

        pdf_path = signer["final_pdf_path"] if signer["agr_status"] == "finalized" and signer["final_pdf_path"] else signer["pdf_path"]
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify(ok=False, error="PDF not found"), 404

        from flask import send_file
        return send_file(pdf_path, mimetype="application/pdf", as_attachment=False)
    finally:
        conn.close()


@app.route("/api/sign/share/<signer_token>", methods=["POST"])
@_rate_limit_deco(10, 3600, by_user=False)
def api_sign_share(signer_token):
    """把未签署的合同 PDF 草稿作为附件发给指定邮箱。"""
    conn = db_conn()
    try:
        signer = conn.execute(
            "SELECT s.*, a.title, a.agreement_no, a.rev, a.pdf_path "
            "FROM agreement_signers s JOIN agreements a ON s.agreement_id=a.id "
            "WHERE s.signer_token=?", (signer_token,)
        ).fetchone()
        if not signer:
            return jsonify(ok=False, error="not found"), 404

        data = request.get_json(silent=True) or {}
        emails = data.get("emails", [])
        # 校验 + 去重
        valid = []
        seen = set()
        for e in emails:
            e = e.strip().lower()
            if e and re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", e) and e not in seen:
                valid.append(e)
                seen.add(e)
        if not valid:
            return jsonify(ok=False, error="no valid emails"), 400
        if len(valid) > 10:
            return jsonify(ok=False, error="max 10 recipients at once"), 400

        pdf_path = signer["pdf_path"]
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify(ok=False, error="PDF not found"), 404

        pdf_bytes = Path(pdf_path).read_bytes()
        fname = "{}-{}-Draft.pdf".format(signer["agreement_no"], signer["rev"].replace(" ", ""))

        subject = "Draft of Agreement {} ({}) shared for review".format(
            signer["agreement_no"], signer["rev"])
        for to_addr in valid:
            html = (
                '<div style="font-family:Inter,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px">'
                '<div style="background:#1A1A2E;padding:16px;border-radius:8px 8px 0 0">'
                '<span style="color:#D4A547;font-size:20px;font-weight:500">Snail</span>'
                '<span style="color:#FF5B1F;font-size:20px;font-weight:500">AI</span>'
                '<span style="color:#fff;font-size:20px;font-weight:500">.AI e-Sign</span></div>'
                '<div style="padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px">'
                '<p style="font-size:14px;color:#444">{sharer} has shared the draft of Agreement '
                '<strong>{no}</strong> ({rev}) with you for review.</p>'
                '<p style="font-size:12px;color:#888;margin-top:16px">The unsigned draft PDF is attached. '
                'Please review and contact the sender with any questions.</p>'
                '<p style="font-size:12px;color:#888">SnailAI.AI e-Sign</p>'
                '</div></div>'
            ).format(sharer=_esc(signer["name"]), no=_esc(signer["agreement_no"]), rev=_esc(signer["rev"]))
            try:
                _send_sign_email(to_addr, subject, html, attachments=[(fname, pdf_bytes)])
            except Exception as e:
                app.logger.warning("[sign-email] share failed for %s: %s", to_addr, e)

        # 记录事件
        conn.execute(
            "INSERT INTO agreement_events(agreement_id, signer_id, event_type, detail, ip, created_at) VALUES(?,?,?,?,?,?)",
            (signer["agreement_id"], signer["id"], "draft_shared",
             "sent to {} recipients".format(len(valid)), _client_ip(), datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()
        return jsonify(ok=True, sent_to=valid)
    finally:
        conn.close()


@app.route("/api/sign/sign/<signer_token>", methods=["POST"])
@_rate_limit_deco(5, 60, by_user=False)
def api_sign_sign(signer_token):
    """提交手写签名：嵌入 PDF + 标记 signed + 若双方签完生成最终版并邮件通知。"""
    import base64
    conn = db_conn()
    try:
        signer = conn.execute(
            "SELECT s.*, a.pdf_path, a.title, a.agreement_no, a.rev "
            "FROM agreement_signers s JOIN agreements a ON s.agreement_id=a.id "
            "WHERE s.signer_token=?", (signer_token,)
        ).fetchone()
        if not signer:
            return jsonify(ok=False, error="not found"), 404
        if signer["status"] != "pending":
            return jsonify(ok=False, error="already signed or agreement finalized"), 409

        data = request.get_json(silent=True) or {}
        sig_b64 = data.get("signature_base64", "").strip()
        full_name = data.get("full_name", "").strip()
        if not sig_b64 or not full_name:
            return jsonify(ok=False, error="signature_base64 and full_name required"), 400

        # 解码签名 PNG
        # 支持 data:image/png;base64,XXXX 前缀
        if "," in sig_b64:
            sig_b64 = sig_b64.split(",", 1)[1]
        try:
            sig_bytes = base64.b64decode(sig_b64)
        except Exception:
            return jsonify(ok=False, error="invalid signature_base64"), 400

        now = datetime.datetime.utcnow()
        now_str = now.isoformat()
        date_str = now.strftime("%d %B %Y")  # e.g. "21 August 2026"

        # 存签名 PNG
        agr_dir = AGREEMENTS_DIR / str(signer["agreement_id"])
        agr_dir.mkdir(parents=True, exist_ok=True)
        sig_dir = agr_dir / "signatures"
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig_path = sig_dir / "{}.png".format(signer["id"])
        sig_path.write_bytes(sig_bytes)

        # 嵌入签名到 PDF（基于当前 progress.pdf 或 original.pdf）
        sign_rects = json.loads(signer["sign_rects"]) if signer["sign_rects"] else {}
        # 找到当前版本的 PDF（优先 progress，其次 original）
        progress_path = agr_dir / "progress.pdf"
        source_pdf = str(progress_path) if progress_path.exists() else signer["pdf_path"]

        try:
            pdf_bytes = _embed_signature(source_pdf, str(sig_path), sign_rects, full_name, date_str)
        except Exception as e:
            app.logger.error("[sign] embed failed: %s", e)
            return jsonify(ok=False, error="signature embedding failed: {}".format(e)), 500

        # 保存中间版
        progress_path.write_bytes(pdf_bytes)

        # 更新签署方状态
        conn.execute(
            "UPDATE agreement_signers SET status='signed', signed_name=?, signature_png_path=?, signed_at=? WHERE id=?",
            (full_name, str(sig_path), now_str, signer["id"]),
        )

        # 记录事件
        conn.execute(
            "INSERT INTO agreement_events(agreement_id, signer_id, event_type, ip, created_at) VALUES(?,?,?,?,?)",
            (signer["agreement_id"], signer["id"], "signed", _client_ip(), now_str),
        )

        # 检查是否全部签完
        all_signers = conn.execute(
            "SELECT id, role, name, email, signer_token, status FROM agreement_signers WHERE agreement_id=?",
            (signer["agreement_id"],)
        ).fetchall()
        all_signed = all(s["status"] == "signed" for s in all_signers)

        finalized = False
        if all_signed:
            # 生成最终版
            final_path = agr_dir / "final.pdf"
            final_path.write_bytes(pdf_bytes)
            conn.execute(
                "UPDATE agreements SET final_pdf_path=?, status='finalized' WHERE id=?",
                (str(final_path), signer["agreement_id"]),
            )
            finalized = True

        conn.commit()

        # 邮件通知（异步，不影响签署结果）
        try:
            if finalized:
                # 双方签完：各发最终版 PDF
                final_bytes = pdf_bytes
                final_fname = "{}-{}-Signed.pdf".format(signer["agreement_no"], signer["rev"].replace(" ", ""))
                subject_done = "Agreement {} ({}) is fully signed".format(
                    signer["agreement_no"], signer["rev"])
                for s in all_signers:
                    html = (
                        '<div style="font-family:Inter,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px">'
                        '<div style="background:#1A1A2E;padding:16px;border-radius:8px 8px 0 0">'
                        '<span style="color:#D4A547;font-size:20px;font-weight:500">Snail</span>'
                        '<span style="color:#FF5B1F;font-size:20px;font-weight:500">AI</span>'
                        '<span style="color:#fff;font-size:20px;font-weight:500">.AI e-Sign</span></div>'
                        '<div style="padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px">'
                        '<p style="font-size:15px;color:#1A1A2E">Hello {name},</p>'
                        '<p style="font-size:14px;color:#444">Agreement <strong>{no}</strong> ({rev}) is now fully signed.</p>'
                        '<p style="font-size:14px;color:#444">The signed copy is attached. Please keep it safe.</p>'
                        '<p style="font-size:12px;color:#888;margin-top:16px">SnailAI.AI e-Sign</p>'
                        '</div></div>'
                    ).format(name=_esc(s["name"]), no=_esc(signer["agreement_no"]), rev=_esc(signer["rev"]))
                    _send_sign_email(s["email"], subject_done, html, attachments=[(final_fname, final_bytes)])
                # 通知 Robin（个人 Gmail 兜底 + 提示下一步发 Portal 启用邮件）
                html_r = (
                    '<div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">'
                    '<p style="font-size:14px;color:#1A1A2E">Agreement <strong>{no}</strong> ({rev}) has been fully signed by both parties.</p>'
                    '<p style="font-size:12px;color:#888">Finalized at: {ts} UTC &middot; Ref: {ref}</p>'
                    '<p style="font-size:14px;color:#1A1A2E;margin-top:12px">Next step: send the Portal onboarding email '
                    '(login URL, account &amp; password) to the client from the Admin Console — '
                    '<a href="https://snailai.ai/admin/" style="color:#FF5B1F">open Admin Console</a>.</p>'
                    '<p style="font-size:13px;color:#888">SnailAI.AI e-Sign</p></div>'
                ).format(no=_esc(signer["agreement_no"]), rev=_esc(signer["rev"]),
                         ts=now_str, ref=signer["signer_token"][:8])
                _send_sign_email(QUOTE_NOTIFY_TO, subject_done, html_r, from_addr=FROM_ADMIN)
            else:
                # 仅一方签完：通知 Robin 进度
                subject_prog = "Agreement {} ({}) — {} signed".format(
                    signer["agreement_no"], signer["rev"], full_name)
                html_prog = (
                    '<div style="font-family:Inter,Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">'
                    '<p style="font-size:14px;color:#1A1A2E">{name} has signed Agreement <strong>{no}</strong> ({rev}). '
                    'Awaiting other party.</p>'
                    '<p style="font-size:12px;color:#888">Signed at: {ts} UTC &middot; Ref: {ref}</p>'
                    '<p style="font-size:13px;color:#888">SnailAI.AI e-Sign</p></div>'
                ).format(name=_esc(full_name), no=_esc(signer["agreement_no"]), rev=_esc(signer["rev"]),
                         ts=now_str, ref=signer["signer_token"][:8])
                _send_sign_email(QUOTE_NOTIFY_TO, subject_prog, html_prog, from_addr=FROM_ADMIN)
        except Exception as e:
            app.logger.warning("[sign-email] notification failed: %s", e)

        return jsonify(ok=True, finalized=finalized)
    except Exception as e:
        conn.rollback()
        app.logger.error("[sign] error: %s", e)
        return jsonify(ok=False, error=str(e)), 500
    finally:
        conn.close()


@app.route("/sign/<signer_token>")
def sign_page(signer_token):
    """签合同页面路由：https://snailai.ai/sign/{signer_token}
    前端单页（sign/index.html）自行从 URL 提取 token 并调用 /api/sign/info/{token}。
    注意：必须注册在 catch-all serve() 之前，否则 /sign/{token} 会被静态文件
    处理器当作不存在的文件路径而 404。"""
    return send_from_directory(BASE, "sign/index.html")


@app.route("/api/quote/admin/cleanup", methods=["POST"])
def api_quote_admin_cleanup():
    """清空报价确认测试数据（交付前清场用）。需 X-Admin-Token 匹配 QUOTE_ADMIN_TOKEN。
    V1.7.0+: 只删除豁免名单内账号（如 demo）的确认记录，真实客户记录永久保留。"""
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify({"ok": False, "error": "unauthorised"}), 401
    conn = db_conn()
    try:
        before = conn.execute("SELECT COUNT(*) FROM quote_confirmations").fetchone()[0]
        # 只删豁免名单内的记录（demo 等测试账号），保留真实客户记录
        exempt_list = list(QUOTE_LOGIN_EXEMPT)
        if exempt_list:
            placeholders = ",".join(["?"] * len(exempt_list))
            rows = conn.execute(
                f"SELECT quote_id, client, confirmed_at FROM quote_confirmations WHERE LOWER(confirmed_by) IN ({placeholders}) ORDER BY confirmed_at DESC LIMIT 50",
                exempt_list
            ).fetchall()
            conn.execute(
                f"DELETE FROM quote_confirmations WHERE LOWER(confirmed_by) IN ({placeholders})",
                exempt_list
            )
        else:
            rows = []
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM quote_confirmations").fetchone()[0]
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "deletedCount": before - after,
        "remaining": after,
        "deletedRows": [{"quoteId": r[0], "client": r[1], "confirmedAt": r[2]} for r in rows],
    })


@app.route("/api/quote/admin/test-user", methods=["POST"])
def api_quote_admin_test_user():
    """Create or reset a test user for the quotation system.
    Requires X-Admin-Token header matching QUOTE_ADMIN_TOKEN env var.
    Body: {"username": "demo", "password": "test888", "name": "Test User"}
    Defaults: username=demo, password=test888, name=Demo User, role=customer"""
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "demo").strip().lower()
    password = data.get("password") or "test888"
    name = data.get("name") or "Demo User"
    role = "customer"
    import secrets as _sec
    salt = _sec.token_hex(16)
    pw_hash = _hash_pw(password, salt)
    c = db_conn()
    try:
        existing = c.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                             (username,)).fetchone()
        if existing:
            c.execute("UPDATE users SET password_hash=?, salt=?, name=?, role=?, must_change_pw=0 WHERE id=?",
                      (pw_hash, salt, name, role, existing["id"]))
        else:
            c.execute("INSERT INTO users (username, name, role, password_hash, salt, must_change_pw) "
                      "VALUES (?,?,?,?,?,0)", (username, name, role, pw_hash, salt))
        c.commit()
        app.logger.info("[admin] test user %s created/reset (role=%s)", username, role)
    finally:
        c.close()
    return jsonify({"ok": True, "username": username, "name": name, "role": role,
                    "password": password, "message": "Test user ready for login"})


@app.route("/api/login", methods=["POST"])
@_rate_limit_deco(_RL_LOGIN_LIMIT, _RL_LOGIN_WINDOW, by_user=False)
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = _auth_user(username, password)
    if not user:
        return jsonify(ok=False, error="用户名或密码错误"), 401
    # --- 一次性确认锁：已确认报价的客户无法再登录（豁免账号除外）---
    uname_lower = user["username"].lower()
    if uname_lower not in QUOTE_LOGIN_EXEMPT:
        conn_check = db_conn()
        finished = conn_check.execute(
            "SELECT 1 FROM quote_confirmations WHERE confirmed_by = ? LIMIT 1",
            (user["username"],)).fetchone()
        conn_check.close()
        if finished:
            return jsonify(ok=True, quote_finished=True,
                           user={"username": user["username"], "name": user["name"],
                                 "role": user["role"]}), 200
    token = _create_session(user["username"])
    ip = _client_ip()
    ua = request.headers.get("User-Agent", "")
    country, region, city = _geo_lookup(ip)
    conn = db_conn()
    conn.execute(
        "INSERT INTO login_events(username, ip, ua, country, region, city, login_at) "
        "VALUES(?,?,?,?,?,?, datetime('now'))",
        (user["username"], ip, ua, country, region, city))
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
    # 检查一次性确认锁
    uname_lower = user["username"].lower()
    quote_finished = False
    if uname_lower not in QUOTE_LOGIN_EXEMPT:
        conn_qf = db_conn()
        qf_row = conn_qf.execute(
            "SELECT 1 FROM quote_confirmations WHERE confirmed_by = ? LIMIT 1",
            (user["username"],)).fetchone()
        conn_qf.close()
        quote_finished = bool(qf_row)
    resp = {"ok": True, "user": _public_user(user)}
    if quote_finished:
        resp["quote_finished"] = True
    return jsonify(resp)


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
    rows = conn.execute(
        "SELECT id, title, description, category, points, sort_order "
        "FROM capabilities ORDER BY sort_order IS NULL, sort_order, id").fetchall()
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

    # 新项追加到末尾：sort_order = 当前最大 +1（保证排在列表最后）
    mx = conn.execute("SELECT MAX(sort_order) AS m FROM capabilities").fetchone()
    new_sort = (mx["m"] or 0) + 1

    # 防重复标题
    dup = conn.execute("SELECT id FROM capabilities WHERE title=?", (title,)).fetchone()
    if dup:
        conn.close()
        return jsonify(ok=False, error="已存在同名能力项"), 409

    conn.execute(
        "INSERT INTO capabilities(id, title, description, category, points, sort_order) "
        "VALUES(?,?,?,?,?,?)",
        (new_id, title, description, category, points, new_sort),
    )
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=new_id, title=title, description=description,
                   category=category, points=points)


@app.route("/api/capabilities/<cap_id>", methods=["DELETE"])
def api_delete_capability(cap_id):
    """管理员可删除 AI 能力项（助教/讲师无权限）。

    强制删除：删除能力项时一并清除学员对该项的勾选记录（checks），
    确保带勾选的能力也能直接删除，不留孤儿引用。
    """
    user = _current_user()
    if not user or user["role"] != "admin":
        return jsonify(ok=False, error="仅管理员可删除能力项"), 403
    conn = db_conn()
    cap = conn.execute("SELECT id FROM capabilities WHERE id=?", (cap_id,)).fetchone()
    if not cap:
        conn.close()
        return jsonify(ok=False, error="能力项不存在"), 404
    # 强制删除：连带清除学员对该能力项的勾选记录（用户已确认勾选记录无需保留）
    conn.execute("DELETE FROM checks WHERE cap_id=?", (cap_id,))
    conn.execute("DELETE FROM capabilities WHERE id=?", (cap_id,))
    conn.commit()
    conn.close()
    return jsonify(ok=True, id=cap_id, deleted_checks=True)


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


@app.route("/api/capabilities/<cap_id>", methods=["PUT"])
def api_update_capability(cap_id):
    """助教/讲师/管理员可更新能力项的标题、描述、分类和积分。

    所有字段均可选，仅更新传入的字段。
    """
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}

    conn = db_conn()
    cap = conn.execute("SELECT * FROM capabilities WHERE id=?", (cap_id,)).fetchone()
    if not cap:
        conn.close()
        return jsonify(ok=False, error="能力项不存在"), 404

    updates = {}
    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            conn.close()
            return jsonify(ok=False, error="标题不能为空"), 400
        # 防重复标题（排除自身）
        dup = conn.execute("SELECT id FROM capabilities WHERE title=? AND id!=?", (title, cap_id)).fetchone()
        if dup:
            conn.close()
            return jsonify(ok=False, error="已存在同名能力项"), 409
        updates["title"] = title
    if "description" in data:
        updates["description"] = (data.get("description") or "").strip()
    if "category" in data:
        category = (data.get("category") or "").strip()
        if not category:
            conn.close()
            return jsonify(ok=False, error="分类不能为空"), 400
        updates["category"] = category
    if "points" in data:
        try:
            pts = int(data.get("points", 0))
            if pts < 0:
                raise ValueError
        except (ValueError, TypeError):
            conn.close()
            return jsonify(ok=False, error="点数必须为非负整数"), 400
        updates["points"] = pts

    if not updates:
        conn.close()
        return jsonify(ok=False, error="没有需要更新的字段"), 400

    set_clause = ", ".join(f"{k}=?" for k in updates)
    params = list(updates.values()) + [cap_id]
    conn.execute(f"UPDATE capabilities SET {set_clause} WHERE id=?", params)
    conn.commit()

    updated = conn.execute("SELECT * FROM capabilities WHERE id=?", (cap_id,)).fetchone()
    conn.close()
    return jsonify(ok=True, cap_id=cap_id, **dict(updated))


@app.route("/api/capabilities/reorder", methods=["POST"])
@_rate_limit_deco(20, 60)
def api_reorder_capabilities():
    """助教/讲师/管理员可重排能力清单显示顺序。

    请求体：{"order": ["c06", "c01", ...]} —— 完整的、按期望显示顺序排列的 id 列表。
    后端校验 order 必须正好覆盖全部现有能力项 id（无重复、无外来项），
    通过后按列表下标 1..N 重写每项的 sort_order。互换 / 前移后移 / 插队
    都可由调用方在客户端算出完整顺序后一次性提交（幂等、原子）。
    """
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not order:
        return jsonify(ok=False, error="order 必须为非空 id 数组"), 400
    # 去重校验 + 类型归一
    seen, norm = set(), []
    for cid in order:
        s = str(cid).strip()
        if s in seen:
            return jsonify(ok=False, error="order 含重复 id"), 400
        seen.add(s)
        norm.append(s)
    conn = db_conn()
    rows = conn.execute("SELECT id FROM capabilities").fetchall()
    all_ids = {r["id"] for r in rows}
    if seen != all_ids:
        conn.close()
        return jsonify(ok=False, error="order 必须恰好包含全部现有能力项 id（无重复、无外来项）",
                       missing=sorted(all_ids - seen), extra=sorted(seen - all_ids)), 400
    for i, cid in enumerate(norm, 1):
        conn.execute("UPDATE capabilities SET sort_order=? WHERE id=?", (i, cid))
    conn.commit()
    conn.close()
    return jsonify(ok=True, count=len(norm))


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
    conn = db_conn()
    # 助教/总讲师/管理员：?all=1 返回所有学员的 AI 刚需，按学员分组
    if user["role"] in ("ta", "instructor", "admin") and request.args.get("all") == "1":
        # 获取所有有 AI 刚需的学员
        students = conn.execute(
            "SELECT DISTINCT n.username, u.name FROM ai_needs n "
            "LEFT JOIN users u ON n.username=u.username ORDER BY u.name, n.username"
        ).fetchall()
        result = []
        for s in students:
            rows = conn.execute(
                "SELECT id, username, seq, title, content, category, priority, tags, "
                "created_at, updated_at FROM ai_needs WHERE username=? ORDER BY seq",
                (s["username"],)).fetchall()
            needs = []
            for r in rows:
                d = dict(r)
                try:
                    d["tags"] = json.loads(d["tags"]) if d["tags"] else []
                except Exception:
                    d["tags"] = []
                needs.append(d)
            result.append({
                "username": s["username"],
                "name": s["name"] or s["username"],
                "needs": needs
            })
        conn.close()
        return jsonify(ok=True, all=True, students=result)
    # 学员只能看自己的；助教/总讲师可指定 username
    req_user = request.args.get("username")
    if user["role"] == "student":
        target = user["username"]
    else:
        target = req_user or user["username"]
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


@app.route("/api/admin/users/<username>/role", methods=["PUT"])
def api_admin_set_role(username):
    """总管理员修改用户角色（不改变密码）。
    仅 admin 可调用；支持 student/ta/instructor 之间的角色切换。"""
    user = _current_user()
    if not _is_admin(user):
        return jsonify(ok=False, error="无权限"), 403
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    if role not in ("student", "ta", "instructor"):
        return jsonify(ok=False, error="角色必须是 student/ta/instructor"), 400
    conn = db_conn()
    row = conn.execute("SELECT username FROM users WHERE username=?",
                       (username,)).fetchone()
    if not row:
        conn.close()
        return jsonify(ok=False, error="用户不存在"), 404
    conn.execute("UPDATE users SET role=? WHERE username=?", (role, username))
    conn.commit()
    updated = dict(conn.execute(
        "SELECT username, name, role FROM users WHERE username=?",
        (username,)).fetchone())
    conn.close()
    return jsonify(ok=True, user=updated)


# ---------------------------------------------------------------- 通讯录 (directory)
_DIR_FIELDS = ["student_no", "name", "zoom_id", "cpu", "ram", "storage", "github",
               "login_username", "email", "wechat", "phone", "online_course",
               "offline_course", "tuition_fee", "tuition_paid", "course_term", "identity"]
_DIR_INT = {"student_no", "online_course", "offline_course", "tuition_fee", "tuition_paid"}
# 学员可见的安全字段（不含邮箱、微信、手机、学费等隐私信息）
_DIR_PUBLIC_FIELDS = ["student_no", "name", "zoom_id", "cpu", "ram", "storage",
                      "github", "login_username"]


@app.route("/api/directory", methods=["GET"])
def api_dir_list():
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    conn = db_conn()
    if user["role"] == "student":
        # 学员可查看全部通讯录，但只返回安全字段（脱敏）
        rows = conn.execute(
            "SELECT " + ",".join(_DIR_PUBLIC_FIELDS) + " FROM directory ORDER BY student_no"
        ).fetchall()
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


@app.route("/api/congrats/log", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_congrats_log():
    """查询恭喜通知历史（助教/讲师/管理员可见）。"""
    user = _current_user()
    if not user or user["role"] not in ("ta", "instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    rows = conn.execute(
        "SELECT cl.id, cl.student_username, u.name AS student_name, "
        "cl.granted_by, cl.cap_count, cl.content, cl.created_at "
        "FROM congrats_log cl "
        "LEFT JOIN users u ON u.username=cl.student_username "
        "ORDER BY cl.created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify(ok=True, logs=[dict(r) for r in rows])


@app.route("/api/congrats/student/<username>", methods=["GET"])
@_rate_limit_deco(_RL_QUERY_LIMIT, _RL_QUERY_WINDOW)
def api_congrats_student(username):
    """查询某学员的恭喜通知历史（学员本人也可查）。"""
    user = _current_user()
    if not user:
        return jsonify(ok=False, error="未登录"), 401
    if user["role"] == "student" and user["username"] != username:
        return jsonify(ok=False, error="无权限"), 403
    conn = db_conn()
    rows = conn.execute(
        "SELECT cl.id, cl.granted_by, cl.cap_count, cl.content, cl.created_at "
        "FROM congrats_log cl "
        "WHERE cl.student_username=? ORDER BY cl.created_at DESC LIMIT 50",
        (username,)
    ).fetchall()
    conn.close()
    return jsonify(ok=True, logs=[dict(r) for r in rows])


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
        "FROM capabilities ORDER BY sort_order IS NULL, sort_order, id").fetchall()
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
    自动汇总该学员 self=1 AND ta=1 的能力项，构造企业微信 markdown 消息。
    同时写入 congrats_log，供助教看板查看历史。"""
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
    if not rows:
        conn.close()
        return jsonify(ok=False, error="该学员暂无可恭喜的能力项（需自查与助教审核均通过）"), 400
    lines = ["恭喜🎉 **%s** 学员获得以下 AI 能力：" % (t["name"] or username)]
    for i, r in enumerate(rows, 1):
        lines.append("%d. %s" % (i, r["title"]))
    lines.append("继续努力哦😄！")
    content = "\n".join(lines)
    ok, msg = _send_capability_congrats(content)
    # 写入 congrats_log（无论企微是否成功，都记录操作）
    try:
        conn.execute(
            "INSERT INTO congrats_log(student_username, granted_by, cap_count, content) "
            "VALUES(?,?,?,?)",
            (username, user["username"], len(rows), content))
        conn.commit()
    except Exception as e:
        print("[congrats_log] write error:", e)
    conn.close()
    return jsonify(ok=ok, sent=ok, message=msg, content=content, count=len(rows))


@app.route("/api/admin/leaderboard/test", methods=["POST"])
def api_leaderboard_test():
    """手动触发每日积分排行榜推送（测试用，仅管理员）。"""
    user = _current_user()
    if not user or user["role"] not in ("instructor", "admin"):
        return jsonify(ok=False, error="无权限"), 403
    _send_daily_leaderboard()
    return jsonify(ok=True, message="排行榜推送已触发（请检查企业微信群）")


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


def _build_points_leaderboard_text():
    """构造每日积分排行榜消息（markdown 格式，发企业微信群）。"""
    conn = db_conn()
    rows = conn.execute(
        "SELECT u.username, u.name, COALESCE(SUM(pl.points),0) AS total "
        "FROM users u "
        "LEFT JOIN points_log pl ON pl.username=u.username "
        "WHERE u.role='student' "
        "GROUP BY u.username, u.name "
        "ORDER BY total DESC, u.name ASC"
    ).fetchall()
    conn.close()
    if not rows:
        return None
    lines = [
        "🏆 **蜗牛AI 每日积分排行榜**",
        "📅 " + datetime.datetime.now().strftime("%Y-%m-%d") + "（悉尼时间）",
        "---"
    ]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows, 1):
        name = r["name"] or r["username"]
        total = r["total"]
        if i <= 3:
            lines.append("%s **%s** — %d 分" % (medals[i-1], name, total))
        else:
            lines.append("%d. %s — %d 分" % (i, name, total))
    lines.append("---")
    # 鼓励语
    top_name = (rows[0]["name"] or rows[0]["username"]) if rows else ""
    lines.append("🌟 **%s** 暂时领先，太棒了！" % top_name)
    lines.append("💪 其他同学继续加油，每天进步一点点，积少成多！")
    lines.append("🚀 明天的排行榜，等你来挑战！")
    return "\n".join(lines)


def _send_daily_leaderboard():
    """每日积分排行榜推送（由定时任务调用）。"""
    text = _build_points_leaderboard_text()
    if not text:
        print("[daily_leaderboard] 无学员数据，跳过推送")
        return
    url = os.environ.get("CAPABILITY_WEBHOOK_URL") or os.environ.get("WECHAT_WEBHOOK_URL")
    if not url:
        print("[daily_leaderboard] webhook URL 未配置，跳过推送")
        return
    try:
        r = requests.post(url, json={"msgtype": "markdown",
                                    "markdown": {"content": text}}, timeout=10)
        print("[daily_leaderboard] 推送结果:", r.status_code, r.text[:200])
    except Exception as e:
        print("[daily_leaderboard] 推送失败:", e)


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
    # 每日积分排行榜：悉尼时间 11:59（中午）推送
    _sched.add_job(_send_daily_leaderboard,
                   "cron", hour=11, minute=59, id="daily_leaderboard")
    _sched.start()


# ---------------------------------------------------------------- Stripe 支付（蜗牛AI课程报名）
import stripe as _stripe

_STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
_stripe.api_key = _STRIPE_KEY

_COURSE_PRICES = {
    "trial":   {"name_zh": "AI 体验课", "name_en": "AI Trial Class",              "amount_cents": 100},
    "online":  {"name_zh": "AI 应用线上课", "name_en": "AI Application Online Course",  "amount_cents": 59900},
    "wealth":   {"name_zh": "AI 财富管理线下课", "name_en": "AI Wealth Management Offline", "amount_cents": 199900},
}

@app.route("/api/create-checkout-session", methods=["POST"])
def api_create_checkout_session():
    """创建 Stripe Checkout Session，返回跳转 URL"""
    if not _STRIPE_KEY:
        return jsonify({"error": "Stripe 未配置"}), 503
    data = request.get_json(silent=True) or {}
    course = (data.get("course") or "").strip().lower()
    if course not in _COURSE_PRICES:
        return jsonify({"error": f"无效课程: {course}"}), 400
    info = _COURSE_PRICES[course]
    try:
        sess = _stripe.checkout.Session.create(
            mode="payment",
            success_url=request.url_root + "payment/success.html?session_id={CHECKOUT_SESSION_ID}&course=" + course,
            cancel_url=request.url_root + "?cancelled=1",
            line_items=[{
                "price_data": {
                    "currency": "aud",
                    "unit_amount": info["amount_cents"],
                    "product_data": {
                        "name": info["name_en"],
                        "description": info["name_zh"],
                    },
                },
                "quantity": 1,
            }],
            metadata={"course": course, "source": "snailai-portal"},
        )
        return jsonify({"url": sess.url})
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {str(e)}"}), 500


@app.route("/api/verify-session", methods=["GET"])
def api_verify_session():
    """验证 Checkout Session 付款状态"""
    sid = request.args.get("session_id", "")
    if not sid or not _STRIPE_KEY:
        return jsonify({"paid": False})
    try:
        sess = _stripe.checkout.Session.retrieve(sid)
        return jsonify({
            "paid": sess.payment_status == "paid",
            "course": sess.metadata.get("course", ""),
            "customer_email": sess.customer_details.get("email", "") if sess.customer_details else "",
        })
    except Exception:
        return jsonify({"paid": False})


# ---------------------------------------------------------------- 静态站点托管
# 企业微信自建应用「可信域名」验证：文件名 WW_verify_<内容>.txt，直接返回内容。
# 该路由必须在 catch-all 之前注册，否则会被 serve() 的 404 覆盖。
@app.route("/WW_verify_<suffix>.txt")
def wecom_domain_verify(suffix):
    return suffix, 200, {"Content-Type": "text/plain; charset=utf-8"}


# ---------------------------------------------------------------- 企业微信回调（解锁可信 IP 用）
# 仅实现 GET 验证（VerifyURL），不接收业务消息。用于通过「接收消息服务器 URL」
# 校验，从而解锁自建应用的企业可信 IP 白名单。
import base64 as _b64
import hashlib as _hashlib
import struct as _struct
from Crypto.Cipher import AES as _AES


class _WxBizMsgCrypt:
    def __init__(self, token, encoding_aes_key, corp_id):
        self.token = token
        self.key = _b64.b64decode(encoding_aes_key + "=")
        self.corp_id = corp_id

    def _signature(self, *args):
        s = "".join(sorted(args))
        return _hashlib.sha1(s.encode("utf-8")).hexdigest()

    def verify_url(self, msg_signature, timestamp, nonce, echostr):
        if self._signature(self.token, timestamp, nonce, echostr) != msg_signature:
            return None
        aes_msg = _b64.b64decode(echostr)
        # 企微规范：IV 取 AESKey 前 16 字节，对整段密文做 AES-256-CBC 解密
        iv = self.key[:16]
        cipher = _AES.new(self.key, _AES.MODE_CBC, iv)
        plain = cipher.decrypt(aes_msg)
        pad = plain[-1]
        plain = plain[:-pad]
        content = plain[16:]
        msg_len = _struct.unpack(">I", content[:4])[0]
        return content[4:4 + msg_len].decode("utf-8")


@app.route("/wecom_callback", methods=["GET"])
def wecom_callback():
    token = os.environ.get("WECOM_CALLBACK_TOKEN", "snailai_wecom_cb_2026")
    aes_key = os.environ.get("WECOM_CALLBACK_AESKEY",
                             "fATZdQgpClb8HD0/esLdoktglFQFURrAoh0drKGd7VY")
    corpid = os.environ.get("WECOM_CORPID", "wx43b97f937ac5863a")
    msg_signature = request.args.get("msg_signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")
    echostr = request.args.get("echostr", "")
    if not (token and aes_key and corpid and msg_signature and timestamp and nonce and echostr):
        return "bad request", 400
    try:
        crypt = _WxBizMsgCrypt(token, aes_key, corpid)
        reply = crypt.verify_url(msg_signature, timestamp, nonce, echostr)
    except Exception:
        return "verify error", 403
    if reply is None:
        return "signature mismatch", 403
    return reply


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

# ── 注册 Client Portal Blueprint ─────────────────────────
# 注意：Render 以 rootDir=server 启动 gunicorn（app:app），此处模块名为 portal 而非 server.portal
from portal import bp as portal_bp, init_portal_db
app.register_blueprint(portal_bp)
init_portal_db()

# ── 注册 Internal Tasks Blueprint ────────────────────────
from internal_tasks import bp as itask_bp, init_internal_tasks_db
app.register_blueprint(itask_bp)
init_internal_tasks_db()

# ── 注册 Business Opportunity Scan Routes ─────────────────
from scan_models import init_scan_tables
from scan_api import register_scan_routes
init_scan_tables(db_conn())
register_scan_routes(app)

# ── 注册 Grad Registration Blueprint ────────────────────
from grad_reg import bp as grad_reg_bp, init_grad_reg_db
app.register_blueprint(grad_reg_bp)
init_grad_reg_db()

print(f"[蜗牛AI Portal] 数据库: {DB_PATH}")
if not os.environ.get("WECHAT_WEBHOOK_URL"):
    print("[蜗牛AI Portal] ⚠️  警告：WECHAT_WEBHOOK_URL 未配置，日报/周报不会推送。"
          "请在 Render 控制台 → snailai-portal-1 → Environment 中添加该变量（值即企业微信 webhook 地址）。")

if __name__ == "__main__":
    print(f"[蜗牛AI Portal] 监听: http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
