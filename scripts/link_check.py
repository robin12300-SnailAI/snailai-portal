#!/usr/bin/env python3
"""Crawl snailai.ai / academy.snailai.ai / andrew.snailai.ai and report broken links.

Follows internal links up to a depth limit, reports any final status that is not 200.
Respects Cloudflare: always sends a real browser User-Agent.
"""
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SEEDS = [
    "https://snailai.ai/",
    "https://academy.snailai.ai/",
    "https://andrew.snailai.ai/",
]
HOSTS = {"snailai.ai", "academy.snailai.ai", "andrew.snailai.ai"}
MAX_DEPTH = 3
MAX_PAGES = 260
DELAY = 0.12

HREF_RE = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\']', re.I)
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".mp4",
            ".webm", ".woff", ".woff2", ".ttf", ".css", ".js")

# 误报过滤器
SKIP_PATTERNS = (
    "${",           # JS 模板字符串里的占位符（如 href="${c.href}"），不是真实链接
    "/cdn-cgi/",    # Cloudflare 邮件混淆 / 内部端点，需特定上下文才能返回 200
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Capture redirect target without following, so we can record the chain."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"-> {newurl}", headers, fp)


def build_opener(follow: bool):
    if follow:
        return urllib.request.build_opener()
    return urllib.request.build_opener(NoRedirect)


def norm(url: str) -> str:
    """百分号编码非 ASCII 路径——否则 urllib 直接抛错，浏览器却会自动编码。

    不修的话中文路径（如 /AI 应用线上班）会被误报成死链。
    """
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def get(url: str, follow: bool = True):
    """Return (status, final_url, body)."""
    url = norm(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with build_opener(follow).open(req, timeout=25) as r:
            body = r.read()
            if not (url.lower().endswith((".html", "/")) or r.headers.get("Content-Type", "").startswith("text/html")):
                body = b""
            return r.status, r.geturl(), body.decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            return e.code, str(e.reason).replace("-> ", "").strip(), ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        return e.code, url, body
    except Exception as e:
        return 0, url, f"{type(e).__name__}: {e}"


def resolve(start: str):
    """Follow redirect chain, return (final_status, chain)."""
    chain, url, seen = [], start, set()
    for _ in range(6):
        if url in seen:
            return 0, chain + [f"LOOP {url}"]
        seen.add(url)
        code, nxt, _ = get(url, follow=False)
        chain.append(f"{code} {urllib.parse.unquote(url)}")
        if 300 <= code < 400:
            url = urllib.parse.urljoin(url, nxt)
            continue
        return code, chain
    return 0, chain + ["TOO_MANY_REDIRECTS"]


def main() -> int:
    visited, queue, problems = set(), deque(), []
    for s in SEEDS:
        queue.append((s, 0))

    pages = 0
    while queue and pages < MAX_PAGES:
        url, depth = queue.popleft()
        key = url.rstrip("/") or url
        if key in visited:
            continue
        visited.add(key)

        status, final, body = get(url)
        pages += 1
        if status != 200:
            problems.append((status, url, "seed/direct"))
            continue
        if depth >= MAX_DEPTH or not body:
            continue

        for href in HREF_RE.findall(body):
            href = href.strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            if any(bad in href for bad in SKIP_PATTERNS):
                continue
            if href.lower().split("?")[0].endswith(SKIP_EXT):
                continue
            full = urllib.parse.urljoin(url, href)
            p = urllib.parse.urlparse(full)
            if p.scheme not in ("http", "https"):
                continue

            if p.netloc in HOSTS:
                target = full
            elif p.netloc in ("", "www.snailai.ai"):
                continue
            else:
                # external: light HEAD-ish check, record only hard failures
                target = None
                if p.netloc not in ("snailai.com.au", "snailai.au", "snailai.site"):
                    continue
                target = full

            if target:
                nk = target.rstrip("/") or target
                if nk not in visited:
                    queue.append((target, depth + 1))
            time.sleep(DELAY)

    print(f"已抓取 {pages} 个内部页面，发现 {len(visited)} 个链接\n")

    # 逐个解析最终状态
    broken, redirecting = [], []
    for i, u in enumerate(sorted(visited)):
        code, chain = resolve(u)
        if code == 200:
            continue
        if len(chain) > 1 or 300 <= code < 400:
            redirecting.append((code, u, chain))
        else:
            broken.append((code, u, chain))
        time.sleep(DELAY)

    if broken:
        print(f"❌ 死链 {len(broken)} 条")
        for code, u, chain in broken:
            print(f"   {code}  {urllib.parse.unquote(u)}")
    else:
        print("✅ 无死链")

    if redirecting:
        print(f"\n↪️  重定向 {len(redirecting)} 条（全部列出，确认落点正确）")
        for code, u, chain in redirecting:
            print(f"   {urllib.parse.unquote(u)}")
            for c in chain:
                print(f"        └ {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
