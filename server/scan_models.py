# -*- coding: utf-8 -*-
"""
蜗牛AI Business Opportunity Scan — 数据模型与初始化
=====================================================
4 张新表 + 敏感内容检测 + 输入清洗工具函数
"""
import json
import re
import hashlib
import secrets
import sqlite3
import datetime
import os
import logging

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 表创建（在 init_db 时由 app.py 调用）
# ──────────────────────────────────────────────

SCAN_TABLES_SQL = """
-- 提交记录
CREATE TABLE IF NOT EXISTS scan_submissions(
    id TEXT PRIMARY KEY,                    -- UUID
    public_token_hash TEXT UNIQUE NOT NULL, -- 报告访问 token 的 SHA-256
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',     -- NEW/VALIDATING/PROCESSING/REVIEW_FAILED/REPORT_READY/EMAIL_SENT/DELETION_SCHEDULED/DELETED
    -- 联系信息（受限字段，日志不记录明文）
    full_name TEXT NOT NULL,
    work_email TEXT NOT NULL,
    mobile_number TEXT,
    company_name TEXT NOT NULL,
    company_website TEXT,
    suburb TEXT NOT NULL,
    postcode TEXT NOT NULL,
    role TEXT NOT NULL,
    decision_authority TEXT NOT NULL,
    employee_band TEXT NOT NULL,
    -- 行业
    industry_group TEXT NOT NULL,           -- A/B/C
    sub_industry TEXT NOT NULL,
    years_operating TEXT,
    business_model TEXT,
    primary_goal TEXT,
    -- 工具
    tools_json TEXT,                        -- JSON array
    industry_tools_json TEXT,               -- JSON array
    systems_integration TEXT,
    re_entry_frequency TEXT,
    -- 工作流痛点
    main_pain_process TEXT,
    pain_frequency TEXT,
    people_involved TEXT,
    weekly_hours TEXT,
    what_goes_wrong_json TEXT,              -- JSON array
    success_looks_like TEXT,
    -- 行业专属工作流（最多5项）
    industry_workflows_json TEXT,           -- JSON array
    top_workflow_priority TEXT,             -- 最优先的那一项
    -- 准备度
    process_documented TEXT,
    process_owner_exists TEXT,
    pilot_willingness TEXT,
    automation_level TEXT,
    data_sensitivity TEXT,
    desired_start_time TEXT,
    indicative_budget TEXT,
    onsite_assessment_interest TEXT,
    -- 网站抓取同意
    website_review_consent INTEGER DEFAULT 0,
    -- 同意
    consent_report INTEGER DEFAULT 0,
    consent_no_sensitive INTEGER DEFAULT 0,
    consent_privacy INTEGER DEFAULT 0,
    consent_email_delivery INTEGER DEFAULT 0,
    marketing_opt_in INTEGER DEFAULT 0,
    -- 元数据
    source TEXT,
    utm_source TEXT,
    utm_medium TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    utm_term TEXT,
    -- 销售状态
    sales_status TEXT DEFAULT 'NEW',        -- HIGH_FIT/POTENTIAL_FIT/NURTURE/CALL_REQUESTED/CALL_BOOKED/ONSITE_APPROVED/ONSITE_BOOKED/PROPOSAL_SENT/CONVERTED/CLOSED
    -- 数据保留
    retention_delete_at TEXT,
    -- 内部备注（不进入报告）
    internal_notes TEXT,
    -- idempotency
    idempotency_key TEXT UNIQUE,
    -- CAPTCHA
    turnstile_token TEXT
);

-- AI 分析结果
CREATE TABLE IF NOT EXISTS scan_analysis(
    scan_id TEXT PRIMARY KEY REFERENCES scan_submissions(id),
    created_at TEXT NOT NULL,
    normalised_input_json TEXT,
    deterministic_scores_json TEXT,
    risk_flags_json TEXT,
    model_provider TEXT,
    model_name TEXT,
    prompt_version TEXT,
    knowledge_version TEXT,
    raw_model_json TEXT,                    -- 受限，不含被拦截敏感内容
    validated_analysis_json TEXT,
    reviewer_result_json TEXT,
    generation_cost REAL,
    latency_ms INTEGER,
    -- 处理状态
    pipeline_stage TEXT DEFAULT 'PENDING',  -- PENDING/NORMALISATION/SCORING/ANALYSIS/VALIDATION/REVIEW/RENDERING/COMPLETE/FAILED
    pipeline_error TEXT,
    retry_count INTEGER DEFAULT 0
);

-- 报告
CREATE TABLE IF NOT EXISTS scan_reports(
    scan_id TEXT PRIMARY KEY REFERENCES scan_submissions(id),
    report_version INTEGER DEFAULT 1,
    rendered_html TEXT,
    pdf_path TEXT,                          -- 相对于 /data/scan-reports/ 的路径
    secure_token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    emailed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 活动日志
CREATE TABLE IF NOT EXISTS scan_activities(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scan_submissions(id),
    event_type TEXT NOT NULL,               -- CREATED/PROCESSING/REPORT_READY/EMAIL_SENT/REPORT_VIEWED/PDF_DOWNLOADED/CALL_REQUESTED/ONSITE_APPLIED/TOKEN_REVOKED/REGENERATED/STATUS_CHANGED/NOTE_ADDED/DELETED
    actor TEXT,                             -- system / admin:<username> / visitor
    safe_metadata TEXT,                     -- JSON，不含敏感原文
    created_at TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_scan_sub_status ON scan_submissions(status);
CREATE INDEX IF NOT EXISTS idx_scan_sub_sales ON scan_submissions(sales_status);
CREATE INDEX IF NOT EXISTS idx_scan_sub_email ON scan_submissions(work_email);
CREATE INDEX IF NOT EXISTS idx_scan_sub_created ON scan_submissions(created_at);
CREATE INDEX IF NOT EXISTS idx_scan_reports_token ON scan_reports(secure_token_hash);
CREATE INDEX IF NOT EXISTS idx_scan_activities_scan ON scan_activities(scan_id);
CREATE INDEX IF NOT EXISTS idx_scan_sub_retention ON scan_submissions(retention_delete_at);
"""


