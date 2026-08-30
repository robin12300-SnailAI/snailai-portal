# -*- coding: utf-8 -*-
"""
蜗牛AI AI助教 — Chat API 路由
================================
所有 /api/chat/* 路由

架构：官网前端 → /api/chat/ask → 后端代理 → 腾讯元器 API
- 八层防护（IP限流/日预算/并发闸门/缓存/facts直返/输入校验/超时/兜底）
- facts.json 优先命中（学费/开课时间等 100% 可控）
- 聊天日志全量记录 + 每日企微推送
"""
import json
import os
import re
import time
import hashlib
import logging
import sqlite3
import datetime
import threading
from pathlib import Path
from functools import wraps

import requests
from flask import request, jsonify

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

YUANQI_APPKEY = os.environ.get("YUANQI_APPKEY", "")
YUANQI_APPID = os.environ.get("YUANQI_APPID", "")
YUANQI_API_URL = "https://yuanqi.tencent.com/openapi/v1/agent/chat/completions"

CHAT_DAILY_BUDGET = int(os.environ.get("CHAT_DAILY_BUDGET", "400"))
CHAT_MAX_CONCURRENT = int(os.environ.get("CHAT_MAX_CONCURRENT", "8"))
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT_SECONDS", "25"))
WECHAT_WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")

SERVER_DIR = Path(__file__).resolve().parent
FACTS_PATH = SERVER_DIR / "knowledge" / "snailai-facts.json"

# 兜底话术
FALLBACK_ZH = "这不属于蜗牛 AI 知识库的范畴，请您上网去查询，谢谢。"
FALLBACK_EN = "This is outside the Snail AI knowledge base. Please search online, thank you."

# 系统提示词
SYSTEM_PROMPT_ZH = """你是蜗牛AI的助教，一位简洁高效型的AI助手。

规则：
1. 只能基于提供的知识库内容回答，找不到确切信息就说"这不属于蜗牛 AI 知识库的范畴，请您上网去查询，谢谢。"
2. 回答简洁高效，直接给出答案，200-500字
3. 禁止编造URL、价格、日期、人名
4. 禁止提供医疗、法律、投资、税务建议
5. 澳洲华人语境：货币用AUD，地名用悉尼说法
6. 回答结尾附来源：📄 来源：《文档名》
7. 不提系统内部术语，不推荐知识库外的工具
8. 非蜗牛AI相关问题礼貌拒绝"""

SYSTEM_PROMPT_EN = """You are a Snail AI tutor assistant. Be concise and efficient.

Rules:
1. Only answer based on the provided knowledge base. If unsure, say "This is outside the Snail AI knowledge base. Please search online, thank you."
2. Keep answers concise, 200-500 words
3. Never fabricate URLs, prices, dates, or names
4. No medical, legal, investment, or tax advice
5. Australian context: use AUD, Sydney terminology
6. Append source: 📄 Source: "Document Name"
7. No internal system terms; don't recommend tools outside the knowledge base
8. Politely decline non-Snail-AI questions"""

