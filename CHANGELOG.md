# Changelog

All notable changes to Madrasa Pro (Madrasa & School Admin System).

## 1.0.8 — 2026-11-28
The Demo sign-in box on `/login` is visible by default, with no `DEMO_MODE` required.

- New setting `DEMO_LOGINS` (default **true**). When on, `/login` always shows the three Demo sign-in
  boxes (Administrator, Teacher, Student, with usernames and passwords in plain text). Clicking a card
  fills the form; “Sign in with this account” fills and submits. The password field is shown as text
  so you can see it was filled.
- The three demo accounts (`demo.admin` / `Admin@2026`, `demo.karim` / `Teacher@2026`,
  `demo.student` / `Student@2026`) are created if missing, with hashed passwords. Existing non-demo
  users and school data are not wiped or changed. Set `DEMO_LOGINS=false` for a real school: the boxes
  are hidden and those three accounts are disabled.
- On a fresh install with the default on, `/login` is shown even before `/setup` (because `demo.admin`
  exists). `DEMO_MODE` still wipes and re-seeds the sample school on every start.

## 1.0.7 — 2026-11-28
Makes the public demo easy to see, and brings the landing page, Demo sign-in box and product tour closer to the
approved reference.

- `/` is always the landing page, including on a fresh install before an administrator exists (`/setup` is still
  there; **Get started** opens it). A normal `start.bat` no longer hides the landing page behind `/setup`.
- New `start-demo.bat`, `start-demo.ps1` and `start-demo.sh` start the app with `DEMO_MODE=true` and
  `SEED_DEMO_DATA=true`. The README says this is how you see the three demo accounts. `start.bat` stays the
  real-school starter (no demo boxes).
- The Demo sign-in box on `/login` uses a pink dashed border, a light pink background, and a red
  “Sign in with this account →” link. Clicking a card still fills the username and password fields above.
- The product tour control bar and tooltips follow the video-style walkthrough more closely (floating bar,
  spotlight, play/pause, chapters, Step x of N).
- Landing page: darker typographic hero, sticky nav with Live Demo and Take the tour, closer in structure to
  a product marketing site, still with no contact details.

## 1.0.6 — 2026-11-28
A landing page built to sell, Payora-style demo sign-in cards, and a self-hosted product tour. The rest of the
application is unchanged from 1.0.5.

### Landing page
- Redesigned public landing page at `/`: sticky navigation, a stronger hero with Live Demo and Take the tour
  buttons and a real product mockup, trust/stats, a features grid for every module, role sections, screenshot
  tabs, benefits, a how-it-works sequence, technology, an FAQ, a final call to action and a footer.
- Scroll-reveal animations, responsive layouts, and the existing language / right-to-left support. No contact
  details, emails, phone numbers, URLs or social links. Footer credit: only "Developer: Syed Abue Tayeb Al-Zeyed".

### Demo sign-in
- When `DEMO_MODE=true`, a **Demo sign-in** box appears under the login form, with a card for Administrator,
  Teacher and Student. Each card shows the username and password and a "Sign in with this account" action.
  Clicking a card fills the form above; the action submits it.
- Demo accounts now have real hashed passwords, set only in demo mode: `demo.admin` / `Admin@2026`,
  `demo.karim` / `Teacher@2026`, `demo.student` / `Student@2026`. Outside demo mode those passwords are never
  stored (the accounts keep the no-password sentinel and cannot use the password form).
- Direct one-click sign-in (`POST /demo/login`) is still available. All 1.0.5 demo safeguards remain: refused
  with production settings, a real database is never wiped, secrets are never stored in the demo.

### Product tour
- New `/tour` page (and `/tour?autostart=1`) walks through the real app from pre-captured screenshots: dashboard,
  students, attendance, exams and results, fees, the class routine, settings, and teacher / student views.
- Spotlight, tooltips with Next / Back / Skip and "Step x of N", plus a bottom progress bar (play, pause, speed,
  chapters). Self-hosted JavaScript and CSS, no CDN, CSP-compliant. Linked from the landing page ("Take the tour")
  and the login page.

## 1.0.5 — 2026-11-27
Answers every point of the Vibe96 review SUB-2026-1065.