def init_scan_tables(conn: sqlite3.Connection):
    """在现有数据库上创建 scan 相关表。幂等。"""
    c = conn.cursor()
    c.executescript(SCAN_TABLES_SQL)
    conn.commit()
    log.info("[scan] Tables created/verified")


# ──────────────────────────────────────────────
# 敏感内容检测
# ──────────────────────────────────────────────

# 澳洲 Medicare 号码格式（颜色: 1234 56789 0）
_MEDICARE_RE = re.compile(r'\b\d{4}\s?\d{5}\s?\d\b')
# TFN（8-9位数字，常见空格分隔）
_TFN_RE = re.compile(r'\b\d{2,3}\s?\d{3}\s?\d{3}\b')
# 信用卡号（简单：13-19位数字，可能有空格或短横）
_CC_RE = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
# 澳洲驾照号码
_DL_RE = re.compile(r'\b[A-Z]{1,2}\d{4,8}\b', re.IGNORECASE)
# 疑似姓名+病情组合（宽松匹配）
_HEALTH_KEYWORDS = re.compile(
    r'\b(?:patient|diagnosis|diagnosed|prescribed|medication|dosage|'
    r'symptoms|condition|treatment|prognosis|referral|blood test|'
    r'x-ray|mri|ct scan|ultrasound|biopsy|pathology)\b',
    re.IGNORECASE
)
# 疑似个人标识
_PERSONAL_ID = re.compile(
    r'\b(?:medicare|medicare number|health care|concession|'
    r'pension|dva|abn|acn|bsb|account number)\b',
    re.IGNORECASE
)
# DOB 格式
_DOB_RE = re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b')


class SensitiveDetectionResult:
    """敏感内容检测结果"""
    def __init__(self):
        self.has_medicare = False
        self.has_tfn = False
        self.has_credit_card = False
        self.has_health_keyword = False
        self.has_personal_id = False
        self.has_dob = False
        self.blocked = False
        self.flags = []

    @property
    def is_sensitive(self) -> bool:
        return any([self.has_medicare, self.has_tfn, self.has_credit_card,
                     self.has_health_keyword, self.has_personal_id])

    def to_dict(self) -> dict:
        return {
            "has_medicare": self.has_medicare,
            "has_tfn": self.has_tfn,
            "has_credit_card": self.has_credit_card,
            "has_health_keyword": self.has_health_keyword,
            "has_personal_id": self.has_personal_id,
            "has_dob": self.has_dob,
            "blocked": self.blocked,
            "flags": self.flags
        }