# 并发信号量
_llm_semaphore = threading.Semaphore(CHAT_MAX_CONCURRENT)


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _client_ip():
    """获取真实 IP（Render 代理链）"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def _detect_lang(text):
    """检测文本语言：中文字符占比 < 10% 且全 ASCII → en，否则 zh"""
    if not text:
        return "zh"
    zh_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    if zh_chars / max(len(text), 1) < 0.1 and text.isascii():
        return "en"
    return "zh"


def _hash_ip(ip):
    """IP 哈希，不存原文"""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _today_str():
    return datetime.date.today().isoformat()


def _qhash(question, lang):
    """问题缓存 key"""
    return hashlib.md5(f"{question}:{lang}".encode()).hexdigest()


# ──────────────────────────────────────────────
# Facts 加载
# ──────────────────────────────────────────────

_facts = None
_facts_mtime = 0

def _load_facts():
    """加载 facts.json，支持热更新（文件改了自动重载）"""
    global _facts, _facts_mtime
    try:
        mtime = FACTS_PATH.stat().st_mtime
        if _facts is None or mtime != _facts_mtime:
            with open(FACTS_PATH, "r", encoding="utf-8") as f:
                _facts = json.load(f)
            _facts_mtime = mtime
            log.info(f"[AI助教] facts.json 已加载，{len(_facts)} 条")
    except Exception as e:
        log.warning(f"[AI助教] facts.json 加载失败: {e}")
        _facts = _facts or []
    return _facts


def _match_facts(question, lang):
    """关键词匹配 facts，命中返回 (answer, refs)，未命中返回 None"""
    facts = _load_facts()
    q_lower = question.lower()
    best = None
    best_score = 0
    for fact in facts:
        keywords = fact.get("keywords_zh", []) + fact.get("keywords_en", [])
        score = sum(1 for kw in keywords if kw.lower() in q_lower)
        if score > best_score and score >= 1:
            best = fact
            best_score = score
    if best:
        answer = best.get(f"answer_{lang}") or best.get("answer_zh") or best.get("answer_en", "")
        refs = best.get("source", "")
        return answer, refs
    return None


# ──────────────────────────────────────────────
# 数据库操作
# ──────────────────────────────────────────────

def _get_db():
    """获取数据库连接（复用 app.py 的 DB_PATH 逻辑）"""
    db_path = os.environ.get("DB_PATH", "")
    if not db_path:
        if os.path.exists("/data"):
            db_path = "/data/snailai.db"
        else:
            db_path = str(Path(__file__).resolve().parent / "snailai.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _init_chat_tables():
    """建聊天相关表"""
    conn = _get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chat_logs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT DEFAULT (datetime('now')),
      ip_hash TEXT,
      user_id TEXT,
      lang TEXT,
      question TEXT,
      answer TEXT,
      refs TEXT,
      cached INTEGER DEFAULT 0,
      latency_ms INTEGER,
      fallback INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_chat_logs_ts ON chat_logs(ts);

    CREATE TABLE IF NOT EXISTS chat_daily_usage(
      day TEXT PRIMARY KEY,
      count INTEGER DEFAULT 0,
      fallback_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS chat_cache(
      qkey TEXT PRIMARY KEY,
      lang TEXT,
      answer TEXT,
      refs TEXT,
      hit_count INTEGER DEFAULT 1,
      created_at TEXT DEFAULT (datetime('now')),
      expires_at TEXT
    );
    """)
    conn.commit()
    conn.close()
    log.info("[AI助教] 聊天表已初始化")


def _log_chat(ip_hash, user_id, lang, question, answer, refs, cached, latency_ms, fallback):
    """记录聊天日志"""
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO chat_logs(ip_hash,user_id,lang,question,answer,refs,cached,latency_ms,fallback) VALUES(?,?,?,?,?,?,?,?,?)",
            (ip_hash, user_id, lang, question, answer, refs, cached, latency_ms, fallback)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"[AI助教] 日志写入失败: {e}")


def _check_daily_budget():
    """检查全局日预算，返回 (当前用量, 是否超预算)"""
    today = _today_str()
    try:
        conn = _get_db()
        row = conn.execute("SELECT count FROM chat_daily_usage WHERE day=?", (today,)).fetchone()
        count = row["count"] if row else 0
        conn.close()
        return count, count >= CHAT_DAILY_BUDGET
    except Exception:
        return 0, False


def _increment_daily(fallback=False):
    """日用量 +1"""
    today = _today_str()
    try:
        conn = _get_db()
        conn.execute("""
            INSERT INTO chat_daily_usage(day, count, fallback_count) VALUES(?, 1, ?)
            ON CONFLICT(day) DO UPDATE SET count=count+1, fallback_count=fallback_count+?
        """, (today, 1 if fallback else 0, 1 if fallback else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"[AI助教] 日用量更新失败: {e}")


def _check_ip_rate(ip_hash, limit, window_seconds):
    """检查 IP 级别限流，返回是否超限"""
    try:
        conn = _get_db()
        cutoff = (datetime.datetime.now() - datetime.timedelta(seconds=window_seconds)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM chat_logs WHERE ip_hash=? AND ts>?",
            (ip_hash, cutoff)
        ).fetchone()
        conn.close()
        return row["cnt"] >= limit
    except Exception:
        return False


def _check_cache(qkey):
    """查缓存，命中返回 (answer, refs)，未命中返回 None"""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT answer, refs FROM chat_cache WHERE qkey=? AND expires_at > datetime('now')",
            (qkey,)
        ).fetchone()
        if row:
            conn.execute("UPDATE chat_cache SET hit_count=hit_count+1 WHERE qkey=?", (qkey,))
            conn.commit()
            conn.close()
            return row["answer"], row["refs"]
        conn.close()
    except Exception:
        pass
    return None


