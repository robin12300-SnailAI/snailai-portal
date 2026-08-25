# -*- coding: utf-8 -*-
"""
毕业展览日登记系统 — Blueprint
================================
路由前缀：/api/grad-registrations
公开登记页：/register（由静态文件 serve）

表结构：
  event_registrations  — 登记者（访客填表）
  event_referrers      — 推荐人（先登记拿码）

版本：grad-reg-v1.0.0
"""

import os
import json
import sqlite3
import re
from pathlib import Path
from functools import wraps
from flask import Blueprint, request, jsonify

# ── 路径常量 ──────────────────────────────────────────────
if os.environ.get("DB_PATH"):
    DB_PATH = Path(os.environ["DB_PATH"])
elif os.path.exists("/data"):
    DB_PATH = Path("/data/snailai.db")
else:
    DB_PATH = Path(Path(__file__).resolve().parent / "snailai.db")

# Admin Token（复用报价系统的同一个环境变量）
ADMIN_TOKEN = os.environ.get("QUOTE_ADMIN_TOKEN", "")

bp = Blueprint("grad_registrations", __name__, url_prefix="/api/grad-registrations")


# ═══════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════

def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_grad_reg_db():
    """建表。每次服务启动调用，幂等。"""
    conn = _db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS event_registrations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ref_code TEXT,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      wechat TEXT,
      email TEXT,
      company TEXT,
      interest TEXT,
      headcount INTEGER DEFAULT 1,
      status TEXT DEFAULT 'new',
      crm_client_id TEXT,
      crm_synced_at TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS event_referrers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ref_code TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      phone TEXT,
      wechat TEXT,
      crm_client_id TEXT,
      declared_count INTEGER DEFAULT 0,
      created_at TEXT DEFAULT (datetime('now'))
    );
    """)
    # 索引
    for sql in [
        "CREATE INDEX IF NOT EXISTS idx_ereg_status ON event_registrations(status)",
        "CREATE INDEX IF NOT EXISTS idx_ereg_ref_code ON event_registrations(ref_code)",
        "CREATE INDEX IF NOT EXISTS idx_eref_code ON event_referrers(ref_code)",
    ]:
        try:
            c.execute(sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════
# Admin auth decorator
# ═══════════════════════════════════════════════════════════

def _admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Admin-Token", "")
        if not ADMIN_TOKEN or token != ADMIN_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
# ref_code 生成
# ═══════════════════════════════════════════════════════════

def _next_ref_code(conn):
    """生成下一个 ref_code：G2601、G2602…"""
    row = conn.execute(
        "SELECT ref_code FROM event_referrers ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row and row["ref_code"]:
        num = int(row["ref_code"].replace("G26", "")) + 1
    else:
        num = 1
    return f"G26{num:02d}"


# ═══════════════════════════════════════════════════════════
# 公开 API — 登记提交
# ═══════════════════════════════════════════════════════════

@bp.route("/register", methods=["POST"])
def api_register():
    """访客提交登记（公开，无需认证）"""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    wechat = (data.get("wechat") or "").strip()
    email = (data.get("email") or "").strip()
    company = (data.get("company") or "").strip()
    interest = (data.get("interest") or "").strip()
    headcount = data.get("headcount", 1)
    ref_code = (data.get("ref_code") or "").strip()

    if not name or not phone:
        return jsonify({"error": "姓名和手机号为必填"}), 400

    try:
        headcount = int(headcount)
        if headcount < 1:
            headcount = 1
    except (ValueError, TypeError):
        headcount = 1

    conn = _db()
    try:
        # 重复登记去重（按手机号，首次 ref_code 有效）
        existing = conn.execute(
            "SELECT id FROM event_registrations WHERE phone = ?", (phone,)
        ).fetchone()
        if existing:
            return jsonify({"error": "该手机号已登记", "id": existing["id"]}), 409

        # 验证 ref_code 是否有效（如果提供了的话）
        if ref_code:
            ref_exists = conn.execute(
                "SELECT id FROM event_referrers WHERE ref_code = ?", (ref_code,)
            ).fetchone()
            if not ref_exists:
                return jsonify({"error": "推荐码无效"}), 400

        c = conn.execute(
            """INSERT INTO event_registrations
               (ref_code, name, phone, wechat, email, company, interest, headcount, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
            (ref_code or None, name, phone, wechat, email, company, interest, headcount)
        )
        conn.commit()
        reg_id = c.lastrowid
        return jsonify({"ok": True, "id": reg_id}), 201
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# 公开 API — 推荐人登记
# ═══════════════════════════════════════════════════════════