def detect_sensitive_content(text: str, is_medical: bool = False) -> SensitiveDetectionResult:
    """
    检测自由文本中的敏感内容。
    医疗组（is_medical=True）使用更严格的规则。
    返回检测结果；blocked=True 时应阻止提交到 AI 模型。
    """
    r = SensitiveDetectionResult()

    if not text:
        return r

    # 通用检测
    if _MEDICARE_RE.search(text):
        r.has_medicare = True
        r.flags.append("possible_medicare_number")

    if _TFN_RE.search(text):
        r.has_tfn = True
        r.flags.append("possible_tfn")

    if _CC_RE.search(text):
        r.has_credit_card = True
        r.flags.append("possible_credit_card")

    if _PERSONAL_ID.search(text):
        r.has_personal_id = True
        r.flags.append("possible_personal_identifier")

    # 医疗组额外检测
    if is_medical:
        if _HEALTH_KEYWORDS.search(text):
            r.has_health_keyword = True
            r.flags.append("possible_health_information")
        if _DOB_RE.search(text):
            r.has_dob = True
            r.flags.append("possible_date_of_birth")

    # 硬性阻止规则：检测到 Medicare/TFN/CC 时必须阻止
    r.blocked = r.has_medicare or r.has_tfn or r.has_credit_card

    # 医疗组：健康关键词 + DOB 也阻止
    if is_medical and (r.has_health_keyword or r.has_dob):
        r.blocked = True

    return r


# ──────────────────────────────────────────────
# 输入清洗
# ──────────────────────────────────────────────

def sanitize_input(text: str, max_length: int = 2000) -> str:
    """清洗自由文本输入：去 HTML、去脚本、截断"""
    if not text:
        return ""
    # 去除 HTML 标签
    text = re.sub(r'<[^>]*>', '', text)
    # 去除 script/style 内容
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # 去除 null 字节
    text = text.replace('\x00', '')
    # 截断
    if len(text) > max_length:
        text = text[:max_length]
    # 去首尾空白
    return text.strip()


def normalise_email(email: str) -> str:
    """标准化邮箱：小写、去空白"""
    return email.strip().lower() if email else ""


# ──────────────────────────────────────────────
# Token 工具
# ──────────────────────────────────────────────

def generate_public_token() -> str:
    """生成不可猜测的报告访问 token"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """对 token 做 SHA-256 哈希（存数据库用）"""
    return hashlib.sha256(token.encode()).hexdigest()


# ──────────────────────────────────────────────
# 评分常量
# ──────────────────────────────────────────────

LEAD_FIT_BANDS = {
    "high": (75, 100),
    "potential": (55, 74),
    "early": (35, 54),
    "low": (0, 34),
}

INDUSTRY_GROUPS = {
    "A": "Construction, Engineering, Trades & Property Management",
    "B": "Professional Services",
    "C": "Medical & Healthcare Practices",
}

EMPLOYEE_BANDS = ["1", "2-4", "5-9", "10-19", "20-49", "50-99", "100-199", "200+"]

SYDNEY_POSTCODES = set(
    # Sydney metropolitan postcodes (2000-2249)
    [str(i) for i in range(2000, 2250)] +
    # Additional outer metro areas
    [str(i) for i in range(2750, 2780)] +
    ["2560", "2745", "2746", "2747", "2748", "2749", "2760", "2765", "2770", "2774", "2775", "2776", "2777", "2780"]
)


def is_sydney_postcode(postcode: str) -> bool:
    """判断是否在悉尼大都市服务范围内"""
    return postcode in SYDNEY_POSTCODES


# ──────────────────────────────────────────────
# 状态机
# ──────────────────────────────────────────────

SCAN_STATUSES = [
    "NEW", "VALIDATING", "PROCESSING", "REVIEW_FAILED",
    "REPORT_READY", "EMAIL_SENT",
    "DELETION_SCHEDULED", "DELETED"
]

SALES_STATUSES = [
    "NEW", "HIGH_FIT", "POTENTIAL_FIT", "NURTURE",
    "CALL_REQUESTED", "CALL_BOOKED",
    "ONSITE_APPROVED", "ONSITE_BOOKED",
    "PROPOSAL_SENT", "CONVERTED", "CLOSED"
]