### 1. Images
- New cover image (first image) and 12 real screenshots of the demo, all 1920 x 1080, plus a 1080 x 1080 square
  image (`docs/screenshots/`): landing page, login with demo buttons, dashboard, students, exams & results,
  attendance, fees, payment gateways, branding, languages, Arabic RTL and the mobile layouts.

### 2. Landing page
- `/` is now a public landing page (`templates/landing.html`): hero with a dashboard preview, numbers, features,
  screenshot tabs, the three roles, benefits, technology and a call to action. The prominent **Live Demo** button
  opens `/login`. No contact details. Can be switched off in Settings > Branding (then `/` opens the app).
- The app moved from `/` to `/dashboard` (old `/` links show the landing page with a Sign in / Open dashboard
  button). A fresh install still opens `/setup` first.

### 3. Demo logins
- One-click **Log in as Administrator / Teacher / Student** buttons on the login page, only when demo mode is on.
  1.0.4 logged every visitor in automatically, so the reviewer never saw them: visitors now see the landing page
  and the login page first. The switch is now called `DEMO_MODE` (`DEMO_AUTO_LOGIN` still works).
- Richer demo data (demo mode only): 36 students, 4 weeks of attendance, six months of fee payments, marks for all.

### 4. Admin settings (database, editable in the UI)
- Tabbed Settings: General, Branding, Currencies, Languages, Email (SMTP), Payment gateways, SMS & integrations,
  Administrators.
- **Branding**: name, tagline, logo, primary + secondary colour (CSS variables, `app/theme.py`) on every page.
- **Currencies** (new `currencies` table): add / edit / delete / default (re-bases rates, sets the fee symbol);
  top-bar currency switch converts displayed amounts.
- **Languages** (new `languages` + `translations` tables): English, Bangla, Arabic (RTL) built in
  (`app/locales/*.json`), add languages, default language, translation editor, `POST /set-language`.
- **SMTP** with STARTTLS / SSL, From address and a test-email button; **Stripe, PayPal, SSLCommerz, bKash** with
  on/off, test/live mode and masked keys (switched-on gateways become fee payment methods); **SMS** gateway.
  New `app_settings` table; secrets encrypted with Fernet (`app/secret_store.py`, key from `SECRET_KEY`), never
  returned by the API. Demo mode never stores secrets and sends no email.
- Migration 4 adds the tables and the new `school_settings` columns (backup first, as before).

### 5. Premium redesign
- New design system (Inter + Plus Jakarta Sans, bundled with their OFL licences), grouped dark sidebar, top bar,
  dashboard with stat cards and charts (fees, attendance donut, attendance trend, students per class), skeleton
  loaders, a loading bar, new toasts, empty states, restyled login / setup / error / change-password pages; checked
  on desktop, tablet and phone. No inline event handlers (CSP-safe).

### Tests and tooling
- New `tests/test_v105.py` (29 tests): landing page, demo buttons and `DEMO_MODE`, secret encryption and masking,
  SMTP / payments / SMS validation and guards, demo secret skipping, currencies, languages, translations, RTL,
  set-language safety, branding colours, dashboard data, no inline handlers. Existing tests follow `/dashboard`.
- New dependency `cryptography` (hash-pinned in both lock files). `tools/extract_i18n.py` rebuilds the English
  catalogue and lists missing translations.
- Results: 484 application tests + 79 package tests pass, ruff check/format clean, pip-audit and npm audit report
  no known vulnerabilities, Playwright browser checks (desktop, phone, Arabic RTL) show no console errors.

## 1.0.4 — 2026-11-26
Fixes every finding of the Vibe96 audits #3278 (listing 1.0.1) and #3282 (listing 1.0.3).

**Version numbering:** the Vibe96 listing uses 1.0.x. The internal builds 1.1.0–1.3.0 below are the code of
listing versions 1.0.0–1.0.3; 1.0.4 continues from 1.3.0.

