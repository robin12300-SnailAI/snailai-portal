# -*- coding: utf-8 -*-
"""
redirects.py — snailai.ai URL 迁移重定向表（V3.1.0 academy 迁移配套）

维护规则（铁律）：
1. 本表只登记「已从仓库根物理移除」的路径。登记的路径永远不会再有真实文件。
2. 不要删除任何条目——历史邮件、书签、搜索引擎都依赖这些 301 保终身。
3. /sign/<token> 绝不出现在本表（eSign 路由在 catch-all 之前注册，永不冲突）。
4. 新增条目前确认目标 URL 真实存在。
"""

from flask import redirect, request, send_from_directory, abort
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
# 2026-09-02：学院整体迁往 snailai.au（独立服务 snailai-school）。
# 主站旧课程 URL 直跳 snailai.au，避免 snailai.ai → academy.snailai.ai → snailai.au 两跳链。
ACADEMY = "https://snailai.au"

_MAIN_HOSTS = {"snailai.ai", "www.snailai.ai"}

# (old_path, new_url)  — old_path 均为 snailai.ai host 下的路径
REDIRECTS = [
    # ---- A. 中文课程 → academy（同路径迁移） ----
    ("/online-course/", ACADEMY + "/online-course/"),
    ("/offline-course/", ACADEMY + "/offline-course/"),
    ("/AI 应用线上班/", ACADEMY + "/AI%20应用线上班/"),
    ("/AI 财富线下班/", ACADEMY + "/AI%20财富线下班/"),
    ("/AI 能力清单/", ACADEMY + "/AI%20能力清单/"),
    ("/faq/", ACADEMY + "/faq/"),
    ("/guide/", ACADEMY + "/guide/"),
    ("/ai-tutor/", ACADEMY + "/ai-tutor/"),
    ("/qa/", ACADEMY + "/qa/"),
    ("/ta/", ACADEMY + "/ta/"),
    ("/ta/dashboard.html", ACADEMY + "/ta/dashboard.html"),
    ("/ta/ai-needs.html", ACADEMY + "/ta/ai-needs.html"),
    ("/ta/ai-needs-mobile.html", ACADEMY + "/ta/ai-needs-mobile.html"),
    ("/register/", ACADEMY + "/register/"),
    ("/register/services.html", ACADEMY + "/register/services.html"),
    ("/register/students.html", ACADEMY + "/register/students.html"),
    ("/login.html", ACADEMY + "/login.html"),
    ("/welcome.html", ACADEMY + "/welcome.html"),
    ("/payment/success.html", ACADEMY + "/payment/success.html"),  # Stripe 回跳页（checkout 在 academy 域发起时 url_root 已指向 academy；此条覆盖旧链接直接访问主站的场景）
    ("/dashboard.html", ACADEMY + "/dashboard.html"),
    ("/lesson.html", ACADEMY + "/lesson.html"),
    ("/change-password.html", ACADEMY + "/change-password.html"),
    ("/analytics.html", ACADEMY + "/analytics.html"),
    ("/成长点数介绍.html", ACADEMY + "/成长点数介绍.html"),
    ("/admin/", ACADEMY + "/admin/"),
    ("/路演直播 PPT/", ACADEMY + "/路演直播%20PPT/"),
    # blog 6 篇
    ("/blog/chatgpt-basics/", ACADEMY + "/blog/chatgpt-basics/"),
    ("/blog/prompt-engineering/", ACADEMY + "/blog/prompt-engineering/"),
    ("/blog/ai-image-video/", ACADEMY + "/blog/ai-image-video/"),
    ("/blog/ai-wealth/", ACADEMY + "/blog/ai-wealth/"),
    ("/blog/ai-sme/", ACADEMY + "/blog/ai-sme/"),
    ("/blog/sydney-workshop/", ACADEMY + "/blog/sydney-workshop/"),
    # 旧移动首页 → academy 首页
    ("/mobile.html", ACADEMY + "/"),
    # mobile 变体（无扩展名 / 显式 .html）→ 对应桌面页
    ("/faq/mobile", ACADEMY + "/faq/"),
    ("/faq/mobile.html", ACADEMY + "/faq/"),
    ("/qa/mobile", ACADEMY + "/qa/"),
    ("/qa/mobile.html", ACADEMY + "/qa/"),
    ("/ai-tutor/mobile", ACADEMY + "/ai-tutor/"),
    ("/ai-tutor/mobile.html", ACADEMY + "/ai-tutor/"),
    ("/online-course/mobile", ACADEMY + "/online-course/"),
    ("/online-course/mobile.html", ACADEMY + "/online-course/"),
    ("/offline-course/mobile", ACADEMY + "/offline-course/"),
    ("/offline-course/mobile.html", ACADEMY + "/offline-course/"),
    ("/ta/mobile", ACADEMY + "/ta/"),
    ("/ta/mobile.html", ACADEMY + "/ta/"),

    # ---- 归档活动页 → academy/archive ----
    ("/live-share-2026-07-04/", ACADEMY + "/archive/live-share-2026-07-04/"),
    ("/live-share-2026-07-04/mobile.html", ACADEMY + "/archive/live-share-2026-07-04/"),
    ("/snailai-pitch-2026/", ACADEMY + "/archive/snailai-pitch-2026/"),
    ("/snailai-pitch-2026/mobile.html", ACADEMY + "/archive/snailai-pitch-2026/"),
    ("/grad-show-2026/", ACADEMY + "/archive/grad-show-2026/"),
    ("/grad-reg-board/", ACADEMY + "/archive/grad-reg-board/"),

    # ---- B. 英文主站域内 301 ----
    ("/enterprise/", "/services/"),
    ("/enterprise/mobile.html", "/services/"),
    ("/corporate-training/", "/services/corporate-ai-training/"),
    ("/corporate-training/mobile.html", "/services/corporate-ai-training/"),
    ("/industry/healthcare/", "/industries/medical-clinics/"),
    ("/industry/construction/", "/industries/construction-trades/"),
    # 注意：本站目前没有 hospitality（餐饮/酒店）行业页，全站也未提及 hospitality。
    # 早前把它 301 到 professional-services 属语义错配 —— Google 会按 soft-404 处理，
    # 且访客落地质问答非所问。改为落到行业总览页（诚实的父级，保留权重）。
    ("/industry/hospitality/", "/industries/"),
    ("/industry/legal/", "/industries/professional-services/"),
    ("/ai-data-principles/", "/security-and-data-handling/"),
    ("/business-opportunity-scan/", "/business-ai-scan/"),
    ("/business-opportunity-scan/start.html", "/business-ai-scan/start.html"),
    ("/business-opportunity-scan/privacy/", "/business-ai-scan/privacy/"),
]



def register_redirects(app):
    """批量注册 301 显式路由（显式路由天然优先于 catch-all）。

    2026-09-02 起 academy.snailai.ai 全量 301 到 snailai.au（学院独立部署），
    本表目标也已改为 snailai.au 直跳——所有 host 统一 301，不再有本地 academy 静态服务分支。

    2026-09-03 修复：保留 query string（ref_code 等参数不再被丢弃）。
    """
    for i, (old, new) in enumerate(REDIRECTS):
        def _make(old_path, target):
            def _view():
                # 保留原始请求的 query string（如 ?ref_code=G2621）
                qs = request.query_string.decode("utf-8") if request.query_string else ""
                final = target + ("?" + qs if qs else "")
                return redirect(final, code=301)
            return _view
        app.add_url_rule(old, endpoint=f"r301_{i}", view_func=_make(old, new))
        # 目录型路径补一条无尾斜杠规则（Flask 默认 strict_slashes 会 308，这里显式 301）
        if old.endswith("/") and old != "/":
            app.add_url_rule(old.rstrip("/"), endpoint=f"r301_{i}_ns",
                             view_func=_make(old, new))
