# Madrasa Pro 1.0.8 — datasheet

| Item | Value |
|---|---|
| Product | Madrasa Pro — School & Madrasa Management System (web app, full source) |
| Version | 1.0.8 |
| Live demo | https://madrasa-ms.onrender.com/ (landing page > **Live Demo** > Demo sign-in cards, or Take the tour) |
| Stack | Python 3.11+ (3.12 recommended) · FastAPI 0.165 · Starlette 1.10 · SQLAlchemy 2.1 · SQLite (WAL, foreign keys on) · Jinja2 · Alpine.js 3.17.5 (bundled) · Tailwind CSS 3.4.19 (prebuilt `static/app.css`) · cryptography (Fernet for stored API secrets) |
| Runs on | Windows (start.bat / start.ps1), Linux/macOS (start.sh), VPS + nginx + HTTPS, Docker / docker compose, Render |
| Node.js | Not needed to run. Node 18+ only to rebuild the CSS or re-copy Alpine.js (`npm ci && npm run build`) |
| Roles | Admin, Teacher (own classes only), Student (own record only), enforced on the server |
| Settings | Branding (name, logo, colours), currencies, languages (English, Bangla, Arabic RTL + translation editor), SMTP email with test, Stripe / PayPal / SSLCommerz / bKash, SMS gateway; secrets encrypted |
| Database | SQLite file `data/madrasa.db`, created and migrated automatically (numbered migrations, backup before each) |
| Tests | 400+ pytest tests (role guards on every route, IDOR, demo safety, schema = models, no secrets) |
| Dependencies | Exact pins + hash lock; pip-audit and npm audit: 0 known vulnerabilities (`docs/DEPENDENCY-AUDIT.md`) |
| Licence | Single-site licence (`LICENSE-NOTE.md`) |
| Developer | Syed Abue Tayeb Al-Zeyed |

## Demo access

| Role | Account | Password | Enter with |
|---|---|---|---|
| Admin | `demo.admin` | none | **Log in as Administrator** on `/login` (Live Demo button on the landing page) |
| Teacher | `demo.karim` — Abdul Karim (Math, Science in the Grade classes) | none | **Log in as Teacher** on `/login` |
| Student | `demo.student` — Ahmed Rahman, Grade 1 A | none | **Log in as Student** on `/login` |

- The demo accounts are password-less (sentinel hash that never verifies); they only work through the demo buttons,
  which exist only when `DEMO_MODE=true` (old name `DEMO_AUTO_LOGIN`). Nobody is logged in automatically. Demo passwords: Admin@2026, Teacher@2026, Student@2026 (set only in demo mode).
- **Re-seeded on every restart.** On each start in demo mode the SQLite file is deleted and recreated with:
  20 classes (Grade 1–10, Hifz Level 1–10) with sections · subjects with class defaults · 7 periods incl. a break ·
  a full weekly **timetable** for 3 sections with 4 sample teachers · 36 students · **attendance** for the last 4 weeks ·
  a published *1st Term* exam with **marks and results** (GPA, merit, one failing subject) · **fee plans** for every
  class and six months of **payments** with receipts. Anything a visitor changes is gone after the next restart.
- Demo settings (Render dashboard of the demo service only): `DEMO_MODE=true`, `SEED_DEMO_DATA=true`,
  `COOKIE_SECURE=false`, no `ADMIN_USERNAME`/`ADMIN_PASSWORD`. The app refuses any other combination.

## Real installs

- No demo accounts and no default password: the first start opens `/setup` to create your administrator.
- `SEED_DEMO_DATA=false` and `DEMO_MODE=false` are the defaults (`.env.example`, `render.yaml`).

Developer: Syed Abue Tayeb Al-Zeyed
