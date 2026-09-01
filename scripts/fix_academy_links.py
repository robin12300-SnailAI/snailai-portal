#!/usr/bin/env python3
"""Rewrite academy-owned absolute URLs inside academy/ from snailai.ai to academy.snailai.ai.

After the subdomain migration many academy pages still link to
https://snailai.ai/guide/ etc., which now 301 back to academy.snailai.ai.
That is a needless redirect hop for users and for crawlers.

Only academy-owned path prefixes are rewritten. Main-site-only paths are
deliberately preserved:
  /            bare homepage (legitimate brand cross-link to the main site)
  /privacy/    lives on the main site only
  /terms/      lives on the main site only
  /services/   English B2B main site only

Idempotent: pages already pointing at academy.snailai.ai are untouched.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACADEMY = ROOT / "academy"

# 学院自有路径前缀（必须带尾斜杠或为完整文件名，避免误匹配 /services 这类）
OWNED_PREFIXES = (
    "/guide/", "/blog/", "/online-course/", "/offline-course/",
    "/faq/", "/qa/", "/ai-tutor/", "/ta/", "/register/", "/payment/",
    "/login.html", "/dashboard.html", "/lesson.html", "/change-password.html",
    "/analytics.html", "/welcome.html", "/assets/",
)

PATTERN = re.compile(r'https://snailai\.ai(/[A-Za-z0-9._~%/\u4e00-\u9fff -]*)?')


def should_rewrite(path: str) -> bool:
    if not path:
        return False  # 裸首页：保留，属于品牌主站互链
    return any(path.startswith(p) or path == p.rstrip("/") for p in OWNED_PREFIXES)


def repl(m: re.Match) -> str:
    path = m.group(1) or "/"
    if not should_rewrite(path):
        return m.group(0)
    return "https://academy.snailai.ai" + path


def main() -> int:
    if not ACADEMY.is_dir():
        print(f"找不到 academy 目录：{ACADEMY}")
        return 1

    total_files = total_hits = 0
    for page in sorted(ACADEMY.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        new, n = PATTERN.subn(repl, html)
        if n:
            page.write_text(new, encoding="utf-8")
            print(f"  OK ({n:>3}): {page.relative_to(ROOT)}")
            total_files += 1
            total_hits += n

    print(f"\n修改 {total_files} 个文件，{total_hits} 处链接")
    return 0


if __name__ == "__main__":
    sys.exit(main())
