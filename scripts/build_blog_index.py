#!/usr/bin/env python3
"""Generate academy/blog/index.html from the individual blog posts.

academy/blog/ has 6 posts but no index page, so /blog/ returns 404 while it is
already listed in academy/sitemap.xml. This reads each post's <title> and
meta description and builds a matching index page (guide.css card style,
CollectionPage + ItemList JSON-LD).

Idempotent: safe to re-run; overwrites the index each time.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "academy" / "blog"
SITE = "https://academy.snailai.ai"

# 顺序 + 图标 + 分类标签（按「先入门、后进阶」排列）
ORDER = [
    ("chatgpt-basics", "🚀", "入门"),
    ("prompt-engineering", "🎯", "技巧"),
    ("ai-sme", "🏢", "提效"),
    ("ai-image-video", "🎨", "创作"),
    ("ai-wealth", "💰", "财富"),
    ("sydney-workshop", "📍", "线下"),
]


def meta(html: str, pattern: str) -> str:
    m = re.search(pattern, html, re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    if not BLOG.is_dir():
        print(f"找不到目录：{BLOG}")
        return 1

    posts = []
    for slug, emoji, tag in ORDER:
        f = BLOG / slug / "index.html"
        if not f.is_file():
            print(f"  ⚠️ 跳过（无 index.html）: {slug}")
            continue
        html = f.read_text(encoding="utf-8")
        title = meta(html, r"<title>(.*?)</title>").split("|")[0].strip()
        desc = meta(html, r'name="description" content="(.*?)"')
        date = meta(html, r'"datePublished":\s*"([^"]+)"') or "2026-08-17"
        posts.append({"slug": slug, "title": title, "desc": desc,
                      "date": date, "emoji": emoji, "tag": tag})

    # 补上 ORDER 里没列出但实际存在的文章
    for d in sorted(p for p in BLOG.iterdir() if p.is_dir()):
        if (d / "index.html").is_file() and d.name not in {p["slug"] for p in posts}:
            html = (d / "index.html").read_text(encoding="utf-8")
            posts.append({
                "slug": d.name,
                "title": meta(html, r"<title>(.*?)</title>").split("|")[0].strip(),
                "desc": meta(html, r'name="description" content="(.*?)"'),
                "date": meta(html, r'"datePublished":\s*"([^"]+)"') or "2026-08-17",
                "emoji": "📄", "tag": "文章",
            })
            print(f"  + 补入新文章: {d.name}")

    cards = "\n".join(
        f'''        <a class="g-card" href="{SITE}/blog/{p['slug']}/">
          <div class="emo">{p['emoji']}</div>
          <div class="g-tag">{p['tag']} · {p['date']}</div>
          <h3>{p['title']}</h3>
          <p>{p['desc'][:96]}</p>
          <div class="go">阅读全文 →</div>
        </a>'''
        for p in posts
    )

    item_list = [
        {"@type": "ListItem", "position": i + 1,
         "item": {"@type": "Article", "headline": p["title"],
                  "description": p["desc"][:160],
                  "url": f"{SITE}/blog/{p['slug']}/",
                  "datePublished": p["date"],
                  "inLanguage": "zh-CN"}}
        for i, p in enumerate(posts)
    ]

    payload = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage",
             "@id": f"{SITE}/blog/#webpage",
             "url": f"{SITE}/blog/",
             "name": "蜗牛 AI 博客 · 澳洲华人 AI 实用指南",
             "description": "面向澳洲华人的 AI 实用指南：ChatGPT 入门、提示词工程、中小企业提效、AI 绘画与视频、AI 财富研究、悉尼线下工作坊。",
             "inLanguage": "zh-CN",
             "publisher": {"@id": "https://snailai.ai/#organization"},
             "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": [
                 {"@type": "ListItem", "position": 1, "name": "蜗牛AI 学院", "item": f"{SITE}/"},
                 {"@type": "ListItem", "position": 2, "name": "博客", "item": f"{SITE}/blog/"},
             ]}},
            {"@type": "ItemList", "name": "蜗牛 AI 博客文章",
             "itemListOrder": "https://schema.org/ItemListUnordered",
             "numberOfItems": len(posts), "itemListElement": item_list},
        ],
    }, ensure_ascii=False, indent=2)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>蜗牛 AI 博客 · 澳洲华人 AI 实用指南 | 蜗牛 AI 学院</title>
<meta name="description" content="面向澳洲华人的 AI 实用指南：ChatGPT 入门、提示词工程、中小企业提效、AI 绘画与视频、AI 财富研究、悉尼线下工作坊实录。">
<link rel="icon" type="image/png" href="{SITE}/assets/snailai_logo.png">
<link rel="canonical" href="{SITE}/blog/">
<meta property="og:type" content="website">
<meta property="og:title" content="蜗牛 AI 博客 · 澳洲华人 AI 实用指南">
<meta property="og:description" content="ChatGPT 入门、提示词工程、中小企业提效、AI 绘画与视频、AI 财富研究——6 篇实操指南。">
<meta property="og:image" content="{SITE}/assets/snailai_logo.png">
<meta property="og:url" content="{SITE}/blog/">
<meta property="og:locale" content="zh_CN">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/assets/guide.css">
<script type="application/ld+json">
{payload}
</script>
<style>
  .g-tag {{ font-size:12px; color:var(--ink-3); letter-spacing:.3px; margin-bottom:6px; }}
  .blog-hero {{ text-align:center; padding:44px 20px 8px; }}
  .blog-hero h1 {{ font-size:30px; margin-bottom:10px; }}
  .blog-hero p {{ color:var(--ink-3); font-size:15px; max-width:620px; margin:0 auto; }}
  .g-grid {{ margin-top:34px; }}
</style>
</head>
<body>

<header class="g-header">
  <div class="g-wrap" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
    <a href="{SITE}/" style="font-weight:700;font-size:17px;">🐌 蜗牛 AI 学院</a>
    <nav class="g-nav">
      <a href="{SITE}/online-course/">线上课</a>
      <a href="{SITE}/offline-course/">线下课</a>
      <a href="{SITE}/guide/">AI 指南</a>
      <a href="{SITE}/faq/">常见问题</a>
    </nav>
  </div>
</header>

<main class="g-wrap">

  <div class="g-breadcrumb">
    <a href="{SITE}/">首页</a> › <span>博客</span>
  </div>

  <div class="blog-hero">
    <h1>澳洲华人 AI 实用指南</h1>
    <p>不讲概念，只讲能立刻上手的做法。每篇都围绕一个具体场景：写邮件、做方案、出图出片、读财报。</p>
  </div>

  <div class="g-grid">
{cards}
  </div>

  <section class="g-cta" style="margin-top:52px;">
    <h3>想系统学？看线上课</h3>
    <p>6 篇指南覆盖的场景，蜗牛 AI 线上班会带你在自己的业务上完整练一遍。</p>
    <a href="{SITE}/online-course/" class="g-btn">查看课程 →</a>
  </section>

</main>

<footer class="g-foot">
  <p>蜗牛 AI Snail AI · 澳洲华人 AI 应用教育学院 · <a href="https://snailai.ai/">snailai.ai</a></p>
</footer>

</body>
</html>
'''

    out = BLOG / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✅ 已生成 {out.relative_to(ROOT)}（{len(posts)} 篇文章）")
    for p in posts:
        print(f"     {p['emoji']} {p['tag']:<4} {p['slug']:<20} {p['title'][:36]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
