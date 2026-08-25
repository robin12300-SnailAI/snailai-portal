#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
毕业展览日 · 推荐人批量创建脚本
================================
从名单批量创建推荐人，每人分配专属 ref_code（G26XX），
生成海报链接清单（MD + HTML）。

去重键：phone 字段存 "gh:<GitHub用户名>"，重复运行幂等（同账号返回已有 ref_code）。

用法：
    python3 tools/batch_create_referrers.py [--base https://snailai.ai] [--token XXX]

产出：
    tools/out/referrer_links.md   — 链接清单（Markdown）
    tools/out/referrer_links.html — 链接清单（可点击复制，浏览器打开）
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import date

# ═══════════════════════════════════════════════════════════
# 名单（GitHub 账号为唯一标识，去重合并学生/助教）
# 角色: student=纯学员 / ta=纯助教 / both=学员兼助教
# ═══════════════════════════════════════════════════════════
ROSTER = [
    # ── 纯学员（students.yml 顺序）──
    {"name": "Nova",            "github": "NOVASUN168",        "role": "student"},
    {"name": "Wang",            "github": "pwang8866",          "role": "student"},
    {"name": "SHOU390",         "github": "SHOU390",            "role": "student"},
    {"name": "Jason 王",        "github": "jmcawang-ui",        "role": "student"},
    {"name": "Coco",            "github": "Coco-li-yanhong",    "role": "student"},
    {"name": "Lucyshi333",      "github": "Lucyshi333",         "role": "student"},
    {"name": "Scamp-rabbit",    "github": "Scamp-rabbit",       "role": "student"},
    {"name": "Scamprabbit",     "github": "Scamprabbit",        "role": "student"},
    {"name": "danjin111",       "github": "danjin111",          "role": "student"},
    {"name": "serenaxie888",    "github": "serenaxie888",       "role": "student"},
    {"name": "simonzy168-star", "github": "simonzy168-star",    "role": "student"},
    {"name": "tellmood",        "github": "tellmood",           "role": "student"},
    {"name": "xdliu788-star",   "github": "xdliu788-star",      "role": "student"},
    # ── 学员兼助教 ──
    {"name": "Michael",         "github": "mynameisgy",         "role": "both"},
    {"name": "Maureen",         "github": "maureengithub123",   "role": "both"},
    {"name": "仙路",            "github": "jiangpei555",        "role": "both"},
    # ── 纯助教（Teaching-Assistants 团队）──
    {"name": "Jason918262",     "github": "jason918262",        "role": "ta"},
    {"name": "ksiwuqing-cmyk",  "github": "ksiwuqing-cmyk",     "role": "ta"},
    {"name": "ZRR168",          "github": "ZRR168",             "role": "ta"},
    {"name": "rssz12300",       "github": "rssz12300",          "role": "ta"},
]

ROLE_LABEL = {"student": "学员", "ta": "助教", "both": "学员+助教"}


def api(base, path, method="GET", body=None, token=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    # Cloudflare 会拦截 Python-urllib 默认 UA（error 1010），必须带自定义 UA
    req.add_header("User-Agent", "SnailAI-GradReg-Tool/1.0")
    if token:
        req.add_header("X-Admin-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://snailai.ai")
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    results = []
    print(f"共 {len(ROSTER)} 人，开始批量创建推荐人...\n")
    print(f"{'#':<3} {'姓名':<16} {'GitHub':<20} {'角色':<8} {'ref_code':<9} 结果")
    print("-" * 75)

    for i, p in enumerate(ROSTER, 1):
        status, resp = api(
            args.base, "/api/grad-registrations/referrer", method="POST",
            body={"name": p["name"], "phone": f"gh:{p['github']}"},
        )
        ref_code = resp.get("ref_code", "?")
        if status in (200, 201) and ref_code:
            tag = "新建" if status == 201 else "已存在(幂等)"
            link = f"{args.base.rstrip('/')}/register?ref_code={ref_code}"
            results.append({**p, "ref_code": ref_code, "link": link, "tag": tag})
            print(f"{i:<3} {p['name']:<16} {p['github']:<20} {ROLE_LABEL[p['role']]:<8} {ref_code:<9} ✅ {tag}")
        else:
            results.append({**p, "ref_code": None, "link": None, "tag": f"失败({status})"})
            print(f"{i:<3} {p['name']:<16} {p['github']:<20} {ROLE_LABEL[p['role']]:<8} {'-':<9} ❌ {resp}")

    ok = [r for r in results if r["ref_code"]]
    fail = [r for r in results if not r["ref_code"]]
    print("-" * 75)
    print(f"\n成功 {len(ok)} / 失败 {len(fail)}")

    if not ok:
        sys.exit(1)

    # ── 生成清单文件 ──
    out_dir = Path(__file__).parent / "out"
    out_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()

    # Markdown
    md = ["# 毕业展览日 · 推荐人专属链接清单", "",
          f"> 生成时间：{today} · 共 {len(ok)} 人",
          "> 每人链接用于海报二维码，扫码登记自动关联推荐人", "",
          "| # | 姓名 | 角色 | GitHub | 推荐码 | 专属链接 |",
          "|---|------|------|--------|--------|----------|"]
    for i, r in enumerate(ok, 1):
        md.append(f"| {i} | {r['name']} | {ROLE_LABEL[r['role']]} | {r['github']} | `{r['ref_code']}` | `{r['link']}` |")
    (out_dir / "referrer_links.md").write_text("\n".join(md), encoding="utf-8")

    # HTML（可点击复制）
    rows = ""
    for i, r in enumerate(ok, 1):
        rows += f"""
      <tr>
        <td>{i}</td><td class="name">{r['name']}</td><td>{ROLE_LABEL[r['role']]}</td>
        <td>{r['github']}</td><td><span class="code">{r['ref_code']}</span></td>
        <td class="link-cell"><span class="link" id="lnk{i}">{r['link']}</span></td>
        <td><button onclick="copyLink({i})">复制</button></td>
      </tr>"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>毕业展览日 · 推荐人链接清单</title>
<style>
body {{ font-family: -apple-system, sans-serif; background: #f5f6f8; color: #1a1d27; padding: 20px; }}
h1 {{ font-size: 20px; }}
.meta {{ color: #6b7280; font-size: 13px; margin-bottom: 16px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
th {{ background: #eef0f4; padding: 10px 12px; font-size: 12px; text-align: left; color: #6b7280; }}
td {{ padding: 10px 12px; border-top: 1px solid #e5e7eb; font-size: 14px; }}
.name {{ font-weight: 600; }}
.code {{ font-family: monospace; font-weight: 700; color: #c75a3a; background: #fde8e0; padding: 2px 8px; border-radius: 4px; }}
.link {{ font-family: monospace; font-size: 12px; color: #2563eb; word-break: break-all; }}
button {{ background: #2563eb; color: #fff; border: none; border-radius: 6px; padding: 5px 12px; cursor: pointer; font-size: 12px; }}
button:hover {{ background: #1d4ed8; }}
.toast {{ position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #16a07a; color: #fff; padding: 8px 20px; border-radius: 8px; display: none; }}
</style>
</head>
<body>
<h1>🐌 毕业展览日 · 推荐人专属链接</h1>
<div class="meta">生成 {today} · 共 {len(ok)} 人 · 链接用于海报二维码，扫码登记自动归因</div>
<table>
  <thead><tr><th>#</th><th>姓名</th><th>角色</th><th>GitHub</th><th>推荐码</th><th>专属链接</th><th></th></tr></thead>
  <tbody>{rows}
  </tbody>
</table>
<div class="toast" id="toast">已复制到剪贴板 ✓</div>
<script>
function copyLink(i) {{
  const text = document.getElementById('lnk' + i).textContent;
  navigator.clipboard.writeText(text).then(() => {{
    const t = document.getElementById('toast');
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', 1500);
  }});
}}
</script>
</body>
</html>"""
    (out_dir / "referrer_links.html").write_text(html, encoding="utf-8")

    print(f"\n清单已生成：")
    print(f"  MD   {out_dir / 'referrer_links.md'}")
    print(f"  HTML {out_dir / 'referrer_links.html'}")


if __name__ == "__main__":
    main()