def _write_cache(qkey, lang, answer, refs, ttl_hours=24):
    """写缓存"""
    try:
        conn = _get_db()
        expires = (datetime.datetime.now() + datetime.timedelta(hours=ttl_hours)).isoformat()
        conn.execute("""
            INSERT OR REPLACE INTO chat_cache(qkey, lang, answer, refs, hit_count, created_at, expires_at)
            VALUES(?, ?, ?, ?, 1, datetime('now'), ?)
        """, (qkey, lang, answer, refs, expires))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"[AI助教] 缓存写入失败: {e}")


# ──────────────────────────────────────────────
# 腾讯元器 API 调用
# ──────────────────────────────────────────────

def _call_yuanqi(question, lang):
    """调用腾讯元器 API，返回 (answer, refs) 或 raise"""
    if not YUANQI_APPKEY or not YUANQI_APPID:
        raise ValueError("YUANQI_APPKEY / YUANQI_APPID 未配置")

    system_prompt = SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN
    user_msg = question
    if lang == "en":
        # 跨语言 RAG：中文知识库 + 英文输出
        user_msg = f"{question}\n\nPlease answer in English based on the knowledge base."

    payload = {
        "assistant_id": YUANQI_APPID,
        "user_id": "snailai-visitor",
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_msg}]
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {YUANQI_APPKEY}",
        "Content-Type": "application/json"
    }

    with _llm_semaphore:
        resp = requests.post(
            YUANQI_API_URL,
            json=payload,
            headers=headers,
            timeout=AI_TIMEOUT
        )

    if resp.status_code != 200:
        log.error(f"[AI助教] 元器返回 {resp.status_code}: {resp.text[:200]}")
        raise ValueError(f"元器 API 返回 {resp.status_code}")

    data = resp.json()
    choice = data.get("choices", [{}])[0]
    answer = choice.get("message", {}).get("content", "")

    # 提取引文
    refs = ""
    steps = choice.get("message", {}).get("steps", [])
    for step in steps:
        if step.get("type") == "knowledge":
            for doc in step.get("documents", []):
                name = doc.get("name", doc.get("title", ""))
                if name and name not in refs:
                    refs = (refs + " | " + name) if refs else name

    return answer, refs


# ──────────────────────────────────────────────
# 企微告警
# ──────────────────────────────────────────────

def _send_wechat_alert(content):
    """发送企微 webhook 告警"""
    if not WECHAT_WEBHOOK_URL:
        return
    try:
        requests.post(
            WECHAT_WEBHOOK_URL,
            json={"msgtype": "text", "text": {"content": content}},
            timeout=5
        )
    except Exception:
        pass


# ──────────────────────────────────────────────
# 核心 API 处理函数
# ──────────────────────────────────────────────

