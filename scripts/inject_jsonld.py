#!/usr/bin/env python3
"""Inject JSON-LD structured data into snailai.ai pages before </head>.

Idempotent: skips any page that already contains application/ld+json.
Also fixes Business AI Scan page meta (title/description/canonical/OG).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ORG_ID = "https://snailai.ai/#organization"
SITE = "https://snailai.ai"

SERVICES = [
    ("ai-workflow-automation", "AI Workflow Automation"),
    ("website-system-integration", "Website and System Integration"),
    ("business-ai-assessment", "Business AI Assessment"),
    ("corporate-ai-training", "Corporate AI Training"),
]

INDUSTRIES = [
    ("medical-clinics", "AI for Medical Clinics"),
    ("construction-trades", "AI for Construction and Trades"),
    ("property-management", "AI for Property Management"),
    ("professional-services", "AI for Professional Services"),
]


def meta(page: Path, name: str) -> str:
    """Extract a <meta name=...> content value."""
    html = page.read_text(encoding="utf-8")
    m = re.search(rf'<meta\s+name="{name}"\s+content="([^"]*)"', html)
    return m.group(1) if m else ""


def title_of(page: Path) -> str:
    m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else ""


def breadcrumb(items):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
            for i, (n, u) in enumerate(items)
        ],
    }


def org_ref():
    return {"@id": ORG_ID}


def graph(*nodes):
    return json.dumps(
        {"@context": "https://schema.org", "@graph": [org_ref(), *nodes]},
        ensure_ascii=False,
        indent=2,
    )


def script_tag(payload: str) -> str:
    return f'<script type="application/ld+json">\n{payload}\n</script>\n</head>'


def inject(page: Path, payload: str) -> bool:
    html = page.read_text(encoding="utf-8")
    if "application/ld+json" in html:
        print(f"  SKIP (has JSON-LD): {page.relative_to(ROOT)}")
        return False
    if "</head>" not in html:
        print(f"  SKIP (no </head>):  {page.relative_to(ROOT)}")
        return False
    page.write_text(html.replace("</head>", script_tag(payload), 1), encoding="utf-8")
    print(f"  OK: {page.relative_to(ROOT)}")
    return True


def main() -> int:
    changed = 0

    # ---- services/index.html -------------------------------------------------
    p = ROOT / "services/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/services/#webpage",
                "url": f"{SITE}/services/",
                "name": "AI Services for Sydney Businesses",
                "description": meta(p, "description"),
                "isPartOf": {"@id": f"{SITE}/#website"},
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("Services", f"{SITE}/services/")]),
            },
            {
                "@type": "ItemList",
                "name": "Snail AI services",
                "itemListOrder": "https://schema.org/ItemListUnordered",
                "numberOfItems": len(SERVICES),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "item": {
                            "@type": "Service",
                            "name": name,
                            "url": f"{SITE}/services/{slug}/",
                            "provider": org_ref(),
                            "areaServed": {"@type": "City", "name": "Sydney"},
                        },
                    }
                    for i, (slug, name) in enumerate(SERVICES)
                ],
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- services/<slug>/index.html -----------------------------------------
    for slug, name in SERVICES:
        p = ROOT / f"services/{slug}/index.html"
        if not p.exists():
            continue
        nodes = [
            {
                "@type": "Service",
                "@id": f"{SITE}/services/{slug}/#service",
                "name": name,
                "description": meta(p, "description"),
                "url": f"{SITE}/services/{slug}/",
                "serviceType": name,
                "provider": org_ref(),
                "areaServed": [
                    {"@type": "City", "name": "Sydney"},
                    {"@type": "AdministrativeArea", "name": "New South Wales"},
                ],
                "audience": {"@type": "BusinessAudience", "audienceType": "Small and medium business"},
            },
            breadcrumb(
                [
                    ("Home", f"{SITE}/"),
                    ("Services", f"{SITE}/services/"),
                    (name, f"{SITE}/services/{slug}/"),
                ]
            ),
        ]
        changed += inject(p, graph(*nodes))

    # ---- industries/index.html ----------------------------------------------
    p = ROOT / "industries/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/industries/#webpage",
                "url": f"{SITE}/industries/",
                "name": "AI Implementation by Industry",
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("Industries", f"{SITE}/industries/")]),
            },
            {
                "@type": "ItemList",
                "name": "Industries served",
                "itemListOrder": "https://schema.org/ItemListUnordered",
                "numberOfItems": len(INDUSTRIES),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i + 1,
                        "item": {
                            "@type": "WebPage",
                            "name": name,
                            "url": f"{SITE}/industries/{slug}/",
                        },
                    }
                    for i, (slug, name) in enumerate(INDUSTRIES)
                ],
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- industries/<slug>/index.html ---------------------------------------
    for slug, name in INDUSTRIES:
        p = ROOT / f"industries/{slug}/index.html"
        if not p.exists():
            continue
        nodes = [
            {
                "@type": "WebPage",
                "@id": f"{SITE}/industries/{slug}/#webpage",
                "url": f"{SITE}/industries/{slug}/",
                "name": title_of(p),
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "about": {"@type": "Thing", "name": name.replace("AI for ", "")},
            },
            breadcrumb(
                [
                    ("Home", f"{SITE}/"),
                    ("Industries", f"{SITE}/industries/"),
                    (name, f"{SITE}/industries/{slug}/"),
                ]
            ),
        ]
        changed += inject(p, graph(*nodes))

    # ---- about/index.html ----------------------------------------------------
    p = ROOT / "about/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "AboutPage",
                "@id": f"{SITE}/about/#webpage",
                "url": f"{SITE}/about/",
                "name": "About Snail AI",
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("About", f"{SITE}/about/")]),
            },
            {
                "@type": "Person",
                "@id": f"{SITE}/about/#founder",
                "name": "Robin Luo",
                "jobTitle": "Founder and Business AI Implementation Lead",
                "worksFor": org_ref(),
                "workLocation": {"@type": "City", "name": "Sydney"},
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- contact/index.html --------------------------------------------------
    p = ROOT / "contact/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "ContactPage",
                "@id": f"{SITE}/contact/#webpage",
                "url": f"{SITE}/contact/",
                "name": "Contact Snail AI",
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("Contact", f"{SITE}/contact/")]),
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- case-studies/index.html --------------------------------------------
    p = ROOT / "case-studies/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/case-studies/#webpage",
                "url": f"{SITE}/case-studies/",
                "name": "Case Studies",
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("Case Studies", f"{SITE}/case-studies/")]),
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- insights/index.html ------------------------------------------------
    p = ROOT / "insights/index.html"
    if p.exists():
        nodes = [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/insights/#webpage",
                "url": f"{SITE}/insights/",
                "name": "Insights",
                "description": meta(p, "description"),
                "publisher": org_ref(),
                "breadcrumb": breadcrumb([("Home", f"{SITE}/"), ("Insights", f"{SITE}/insights/")]),
            },
        ]
        changed += inject(p, graph(*nodes))

    # ---- Business AI Scan: fix missing meta ---------------------------------
    scan = ROOT / "business-ai-scan/start.html"
    if scan.exists():
        html = scan.read_text(encoding="utf-8")
        if 'rel="canonical"' not in html:
            html = html.replace(
                "<title>Business Opportunity Scan — Snail AI</title>",
                "<title>Business AI Scan — Free 10-Minute AI Opportunity Review | Snail AI</title>",
            )
            add = (
                '<meta name="description" content="Answer 25 questions in about 10 minutes and get a '
                'prioritised AI opportunity report for your Sydney business — no cost, no obligation.">\n'
                f'<link rel="canonical" href="{SITE}/business-ai-scan/start.html">\n'
                '<meta property="og:type" content="website">\n'
                '<meta property="og:title" content="Business AI Scan | Snail AI">\n'
                '<meta property="og:description" content="Free 10-minute scan. Get a prioritised AI '
                'opportunity report for your business.">\n'
                f'<meta property="og:url" content="{SITE}/business-ai-scan/start.html">\n'
                '<meta property="og:site_name" content="Snail AI">\n'
            )
            html = html.replace("</title>", "</title>\n" + add, 1)
            scan.write_text(html, encoding="utf-8")
            print("  OK (meta fixed): business-ai-scan/start.html")
            changed += 1
        else:
            print("  SKIP (has canonical): business-ai-scan/start.html")

    print(f"\nChanged: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
