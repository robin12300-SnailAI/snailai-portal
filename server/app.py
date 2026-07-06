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
DB_PATH = SERVER_DIR / "snailai.db"
PORT = int(os.environ.get("PORT", "5000"))
HOST = os.environ.get("HOST", "127.0.0.1")
# 允许跨域的来源（GitHub Pages 主站等）。生产可改为你的域名。
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
SESSION_TTL_HOURS = 24 * 7  # 会话有效期 7 天

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------- 数据库
def db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
        ("student01", "张三（学员示例）", "student", "snail123"),
        ("student02", "李四（学员示例）", "student", "snail123"),
        ("ta01", "王助教（示例）", "ta", "snailai@ta"),
        ("teacher01", "Robin Luo（总讲师）", "instructor", "snail@teacher"),
    ]
    for username, name, role, pw in users:
        salt = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users(username, name, role, password_hash, salt) "
            "VALUES(?,?,?,?,?)",
            (username, name, role, _hash_pw(pw, salt), salt),
        )


def _seed_capabilities(c):
    caps = [
        ("c01", "AI 认知与思维", "理解 AI 的能力边界", "能说清大模型能做什么、不能做什么，不把 AI 当万能神"),
        ("c02", "AI 认知与思维", "输出式学习思维", "边用边学，用 AI 完成真实任务而非只看教程"),
        ("c03", "AI 认知与思维", "从问题出发选工具", "先有真实问题，再找 AI 怎么帮，而非为用而用"),
        ("c04", "基础工具使用", "ChatGPT 提示词基础", "会用角色+任务+约束结构，从问答题变选择题"),
        ("c05", "基础工具使用", "豆包 / 语音输入法", "会用悬浮窗语音输入，用语音和 AI 对话做记录"),
        ("c06", "基础工具使用", "Gemini 与 Google 全家桶", "会用侧边栏、Drive/Calendar 联动、记忆导入"),
        ("c07", "基础工具使用", "NotebookLM 资料总结", "上传资料让 AI 总结、提取要点"),
        ("c08", "基础工具使用", "PDF / 文档处理", "图片 PDF 转文字、生成 Word/PDF"),
        ("c09", "内容创作", "AI 写短视频脚本", "会用钩子+内容+结尾结构生成脚本"),
        ("c10", "内容创作", "文生图提示词", "能写基础文生图提示词生成图片"),
        ("c11", "内容创作", "AI 邮件处理", "起草、翻译、提炼英文/中文邮件"),
        ("c12", "工作流与自动化", "双 AI 协作模式", "主管 AI 规划 + 执行 AI 落地的工作流"),
        ("c13", "工作流与自动化", "提示词工程进阶", "能从喜欢的模板提取并升级提示词"),
        ("c14", "工作流与自动化", "AI 记忆系统配置", "会用 Soul/Identity/User/Memory 建立 AI 档案"),
        ("c15", "工作流与自动化", "自动化任务设置", "会设每日/定时自动化，让 AI 替你跑"),
        ("c16", "工作流与自动化", "自定义技能开发", "能用 MD+JSON 把重复工作变成一键技能"),
        ("c17", "工作流与自动化", "企业微信机器人推送", "配置 Webhook，让 AI 推送到手机"),
        ("c18", "财富 AI 应用", "财务 / 报税自动化", "澳洲费用分析、银行对账单 OCR、报税整理"),
        ("c19", "财富 AI 应用", "股票 / 房产 AI 分析", "用 AI 做强度系统、房产数据自动化复盘"),
        ("c20", "财富 AI 应用", "个人 AI 财富工作流", "搭建从数据到决策的完整投资 AI 流程"),
        ("c21", "安全与伦理", "隐私与数据安全", "知道什么资料不该喂给公开 AI、用本地/合规方案"),
        ("c22", "安全与伦理", "AI 内容甄别", "能识别 AI 幻觉、交叉验证关键信息"),
    ]
    for cid, cat, title, desc in caps:
        c.execute(
            "INSERT INTO capabilities(id, title, description, category) VALUES(?,?,?,?)",
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
    if not path:
        return send_from_directory(BASE, "login.html")
    target = (BASE / path).resolve()
    # 防目录穿越
    if BASE in target.parents or target == BASE:
        if target.is_dir():
            idx = target / "index.html"
            if idx.is_file():
                return send_from_directory(BASE, path.rstrip("/") + "/index.html")
        elif target.is_file():
            return send_from_directory(BASE, path)
    # SPA 回退到登录页
    return send_from_directory(BASE, "login.html")


if __name__ == "__main__":
    init_db()
    print(f"[蜗牛AI Portal] 数据库: {DB_PATH}")
    print(f"[蜗牛AI Portal] 监听: http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
