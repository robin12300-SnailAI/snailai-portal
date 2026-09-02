"""
数据搬迁专用一次性导出端点（Phase 2 迁移期临时使用）。

- GET /api/admin/db-export  (X-Admin-Token 保护)
  导出学院站所需的全部 SQLite 表（JSON: {tables: {name: [rows...]}}）。
  只读操作，不修改任何数据；不导出 quote_* 表（企业站专属）。
- 搬迁完成验证后应删除本文件。
"""
from flask import Blueprint, request, jsonify

bp = Blueprint("migration_export", __name__)


def _deps():
    """延迟导入：app.py 尾部 import 本模块时避免循环导入。
    db_conn / QUOTE_ADMIN_TOKEN 在请求期必然已可用。"""
    from app import db_conn, QUOTE_ADMIN_TOKEN
    return db_conn, QUOTE_ADMIN_TOKEN

# 学院站需要的表（企业站专属表 quote_confirmations/contact_submissions 等不导出）
EXPORT_TABLES = [
    "users", "capabilities", "checks", "ai_needs", "directory",
    "points_log", "points_config", "assistant_assignments",
    "qa_threads", "qa_replies", "congrats_log",
    "login_events", "page_views",
    "agreements", "agreement_signers", "agreement_events",
    "course_payments", "sessions",
    "event_registrations", "event_referrers",
    "rate_limits", "conversion_events",
]


@bp.route("/api/admin/db-export", methods=["GET"])
def db_export():
    db_conn, QUOTE_ADMIN_TOKEN = _deps()
    if not QUOTE_ADMIN_TOKEN or request.headers.get("X-Admin-Token") != QUOTE_ADMIN_TOKEN:
        return jsonify(ok=False, error="unauthorized"), 401
    conn = db_conn()
    out = {}
    try:
        for name in EXPORT_TABLES:
            try:
                rows = conn.execute('SELECT * FROM "%s"' % name).fetchall()
                out[name] = [dict(r) for r in rows]
            except Exception:
                out[name] = []  # 表不存在则空数组
    finally:
        conn.close()
    return jsonify(ok=True, tables=out)