### Security and access control
- Demo mode documented for all three roles (`demo.admin`, `demo.karim`, `demo.student`, password-less, buttons on
  `/login`) and locked down: the app refuses to start with `DEMO_AUTO_LOGIN=true` plus `COOKIE_SECURE=true`,
  `SEED_DEMO_DATA=false` or `ADMIN_USERNAME`/`ADMIN_PASSWORD`; it never wipes a database that holds a real
  administrator; a loud warning is logged. The demo DB is re-seeded on every start (classes, timetable,
  attendance, results, fees) — tested in `tests/test_demo_v104.py`.
- `render.yaml` is now buyer-safe (`DEMO_AUTO_LOGIN=false`, `SEED_DEMO_DATA=false`); demo settings are documented
  for a separate demo service only.
- Login throttle persisted in the new `login_attempts` table (survives restarts, shared by workers).
- `data/` ships only `.gitkeep` + `README.txt`; `data/.secret_key`, `*.db` and `.env` can never ship
  (`**/data/*` in `.gitignore`/`.dockerignore`, removed in the Dockerfile, checked by the root tests).
- New `tests/test_guards_v104.py`: shared guard on every write and DELETE route, teacher marks/attendance scope,
  IDOR on student and receipt ids, `Cache-Control: no-store` on password responses, temporary passwords only
  hashed (raw DB scan), sentinel never verifies, no `text()`/f-string SQL, every bulk delete has a WHERE.

### Database
- Every foreign key declares ON DELETE (CASCADE / RESTRICT / SET NULL); schema.sql lists all 24 FKs with their
  index and rule at the top. Migration 3 (numbered, backed up first). `tools/gen_schema_sql.py` regenerates
  `schema.sql` and `seed.sql` without string-built SQL. Demo mode check uses SQLAlchemy instead of raw SQL.
- Demo attendance is also seeded in the first days of January.

### Structure
- `app/api.py` (1,900 lines) split into `app/api/` domain routers: dashboard, students, exams, academics,
  attendance, fees, school_settings, accounts, routine (+ `_common`). Each module lists its routes and guards.
- `static/js/app.js` split into a thin shell + `static/js/admin/*.js` feature mixins. One credential-slip builder
  (`MA.credRow` / `MA.credRows` in `common.js`) is used by the teacher, student-login, bulk-login and student pages.
- Student profile: students now see a read-only hint under their marks (the "marks save automatically" hint is
  for staff only).

### Dependencies and build
- Pins updated to current patches (fastapi 0.165.0, sqlalchemy 2.1.9, python-multipart 0.0.34, pydantic 2.14.4);
  `requirements.lock` regenerated with hashes for all 19 packages; new `requirements-dev.lock`. pip-audit and
  npm audit: 0 known vulnerabilities (`docs/DEPENDENCY-AUDIT.md`).
- `package.json` now pins `alpinejs` 3.17.5 = the vendored file (byte-identical); real `package-lock.json`;
  `npm run build:vendor` / `build:css`; Node 18+ only needed to rebuild.
- Dockerfile: `python:3.12.16-slim` pinned by digest; no landing folder. Compose `.env` optional
  (`required: false`). Both `.env.example` files identical, with every setting.

### Docs
- README: demo access table at the top and an audit-evidence index. New `docs/SECURITY-EVIDENCE.md`,
  `docs/DEPENDENCY-AUDIT.md`, `docs/DATASHEET.md`; `docs/ROUTES.md` starts with the write-route guard table.

## 1.3.0 — 2026-11-23
### Added
- **Teachers page** (admin menu *Teachers*): every teacher with phone, login status (Active / First login pending /
  Disabled / No password yet), last login, assigned subjects and classes and periods per week. Add a teacher (full
  name, username, optional phone, initial password typed or **generated**), edit, **reset password**, enable or
  disable the login, and jump to *Assign subjects*. Duplicate usernames (any letter case) and weak passwords are
  refused. New and reset teachers must choose their own password at first login.
- **Student logins page** (admin menu *Student logins*): login status of every student per class/section; create,
  reset, disable or enable a login; **bulk-create logins for a whole class or section** (username = 6-digit
  student ID, optional reset of existing logins). Temporary passwords are shown **once** in a credentials window
  with **printable login slips** and a CSV download; only hashes are stored. The student list has a *Login* button
  and the profile's Login tab can enable a login again and print a slip.