@bp.route("/referrer", methods=["POST"])
def api_referrer():
    """推荐人登记（公开，无需认证），返回 ref_code"""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    wechat = (data.get("wechat") or "").strip()
    declared_count = data.get("declared_count", 0)

    if not name:
        return jsonify({"error": "推荐人姓名为必填"}), 400

    try:
        declared_count = int(declared_count)
    except (ValueError, TypeError):
        declared_count = 0

    conn = _db()
    try:
        # 同一推荐人按手机号去重
        if phone:
            existing = conn.execute(
                "SELECT id, ref_code FROM event_referrers WHERE phone = ?", (phone,)
            ).fetchone()
            if existing:
                return jsonify({
                    "ok": True,
                    "id": existing["id"],
                    "ref_code": existing["ref_code"],
                    "message": "该手机号已登记为推荐人"
                }), 200

        ref_code = _next_ref_code(conn)
        c = conn.execute(
            """INSERT INTO event_referrers
               (ref_code, name, phone, wechat, declared_count)
               VALUES (?, ?, ?, ?, ?)""",
            (ref_code, name, phone, wechat, declared_count)
        )
        conn.commit()
        ref_id = c.lastrowid
        return jsonify({"ok": True, "id": ref_id, "ref_code": ref_code}), 201
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# 管理 API — 查看待同步列表
# ═══════════════════════════════════════════════════════════

@bp.route("/pending", methods=["GET"])
@_admin_required
def api_pending():
    """获取所有 status='new' 的登记记录（供 CRM 同步脚本拉取）"""
    conn = _db()
    try:
        rows = conn.execute(
            """SELECT r.*, ef.name AS referrer_name, ef.phone AS referrer_phone,
                      ef.wechat AS referrer_wechat, ef.crm_client_id AS referrer_crm_id
               FROM event_registrations r
               LEFT JOIN event_referrers ef ON r.ref_code = ef.ref_code
               WHERE r.status = 'new'
               ORDER BY r.id ASC"""
        ).fetchall()

        referrers_raw = conn.execute(
            """SELECT * FROM event_referrers ORDER BY id ASC"""
        ).fetchall()

        regs = [dict(r) for r in rows]
        refs = [dict(r) for r in referrers_raw]
        return jsonify({"registrations": regs, "referrers": refs}), 200
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# 管理 API — 回填同步状态
# ═══════════════════════════════════════════════════════════

@bp.route("/<int:reg_id>/sync", methods=["PATCH"])
@_admin_required
def api_mark_synced(reg_id):
    """同步成功后回填 crm_client_id + 更新状态"""
    data = request.get_json(silent=True) or {}
    crm_client_id = (data.get("crm_client_id") or "").strip()
    status = (data.get("status") or "synced").strip()

    if not crm_client_id:
        return jsonify({"error": "crm_client_id 必填"}), 400

    conn = _db()
    try:
        cur = conn.execute(
            """UPDATE event_registrations
               SET status = ?, crm_client_id = ?, crm_synced_at = datetime('now')
               WHERE id = ?""",
            (status, crm_client_id, reg_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "登记记录不存在"}), 404
        return jsonify({"ok": True}), 200
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# 管理 API — 回填推荐人 CRM ID
# ═══════════════════════════════════════════════════════════

@bp.route("/referrers/<int:ref_id>/sync", methods=["PATCH"])
@_admin_required
def api_mark_referrer_synced(ref_id):
    """同步推荐人到 CRM 后回填 crm_client_id"""
    data = request.get_json(silent=True) or {}
    crm_client_id = (data.get("crm_client_id") or "").strip()

    if not crm_client_id:
        return jsonify({"error": "crm_client_id 必填"}), 400

    conn = _db()
    try:
        cur = conn.execute(
            "UPDATE event_referrers SET crm_client_id = ? WHERE id = ?",
            (crm_client_id, ref_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "推荐人不存在"}), 404
        return jsonify({"ok": True}), 200
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
# 管理 API — 统计（助教只读看板用）
# ═══════════════════════════════════════════════════════════

@bp.route("/stats", methods=["GET"])
@_admin_required
def api_stats():
    """登记统计（不含佣金明细）"""
    conn = _db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM event_registrations"
        ).fetchone()["n"]

        by_status = conn.execute(
            "SELECT status, COUNT(*) AS n FROM event_registrations GROUP BY status"
        ).fetchall()

        by_ref = conn.execute(
            """SELECT r.ref_code, ef.name AS referrer_name, COUNT(*) AS cnt
               FROM event_registrations r
               LEFT JOIN event_referrers ef ON r.ref_code = ef.ref_code
               WHERE r.ref_code IS NOT NULL
               GROUP BY r.ref_code
               ORDER BY cnt DESC"""
        ).fetchall()

        total_headcount = conn.execute(
            "SELECT COALESCE(SUM(headcount), 0) AS n FROM event_registrations"
        ).fetchone()["n"]

        referrer_count = conn.execute(
            "SELECT COUNT(*) AS n FROM event_referrers"
        ).fetchone()["n"]

        return jsonify({
            "total_registrations": total,
            "total_headcount": total_headcount,
            "total_referrers": referrer_count,
            "by_status": {r["status"]: r["n"] for r in by_status},
            "by_referrer": [dict(r) for r in by_ref],
        }), 200
    finally:
        conn.close()
