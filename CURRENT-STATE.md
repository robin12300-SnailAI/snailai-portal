# Snail AI Portal — Current State Audit

**Date**: 2026-08-23
**Author**: WorkBuddy (for Robin Luo)
**Purpose**: Baseline for Business Opportunity Scan feature addition

---

## 1. Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python + Flask | 3.13 / 3.0+ |
| WSGI | Gunicorn | 4 workers, 120s timeout |
| Database | SQLite | Single file, persistent disk |
| Frontend | Static HTML + CSS + vanilla JS | No build step |
| PDF | PyMuPDF (vendored wheel) | 1.28.2 |
| Payments | Stripe | 8.0+ |
| Scheduler | APScheduler | 3.10+ |
| Encryption | PyCryptodome | 3.20+ |
| HTTP Client | Requests | 2.31+ |

## 2. Deployment

| Item | Value |
|------|-------|
| Platform | Render (Starter plan) |
| Service name | `snailai-portal-1` |
| Service ID | `srv-d975jj0k1i2s73a5k2n0` |
| Region | Singapore |
| Root dir | `server/` |
| Build | `pip install -r requirements.txt` |
| Start | `gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 app:app` |
| Persistent disk | 1GB at `/data` |
| Database path | `/data/snailai.db` (env `DB_PATH`) |
| Domain | `snailai.ai` (apex) + `www.snailai.ai` (301→apex) |
| SSL | Automatic (Render) |

## 3. Database Tables (18 existing)

| Table | Purpose |
|-------|---------|
| users | Student/TA/Instructor/Admin accounts |
| capabilities | AI capability checklist items |
| checks | Student capability check-offs |
| sessions | Login session tokens (7-day TTL) |
| ai_needs | AI刚需 submissions |
| directory | Contact directory |
| points_log | Growth points ledger |
| points_config | Points per capability |
| assistant_assignments | TA↔student assignments |
| login_events | Login audit log |
| congrats_log | Congratulations log |
| page_views | Page view analytics |
| qa_threads | Q&A forum threads |
| qa_replies | Q&A forum replies |
| rate_limits | Sliding-window rate limiting |
| quote_confirmations | Quote/business confirmations |
| agreements | E-sign agreement templates |
| agreement_signers | E-sign signer records |
| agreement_events | E-sign audit events |

## 4. API Routes (50+)

### Public
- `POST /api/login`, `POST /api/logout`
- `GET /api/capabilities`, `GET /api/students`, `GET /api/directory`
- `GET /api/qa/threads`, `POST /api/qa/threads`, `GET /api/qa/threads/<id>`
- `POST /api/qa/replies`, `POST /api/activity`, `POST /api/track/pageview`
- `POST /api/quote/confirm`
- `GET /api/sign/info/<token>`, `GET /api/sign/pdf/<token>`
- `POST /api/sign/sign/<token>`, `POST /api/sign/share/<token>`
- `POST /api/create-checkout-session`, `GET /api/verify-session`

### Authenticated (token required)
- `GET /api/me`, `GET /api/me/token`, `GET /api/me/growth`
- `PUT /api/checks/<username>/<cap_id>`
- `POST /api/change-password`
- `GET /api/congrats/<username>`, `GET /api/congrats/student/<username>`

### Admin
- `GET/POST /api/admin/users`, `PUT /api/admin/users/<username>/role`
- `POST /api/admin/reset-password`
- `GET /api/admin/tables`, `GET /api/admin/table/<name>`
- `GET/POST/PUT/DELETE /api/admin/assistant-assignments`
- `GET /api/admin/analytics/*` (summary, logins, geo, pages, extra, report)
- `POST /api/admin/leaderboard/test`
- `POST /api/sign/admin/create`, `POST /api/sign/admin/cleanup`, `POST /api/sign/admin/lookup`
- `POST /api/quote/admin/cleanup`, `POST /api/quote/admin/test-user`
- `POST /api/portal/admin/send-portal-email`

### Internal
- `GET/POST /wecom_callback` — WeChat Work webhook
- `GET /WW_verify_*.txt` — WeChat Pay verification

