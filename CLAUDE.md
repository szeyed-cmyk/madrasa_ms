# CLAUDE.md — Madrasa Pro 1.0.8

**Key facts (1.0.8):** roles admin / teacher / student are enforced on the server. Every `/api` route sits on one
router with `Depends(csrf_protect)` (`app/api/__init__.py`) and declares `Depends(require_admin)`,
`Depends(require_staff)` or `Depends(current_user)`; all 57 write routes use `require_admin` or `require_staff`, and
every DELETE is `require_admin` except removing a subject from a student (staff + `ensure_student_access`).
Teacher scope = `teacher_subjects` + `routine_slots` (`services.teacher_scope`); marks: `services.can_enter_marks`.
Queries are SQLAlchemy expressions only (no `text()`/f-string SQL outside the whitelisted migration DDL). Demo mode
(`DEMO_MODE`, old name `DEMO_AUTO_LOGIN`) is off by default, refused with production settings, re-seeds the DB on
every start, shows one-click role buttons on `/login` and never stores secrets typed in Settings.
1.0.5 map: `/` = `templates/landing.html` (public), `/dashboard` = the admin SPA; settings API in `app/api/integrations.py`
(`app/integrations.py` field specs, `app/secret_store.py` Fernet, `app/theme.py` brand colours, `app/i18n.py` +
`app/locales/*.json`; templates call `t('key', 'English')`, JS `MA.t()`; run `python tools/extract_i18n.py` after
adding texts).
Evidence: `docs/SECURITY-EVIDENCE.md`, `docs/ROUTES.md`, `docs/DEPENDENCY-AUDIT.md`. Tests: 484 app + 79 root.

Guide for developers (and AI coding assistants) working on this code base.

## Architecture
- **Backend:** Python 3.11+ / FastAPI. One process (`main.py` runs uvicorn) serves HTML pages, print views,
  a JSON API under `/api` and static files.
- **Database:** SQLite through SQLAlchemy 2 ORM (`app/models.py`). WAL mode and foreign keys are switched on
  per connection. `app/database.py:migrate()` runs numbered migrations recorded in `schema_migrations`
  (1 = add missing tables/columns, 2 = FK indexes, 3 = login_attempts) and backs the file up to `data/backups/`
  before a one-time migration. Every FK is indexed and has an explicit ON DELETE rule. No Alembic needed.
- **Frontend:** server-rendered Jinja2 templates + Alpine.js (bundled in `static/vendor/`, no CDN).
  `templates/index.html` + `static/js/app.js` (thin shell) + `static/js/admin/*.js` (one mixin per page:
  students, exams, attendance, fees, routine, classes, accounts, settings) is the admin/teacher single-page UI. `templates/student.html` + `static/js/student.js` is the student profile hub.
  `static/js/common.js` (`window.MA`) wraps `fetch` (CSRF header, error messages), toasts, formatting, form blanks
  and the ONE credential-slip builder (`MA.credRow`, `MA.credRows`, `MA.printSlips`) used by admin and student pages.
  Print views (`/print/...`) are plain server-rendered templates (auto-escaped).
- **Auth:** Starlette `SessionMiddleware` (signed cookie `madrasa_session`), roles `admin`, `teacher`, `student`.
  PBKDF2-SHA256 (600k iterations), forced first-login password change, login throttle stored in the
  `login_attempts` table (survives restarts, shared by workers).
- **CSRF:** a per-session token. API: `X-CSRF-Token` header (router-level dependency `csrf_protect`).
  Forms: hidden `csrf_token` field checked with `check_csrf`.
- **Config:** environment variables, optionally from `.env` in the project folder (`app/config.py`).
  All paths resolve from `BASE_DIR` = the `Madrasa Admin Project` folder (via `Path(__file__)`), so the app
  works from any working directory and on Windows paths with spaces.

## Folder map
```
<package root>/
├── README.md, HowToSetup.md, CLAUDE.md, CHANGELOG.md, LICENSE-NOTE.md
├── .env.example            every setting (same file as in the project folder)
├── Dockerfile              builds only "Madrasa Admin Project/" into /app (python:3.12.16-slim, pinned by digest)
├── docker-compose.yml      one service "web", named volume madrasa-data -> /app/data, .env optional
├── render.yaml, GITHUB-RENDER.md   optional Render deployment
├── database/schema.sql     CREATE TABLE statements = app/models.py (checked by tests/)
├── database/seed.sql       demo data (same as app/seed.py with SEED_DEMO_DATA=true)
├── docs/ROUTES.md          every route and its role guard (write-route table at the top)
├── docs/SECURITY-EVIDENCE.md, DEPENDENCY-AUDIT.md, DATASHEET.md, api.md, erd.md
├── docs/FIXES-v1.1.0.md    the problems found in 1.0 and how they were fixed
├── docs/screenshots/
├── tests/                  package checks (run from the root: py -m pytest tests)
├── pytest.ini, ruff.toml   settings for the root checks (ruff.toml extends the project's)
└── Madrasa Admin Project/
    ├── main.py             entry point: py main.py (reads HOST/PORT)
    ├── start.bat / start.ps1 / start.sh   create venv with py/python3, install requirements.lock, run
    ├── requirements.txt    direct runtime dependencies (pinned)
    ├── requirements.lock   full hashed lockfile (pip install --require-hashes -r requirements.lock)
    ├── requirements-dev.txt / requirements-dev.lock  + pytest, httpx2, ruff, pip-audit (hash-locked)
    ├── package.json / package-lock.json  optional: build:css, build:vendor (Node 18+)
    ├── runtime.txt         python-3.12.16
    ├── app/
    │   ├── __init__.py     __version__
    │   ├── config.py       settings, BASE_DIR, .env loader, secret key file
    │   ├── database.py     engine, SessionLocal, get_db, migrate()
    │   ├── models.py       all tables (Student is the central record)
    │   ├── schemas.py      Pydantic input models and validation
    │   ├── security.py     hashing, sessions, CSRF, role dependencies, login throttle
    │   ├── grading.py      grading scales (standard 4.00, Bangladesh 5.00) and GPA
    │   ├── services.py     shared queries: results, attendance, fees, routine (periods, assignments, slots, can_enter_marks)
    │   ├── seed.py         first-run data and demo data
    │   ├── demo.py         demo mode: demo accounts with published passwords, DB reset with safety checks
    │   ├── api/            JSON API (/api/...): __init__ (router + csrf), _common, dashboard, students, exams,
    │   │                   academics, attendance, fees, school_settings, accounts, routine
    │   └── main.py         FastAPI app, middleware, error handlers, pages, print views
    ├── templates/          Jinja2 pages, print layouts; _icons.html (SVG icon macro), _routine_view.html (shared routine grid)
    ├── static/             app.css (prebuilt Tailwind), js/ (common.js has MA helpers + routineMixin), vendor/alpine.min.js, favicon.svg
    ├── frontend/           Tailwind source (only to rebuild app.css)
    ├── sample/             students-import-sample.csv
    ├── tools/              gen_schema_sql.py (schema.sql + seed.sql), copy-alpine.cjs
    ├── data/               ships ONLY .gitkeep + README.txt; runtime: madrasa.db, backups/, .secret_key (never commit)
    └── tests/              pytest suite (test_guards_v104.py = guards/IDOR/SQL evidence, test_demo_v104.py = demo)
```