- **School logo**: a dedicated *School logo* card in Settings (preview, Change, Remove, saved at once) and an
  optional logo upload on the first-run setup page. Shown on the login page, menu and printouts.
- Role-based menus: teachers see *My students, My routine, My subjects, Marks & results, Attendance*; students see
  *My profile, My results, My attendance, My fees, Class routine*.
- New API routes: `/api/teachers/manage`, `POST /api/teachers`, `PUT /api/teachers/{id}`,
  `/api/teachers/{id}/reset-password`, `/api/teachers/{id}/status`, `/api/student-logins`,
  `/api/student-logins/bulk`, `/api/students/{id}/enable-login` (all admin only, CSRF protected).
- `users.phone` column (optional staff phone). Existing 1.2.0 databases get it automatically at start-up (no data
  is changed).
- 21 new tests (`tests/test_roles_v130.py`) for teacher management, bulk logins, teacher scope, student IDOR,
  the logo and the migration.

### Changed (security)
- **Teachers only see their own classes, enforced on the server.** A teacher's classes are the classes/sections of
  their subject assignments and routine periods. Students list, student profile/page/result card, attendance (read
  and save), marks sheet, results, class list, class routine, printouts and dashboard numbers are limited to those
  classes; anything else answers 403. `/api/teachers` and `/api/assignments` return only the teacher themselves.
  A teacher's dashboard activity shows only their own attendance and marks entries.
- Teachers can change a student's subjects only for students of their classes.
- Resetting a student login without typing a username keeps the current username (1.2.0 switched it back to the
  student ID). Generated passwords are now 10 readable characters (no 0/O, 1/l/I).
- Settings: *Staff accounts* became *Administrator accounts*; teachers moved to the Teachers page.
- The *Login* card on a student's page is now rendered on the server for administrators only (it was hidden
  in the browser for teachers and students).

### Upgrade from 1.2.0
- Replace the app files and keep `data/` (database, secret key) and `.env`. On start the app adds `users.phone`.
- Teachers who have no subject assignment and no routine period see no students until you assign them.

## 1.2.0 — 2026-11-22
### Added
- **Class routine.** New menu entry *Class routine* (admin and teacher):
  - **Teacher assignments:** the admin assigns a teacher to each subject of a class, for every section or one
    section (a section-specific assignment wins). Saving again replaces the teacher.
  - **Periods:** name, start/end time and a break flag. New installations and upgraded databases start with six
    periods (08:00-13:00) and a tiffin break. Overlapping periods, end before start and turning a period that has
    classes into a break are refused; deleting a period removes its classes from the routine.
  - **Working days** in Settings (default Saturday to Thursday).
  - **Weekly grid** per class section (days x periods). Tap a period to set subject, teacher and room; the assigned
    teacher is chosen automatically. Blocked with a clear message: a teacher not assigned to the subject, a teacher
    already teaching another class at that time, breaks, non-working days and a section of another class. If an
    assignment changes later, the routine entry shows a "not assigned" badge.
  - **My routine** for teachers (admins can view any teacher) and **today's classes** on the dashboard.
    Students see their own class routine in the portal (new *Class routine* tab).
  - **Printable routines** (A4 landscape) per class section and per teacher.
- **Marks entry is limited to assigned subjects for teachers.** Other subjects are shown read-only with a lock and
  the server answers 403 ("You are not assigned to teach ... in this class"). Admins are not restricted.
  After upgrading, assign your teachers (Class routine > Teacher assignments) so they can keep entering marks.
- **Printable fee due list** (`/print/dues`, Fees > Print due list) with guardian, phone, paid, due and a
  "Contacted" column. It **replaces the SMS fee reminders**.
- Dashboard: greeting, stat cards with icons, today's classes, recent activity (attendance, marks, admissions and,
  for admins, receipts) and quick actions.
- The demo data has four **sample teachers** (disabled, no password) with subject assignments and a filled weekly
  routine for Grade 1, Grade 5 and Hifz Level 1. Give one a password with *Set password* to try a teacher login.

