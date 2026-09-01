#!/usr/bin/env python3
"""Fix academy.snailai.ai pages whose canonical/og:url still point at snailai.ai.

These pages were moved to the academy subdomain but kept main-domain URLs in
<meta rel=canonical> and <meta property=og:url>, creating a canonical -> 301
chain. Best practice is a self-referencing canonical on the serving host.

Idempotent: rewrites only https://snailai.ai/... inside academy/, and only in
canonical / og:url / hreflang / twitter:url attributes.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACADEMY = ROOT / "academy"

# 只改这些属性里的主域 URL，避免误伤正文链接
ATTRS = r'(?:rel="canonical" href|property="og:url" content|hreflang="[^"]*" href|name="twitter:url" content|property="og:image" content|name="twitter:image" content)'
PATTERN = re.compile(rf'({ATTRS})="https://snailai\.ai/', re.I)


def main() -> int:
    if not ACADEMY.is_dir():
        print(f"找不到 academy 目录：{ACADEMY}")
        return 1

    changed = 0
    for page in sorted(ACADEMY.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        new, n = PATTERN.subn(r'\1="https://academy.snailai.ai/', html)
        if n:
            page.write_text(new, encoding="utf-8")
            print(f"  OK ({n}): {page.relative_to(ROOT)}")
            changed += 1

    print(f"\n修改文件数: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