## Conventions
- **Every mutating API route** must depend on `require_admin` or `require_staff` (both include
  `current_user`), and the router adds `csrf_protect`. Read routes for per-student data must call
  `ensure_student_access(user, student_pk, db)` (admin: all, teacher: own classes, student: own record), and
  student lists must go through `_scoped()` (`services.student_condition`) so teachers only get their classes;
  class/section pickers use `_check_class_scope()`. Page routes use `page_user(request, db, roles)`.
  Update `docs/ROUTES.md` when you add a route; `tests/test_package_layout.py` checks both rules.
- **Models change => run `python tools/gen_schema_sql.py`** (rewrites `database/schema.sql` and `seed.sql`). New columns need a
  scalar default or `nullable=True` so `migrate()` can add them to old databases.
- Validation lives in Pydantic models in `schemas.py`; return readable messages (they are shown as toasts).
- Never render user input with `|safe` or `x-html`; templates rely on Jinja2 auto-escaping and Alpine `x-text`.
- Keep the UI working offline: no CDN links; vendor files go into `static/vendor/`.
- Links/buttons that only some roles may use: render them conditionally (`{% if user.role == 'admin' %}` or
  `<template x-if>`), not only hidden with `x-show`, so no user ever gets a link that answers 403.
- Style: ruff (`ruff.toml`, line length 120, py311 target). Windows users run Python as `py`.
- Version number: `app/__init__.py` and `CHANGELOG.md`.
- Credit line: "Developer: Syed Abue Tayeb Al-Zeyed" only (no contact details in the code or docs).
- **Mobile first** (1.2.0): every page must fit 360 px without horizontal page scrolling. Wide tables go inside a
  `.scroll-x` box or get a card layout below `md`; controls use `.btn`/`.input` (44 px tall, 16 px text on phones).
  The sidebar is an off-canvas drawer below `lg` (`navOpen` in the Alpine component). Print layouts are separate
  (`_print_base.html`) and not affected.
- **Routine rules** live in `app/api/routine.py` (`save_slot`): working day, no break, section belongs to class, teacher must be
  assigned (`services.is_assigned`), no double booking. Marks: `services.can_enter_marks` (admin always).
- The design system is in `frontend/input.css` (`@layer components`); rebuild `static/app.css` after changes
  (`npm ci && npm run build:css`; Node 18+).
- **Temporary passwords** (new teacher, reset, student logins) come from `services.temp_password()`, are returned
  once by the API and set `must_change_password`. Never store or log them in clear text.

## How to run the tests
From `Madrasa Admin Project`:
```bat
py -m pip install --require-hashes -r requirements-dev.lock
py -m pytest                 :: 484 tests, uses a temporary database (tests/conftest.py)
py -m ruff check .
py -m ruff format --check .
py -m compileall -q app tests main.py
py -m pip_audit -r requirements.lock --require-hashes --disable-pip
```
From the package root (needs the same venv):
```bat
py -m pytest tests           :: layout, forbidden files, schema.sql == models, seed.sql loads, route guards
```
Regenerate the lockfile after changing `requirements.txt`:
`uv pip compile requirements.txt --generate-hashes --universal --python-version 3.11 -o requirements.lock`
(or `pip-compile --generate-hashes`), then run pip-audit again.

## Running locally
`py main.py` (or `start.bat`) then open http://localhost:8000. A fresh database has no accounts: every page (also the landing page `/`) redirects to the
first-run `/setup` page (app name, tagline, administrator username + password); `/setup` returns 404 once an admin
exists. Demo: `DEMO_MODE=true SEED_DEMO_DATA=true py main.py` (see README *Demo access*). Optional `ADMIN_USERNAME` + `ADMIN_PASSWORD` env vars create the admin on start instead (Docker/Render).
The app name/tagline live in `school_settings` and reach every template through `brand_context()` in `app/main.py`.
Health check: `GET /healthz`.

Developer: Syed Abue Tayeb Al-Zeyed
