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
ACADEMY = "https://academy.snailai.ai"

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


def _serve_academy(path):
    """academy host 上：路径已物理迁回 academy/ 目录，直接静态服务（不重定向）。
    与 app.py catch-all 的 academy 分支逻辑一致，防止 301 循环。
    注意：path 可能带前导斜杠（来自 REDIRECTS 表），须先剥掉，否则 pathlib
    会把绝对路径当根、导致目录穿越检查失败而 404。"""
    ac_base = BASE / "academy"
    path = path.lstrip("/")
    if not path:
        return send_from_directory(ac_base, "index.html")
    target = (ac_base / path).resolve()
    if ac_base not in target.parents and target != ac_base:
        abort(404)
    if target.is_dir():
        idx = target / "index.html"
        if idx.is_file():
            return send_from_directory(ac_base, path.rstrip("/") + "/index.html")
        abort(404)
    if target.is_file():
        return send_from_directory(ac_base, path)
    if not target.exists() and target.with_suffix(".html").is_file():
        return send_from_directory(ac_base, path + ".html")
    abort(404)


def register_redirects(app):
    """批量注册 301 显式路由（显式路由天然优先于 catch-all）。

    host 判定：
    - snailai.ai / www.snailai.ai → 301 重定向（迁移语义）
    - academy.snailai.ai → 该路径现属学院，直接静态服务（避免无限循环）
    - 其他 host（本地调试 127.0.0.1 等）→ 视同主站执行 301
    """
    for i, (old, new) in enumerate(REDIRECTS):
        def _make(old_path, target):
            def _view():
                host = request.host.split(":")[0]
                if host == "academy.snailai.ai":
                    return _serve_academy(old_path)
                return redirect(target, code=301)
            return _view
        app.add_url_rule(old, endpoint=f"r301_{i}", view_func=_make(old, new))
        # 目录型路径补一条无尾斜杠规则（Flask 默认 strict_slashes 会 308，这里显式 301）
        if old.endswith("/") and old != "/":
            app.add_url_rule(old.rstrip("/"), endpoint=f"r301_{i}_ns",
                             view_func=_make(old, new))