### Changed
- **Mobile responsive.** Every page works from 360 px phones to desktops with no sideways page scrolling: slide-in
  menu with a top bar and menu button, students as cards on phones, tables scroll inside their own box, attendance
  with four large buttons per student and a sticky save bar, marks entry *by subject* on phones (grid on larger
  screens), routine one day at a time on phones. Touch targets are 44 px and inputs use 16 px text (no zoom on iPhone).
- **New look:** cohesive design in the brand green, SVG icons, cards, nicer tables, badges, empty states, a split
  brand-panel login and setup page and visible focus rings. `static/app.css` is rebuilt locally (no CDN, works
  offline). Printouts are unchanged.
- Setup refuses an administrator username that is already used (for example by a sample teacher).
- Staff accounts show "no password yet" and offer *Set password* (sets the password and enables the account).

### Removed
- **SMS notifications (mock mode) are removed completely:** the SMS log page and menu card, test SMS, SMS to
  guardians of absent students, SMS fee reminders, `send_sms()`, and the `/api/sms`, `/api/sms/test`,
  `/api/attendance/sms-absent` and `/api/fees/reminders` routes. There were no SMS environment variables.
  Fee reminders are replaced by the printable due list.

### Upgrading from 1.1.x
Copy your `data/madrasa.db` as before. On the first start the app adds the routine tables, the default periods
and the working-days setting, and **drops the `sms_logs` table** (back up the database first if you want to keep
the old SMS log). Accounts, students, marks, attendance and fees are kept.

### Tests
- New `tests/test_routine_v120.py` (39 tests): assignments, periods, routine validations (double booking,
  unassigned teacher, breaks, non-working days, wrong section), views per role, my routine / today, prints,
  marks restriction, CSRF and login on the new routes, removed SMS routes, upgrade from a 1.1.x database.
- Existing tests updated for the SMS removal and the marks restriction; root tests check the new `seed.sql`
  (sample teachers disabled without password, periods, routine).
- Browser check (Playwright) of setup + admin, teacher and student at 360, 390, 768 and 1366 px: no page overflow,
  44 px targets and 16 px inputs on phones.

## 1.1.1 — 2026-11-21
### Changed
- **The app name is yours.** The "Madrasa Admin" text is now the app / institution name stored in the settings,
  plus an optional tagline (replaces the fixed "School & Madrasa Management System"). Both are chosen on the
  setup page and editable in Settings; they are used on the login page, menu, browser tab, error and
  password pages, the student portal, print headers and the SMS test message. Default: "Madrasa Admin".
- **No default usernames or passwords.** The `admin / admin123` and `teacher / teacher123` accounts and the
  "First run: ..." note on the login page are gone. On the first start (no administrator yet) every page,
  including `/login`, redirects to a new **first-run setup page** (`/setup`): app name, tagline, administrator
  username, full name, password + confirmation (8+ characters, not common, not the username). The administrator
  is logged in straight away and does not have to change the password again. `/setup` then answers 404 for
  GET and POST, for good.
- No demo teacher account: teachers are created by the administrator in Settings > Staff accounts (with a
  temporary password they must change at first login), students from their profile.
- The login page now says only "Teachers and students get their logins from the administrator."
- Optional `ADMIN_USERNAME` + `ADMIN_PASSWORD` environment variables create the first administrator on start
  (Docker, Render, servers). Weak or invalid values are ignored with a warning. `ADMIN_PASSWORD` alone no longer
  does anything.
- `database/seed.sql` contains no user accounts (first start shows the setup page); `schema.sql` has the new
  `school_settings.tagline` column (added automatically to existing databases).
- Docs (README, HowToSetup, GITHUB-RENDER, render.yaml, `.env.example`, `docs/ROUTES.md`) updated; screenshots
  of the setup and login pages refreshed. `static/app.css` rebuilt for the new page.

### Upgrading from 1.1.0 / 1.0
Copy your `data/madrasa.db` as before: existing accounts keep working, the setup page is not shown, and the
tagline column is added with the old default text.

### Tests
- New `tests/test_setup_v111.py`: setup page appears with no admin, creates the admin and sets the name, is
  blocked afterwards (GET and POST), needs the CSRF token, validates the form, a name change in Settings shows on
  the login page / menu / prints, environment bootstrap, and no default-credential text in the app.