def api_chat_ask():
    """
    POST /api/chat/ask
    body: { question: string, lang?: "zh"|"en" }
    八层防护链路
    """
    t0 = time.time()
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    ui_lang = data.get("lang") or "zh"

    # L0: 输入校验
    if not question or len(question) < 2:
        return jsonify(ok=False, error="请输入至少2个字的问题"), 400
    if len(question) > 500:
        return jsonify(ok=False, error="问题不能超过500字"), 400

    ip = _client_ip()
    ip_hash = _hash_ip(ip)
    detect_lang = _detect_lang(question)
    lang = ui_lang if ui_lang in ("zh", "en") else detect_lang

    # L1: 全局日预算
    current_usage, over_budget = _check_daily_budget()
    if over_budget:
        fallback = FALLBACK_ZH if lang == "zh" else FALLBACK_EN
        _increment_daily(fallback=True)
        _log_chat(ip_hash, None, lang, question, fallback, "", 0, int((time.time()-t0)*1000), 1)
        return jsonify(ok=True, answer=fallback, source="budget_exhausted", refs="")

    # L2: IP 分钟级限流 (10次/60s)
    if _check_ip_rate(ip_hash, 10, 60):
        return jsonify(ok=False, error="请求过于频繁，请稍后再试"), 429

    # L3: IP 日级限流 (60次/天)
    if _check_ip_rate(ip_hash, 60, 86400):
        return jsonify(ok=False, error="今日提问次数已达上限，明天再来"), 429

    # L4: Facts 直返
    fact_result = _match_facts(question, lang)
    if fact_result:
        answer, refs = fact_result
        latency = int((time.time() - t0) * 1000)
        _log_chat(ip_hash, None, lang, question, answer, refs, 0, latency, 0)
        _increment_daily()
        return jsonify(ok=True, answer=answer, source="facts", refs=refs)

    # L5: 缓存命中
    qkey = _qhash(question, lang)
    cached = _check_cache(qkey)
    if cached:
        answer, refs = cached
        latency = int((time.time() - t0) * 1000)
        _log_chat(ip_hash, None, lang, question, answer, refs, 1, latency, 0)
        _increment_daily()
        return jsonify(ok=True, answer=answer, source="cache", refs=refs)

    # L6-L7: 调用元器 API（并发闸门在 _call_yuanqi 内部）
    try:
        answer, refs = _call_yuanqi(question, lang)
        if not answer:
            answer = FALLBACK_ZH if lang == "zh" else FALLBACK_EN
            fallback_flag = 1
        else:
            fallback_flag = 0
    except Exception as e:
        log.error(f"[AI助教] 元器调用失败: {e}")
        answer = FALLBACK_ZH if lang == "zh" else FALLBACK_EN
        refs = ""
        fallback_flag = 1

    latency = int((time.time() - t0) * 1000)
    _log_chat(ip_hash, None, lang, question, answer, refs, 0, latency, fallback_flag)
    _increment_daily(fallback=bool(fallback_flag))

    # L8: 写缓存
    if not fallback_flag:
        _write_cache(qkey, lang, answer, refs)

    # 预算告警
    new_usage = current_usage + 1
    if new_usage >= CHAT_DAILY_BUDGET * 0.8 and new_usage < CHAT_DAILY_BUDGET:
        _send_wechat_alert(f"[AI助教] 今日对话量已达 {new_usage}/{CHAT_DAILY_BUDGET}，接近预算上限")

    return jsonify(ok=True, answer=answer, source="llm" if not fallback_flag else "fallback", refs=refs)


def api_chat_stats():
    """GET /api/admin/chat/stats — 管理员查看聊天统计"""
    try:
        conn = _get_db()
        today = _today_str()
        row = conn.execute("SELECT * FROM chat_daily_usage WHERE day=?", (today,)).fetchone()
        total_today = row["count"] if row else 0
        fallback_today = row["fallback_count"] if row else 0
        conn.close()
        return jsonify(ok=True, today=total_today, fallback=fallback_today, budget=CHAT_DAILY_BUDGET)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


def api_chat_recent():
    """GET /api/admin/chat/recent — 最近100条日志"""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM chat_logs ORDER BY id DESC LIMIT 100"
        ).fetchall()
        conn.close()
        return jsonify(ok=True, logs=[dict(r) for r in rows])
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# ──────────────────────────────────────────────
# 路由注册
# ──────────────────────────────────────────────

def register_chat_routes(app):
    """在 app.py 中调用此函数注册所有 chat 路由"""
    _init_chat_tables()

    # 公开 API
    app.add_url_rule("/api/chat/ask", "chat_ask", api_chat_ask, methods=["POST"])

    # Admin API
    app.add_url_rule("/api/admin/chat/stats", "chat_stats", api_chat_stats, methods=["GET"])
    app.add_url_rule("/api/admin/chat/recent", "chat_recent", api_chat_recent, methods=["GET"])

    log.info("[AI助教] 聊天路由已注册")