## 5. Static File Serving

Flask serves ALL static files via catch-all route (`/<path:path>`), including:
- `index.html` (desktop homepage, 85KB)
- `mobile.html` (mobile homepage, 81KB)
- `login.html`, `welcome.html`, `dashboard.html`, `lesson.html`
- Sub-directories: `faq/`, `online-course/`, `offline-course/`, `qa/`, `ta/`, `enterprise/`, `corporate-training/`, `admin/`, `portal/`, `blog/`, `payment/`, `sign/`, `guide/`, `assets/`, etc.

## 6. Email Infrastructure

- **SMTP**: Gmail SMTP SSL (smtp.gmail.com:465)
- **Auth**: `GMAIL_USER` + `GMAIL_APP_PASSWORD` env vars
- **From addresses**: 
  - `esign@snailai.ai` (agreements)
  - `quote@snailai.ai` (quotes)
  - `admin@snailai.ai` (admin notifications)
- **All are Google Workspace aliases of robin@snailai.ai**
- **Notification target**: `robin12300@gmail.com` + `robin@snailai.ai`

## 7. Auth System

- Username/password with salted SHA-256 hash
- Session tokens stored in `sessions` table, 7-day TTL
- Token passed via `Authorization: Bearer <token>` header
- Admin check: `role ∈ {admin, instructor}`
- Rate limiting: 10 login attempts/min per IP

## 8. WeChat Integration

- Outbound: WeChat Work webhook (`WECHAT_WEBHOOK_URL` env var)
- Used for: High-Fit notifications, admin alerts
- Inbound: `/wecom_callback` for verification

## 9. Existing Enterprise Pages

| Path | Content |
|------|---------|
| `/enterprise/` | English enterprise services (desktop + mobile) |
| `/corporate-training/` | Corporate training offering (desktop + mobile) |
| `/admin/` | Admin dashboard |
| `/portal/` | Client portal (login, account, tasks, progress, quotation, agreement) |

## 10. Brand Design System (Swiss Design)

- Primary accent: `#FF5B1F` (coral orange)
- Dark text: `#1A1A2E`
- Light bg: `#FCFCFA`
- No shadows, geometric blocks, badge pills, strong hierarchy
- Bilingual: `data-zh` + `data-en` attributes on all text
- Desktop + mobile paired pages must stay in sync

## 11. Gaps for Business Opportunity Scan

| Gap | Current | Needed |
|-----|---------|--------|
| AI model integration | None | GLM5.3 API adapter |
| PDF generation | PyMuPDF (for e-sign only) | weasyprint for report rendering |
| CAPTCHA | Rate limiting only | Cloudflare Turnstile |
| Transactional email (English) | Gmail SMTP (Chinese quote/sign emails) | English scan report email template |
| Secure token-based public links | E-sign signer tokens | Scan report secure tokens |
| Multi-step form | None | 7-step wizard with auto-save |
| Knowledge base | None | 3 industry YAML/markdown files |
| Scoring engine | None | Deterministic Lead Fit + Opportunity scoring |
| Admin scan management | None | Scan list, detail, actions |
| Privacy notice (English) | None | `/business-opportunity-scan/privacy/` |
| Analytics events | Page views only | Scan funnel events |

## 12. Key Architecture Decisions for Scan Feature

1. **Extend existing Flask app** — add tables, routes, and scan logic to `server/app.py` (or split into `server/scan.py` module imported by app.py to keep code organized)
2. **Reuse SQLite** — add 4 new tables to same `snailai.db`
3. **Reuse SMTP** — add new From alias `scan@snailai.ai` via Google Workspace
4. **Reuse admin auth** — same `sessions` table, same `role=admin` check
5. **New directory** — `business-opportunity-scan/` for all frontend pages
6. **New Python module** — `server/scan.py` for scan-specific logic (imported by app.py)
7. **weasyprint** — add to requirements.txt for HTML→PDF report generation
8. **Cloudflare Turnstile** — add client-side widget + server-side verification
9. **GLM5.3 API** — via `AI_API_KEY` + `AI_BASE_URL` env vars