- Root tests: `seed.sql` has no users and opens `/setup`, no default-credential text in docs, templates or SQL.

## 1.1.0 (Vibe96 package) — 2026-11-21
Same version, repackaged to the Vibe96 archive layout, plus four small fixes found by a full
browser click-through of every page as admin, teacher and student.

### Packaging
- All application code moved into the `Madrasa Admin Project/` folder; paths still resolve from the
  app's own folder (also on Windows and with spaces in the path).
- New at the package root: `CLAUDE.md`, `LICENSE-NOTE.md`, `.env.example` (every setting explained),
  `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore`, `render.yaml`, `GITHUB-RENDER.md`,
  `database/schema.sql`, `database/seed.sql`, `docs/ROUTES.md` (route and role-guard table), screenshots.
- `requirements.lock`: fully pinned, hash-checked lockfile; pip-audit reports no known vulnerabilities.
- `start.bat`, `start.ps1` (Windows, use `py`) and `start.sh` (Linux/macOS): create the venv and install on first run.
- `runtime.txt` (python-3.12.7).
- HowToSetup.md rewritten: Windows, Linux, VPS with nginx + HTTPS (systemd, certbot), Docker, database setup,
  first login, branding, SMS gateway, backup.
- Root `tests/` check the package layout, forbidden files, that `schema.sql` creates exactly the models'
  tables and that `seed.sql` loads, and that every mutating API route has a role guard.

### Fixed
- "Print all result cards" with no exam chosen yet (`/print/results?exam_id=`) gave a 422 error page;
  it now uses the latest exam (404 only when no exam exists). A blank `exam_id` on a single result card works too.
- The "Export CSV" link was in the teacher's page (hidden) although teachers may not export; it is now only
  rendered for admins.
- The receipt "Print" link on a student's Fees tab was in the page (hidden) for students and teachers although
  receipts are admin-only; it is now only rendered for admins.
- A mistyped address (unknown page) showed raw JSON (`{"detail":"Not Found"}`); it now shows the normal
  error page. API routes still answer JSON.
- 7 new regression tests (248 in total).

## 1.1.0 — 2026-11-15
Review-and-fix release. The full list of problems found and fixed is in `docs/FIXES-v1.1.0.md`.

### Added
- **Subject management:**
  - subject master (code, full marks, pass marks, credits, active);
  - default subjects per class, with "apply to students";
  - add or remove subjects per student;
  - subject-wise marks grid for each exam.
- **Results:**
  - grades, grade points, credit-weighted GPA, Pass/Fail/Incomplete and merit position;
  - Standard 4.00 or Bangladesh 5.00 grading scale;
  - printable result cards, one student or a whole class.
- **Student profile hub:** details, subjects and marks, attendance, fees, and portal login, all in one page.
- **Exams:** create, publish or unpublish, and delete. Students only see published exams.
- **Fees:**
  - monthly fee per class, due list, SMS reminders (mock);
  - fee month and fee type on payments;
  - void a receipt;
  - printable receipts.
- **Attendance:** sections, saved-day reload, monthly report, printable sheet, SMS to guardians of absent students (mock).
- **Students:** CSV import (with a sample file), CSV export, printable list, roll number, guardian relation, notes, delete.
- **Staff accounts:** add, reset password, disable.
- **Settings:** office phone, currency, grading scale, validated logo.
- `.env` configuration, automatic upgrade of v1.0 databases, health check at `/healthz`.

### Security
- Signed sessions (this replaces the forgeable `user` cookie).
- CSRF protection.
- Role checks on every route.
- Forced password change and password rules.
- PBKDF2 with 600k iterations and constant-time comparison.
- Login throttling.
- Security headers.
- Escaped print pages and image-only logos.
- Dependencies updated so that pip-audit is clean.

### Changed
- The database moved to `data/madrasa.db`.
- The server listens on 127.0.0.1 by default.
- CSS and JavaScript are bundled for offline use, and the layout works on phones.
- Code is split into the `app/` package.
- 241 automated tests.

## 1.0.0
- Initial version.
