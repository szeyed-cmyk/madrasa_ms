# Madrasa Pro 1.0.8 — Setup Guide

**Quick facts:** run `start.bat` (Windows) or `./start.sh` in `Madrasa Admin Project`, then open http://localhost:8000. The login page shows the Demo sign-in box by default. **For a real school set `DEMO_LOGINS=false`.** For a sample school that resets on every start, use `start-demo.bat`. Then
complete the first-run setup (name, optional logo, your admin account; no default passwords). Then add teachers on
the **Teachers** page and student logins on the **Student logins** page. Teachers only see their own classes;
students only their own data. Upgrading: replace the files, keep `data/` and `.env` (section 6).

**Prerequisites at a glance:** Python 3.11+ (3.12 recommended). **Node.js is NOT needed** to install or run: `static/app.css` (Tailwind 3.4.19) and `static/vendor/alpine.min.js` (Alpine.js 3.17.5) ship prebuilt. Node 18+ is only for rebuilding them (`npm ci && npm run build`). The `data/` folder is created automatically on first start (`mkdir(parents=True, exist_ok=True)` in `app/config.py`); it ships with only `.gitkeep` and `README.txt` — never a database or `.secret_key`. Docker needs no `.env` (it is optional).

This guide takes you from the downloaded ZIP to a working system. Pick the section that fits you:

| I want to... | Section |
|---|---|
| Run it on one Windows PC in the office | **2. Windows** |
| Run it on Linux or macOS | **3. Linux / macOS** |
| Put it online on my own server with a domain and HTTPS | **7. VPS with nginx + HTTPS** |
| Run it with Docker | **8. Docker** |

All application files are in the folder **`Madrasa Admin Project`**. Commands in sections 2, 3 and 5-6 are run
inside that folder (the one that contains `main.py`).

---

## 1. Requirements
- **Python 3.11 or newer** (3.12 recommended; the Docker image and `runtime.txt` use 3.12.16).
  - Windows: install from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**.
    Windows uses the Python launcher **`py`** (all commands below use `py`, not `python`).
    Check with: `py --version`
  - Linux: `python3 --version` (Ubuntu 22.04+: `sudo apt install python3 python3-venv`).
- Internet only for the first installation of packages. After that the app works fully offline
  (all CSS and JavaScript are bundled).
- About 100 MB of disk space. Any modern browser (Chrome, Edge, Firefox, Safari), also on phones.

## 2. Windows (one PC or a school network)

### Easiest: double-click
1. Unzip the package, for example to `C:\MadrasaAdmin`.
2. Open the `Madrasa Admin Project` folder and double-click **`start.bat`**.
   The first run creates a `venv` folder with `py` and installs the pinned packages (1-2 minutes).
3. When you see `Server is running. Open http://localhost:8000`, open that address in your browser.
4. The first time, complete the setup page (section 4). To stop the app, close the window or press `Ctrl+C`.

PowerShell users can run `.\start.ps1` instead (if it is blocked, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`).

### Manual (same result)
Open Command Prompt in the `Madrasa Admin Project` folder:
```bat
py -m venv venv
venv\Scripts\activate
py -m pip install --require-hashes -r requirements.lock
uvicorn main:app --reload
py main.py
```
Next time: `venv\Scripts\activate` then `py main.py` (or just double-click `start.bat`).

### Use it from other computers on the school network
1. Create `Madrasa Admin Project\.env` (copy `.env.example`) and set `HOST=0.0.0.0`.
2. Start the app and allow Python through Windows Firewall when asked (Private networks).
3. On other PCs/phones open `http://<this-PC-IP>:8000` (find the IP with `ipconfig`).

## 3. Linux / macOS
```bash
cd "Madrasa Admin Project"
./start.sh
```
or manually:
```bash
cd "Madrasa Admin Project"
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --require-hashes -r requirements.lock
python3 main.py
```
Open **http://localhost:8000**.

## 4. First start: setup page (no default passwords)
There are **no default usernames or passwords**. On the very first start (no administrator account yet) every
address, including `/login`, opens the **setup page** (`/setup`):

| Field | What to enter |
|---|---|
| App / institution name | The name shown on the login page, the menu, the browser tab and every printout, e.g. `Al-Noor Madrasa`. |
| Tagline (optional) | A short line under the name on the login page, e.g. `School & Madrasa Management System`. Leave empty for none. |
| School logo (optional) | PNG, JPG, GIF or WebP, max 300 KB. Shown on the login page, in the menu and on printouts. |
| Administrator username | 3-64 characters: letters, digits, `_` `.` `-` (e.g. `principal`). |
| Your full name | Optional, shown in the menu. |
| Password + confirm | At least 8 characters, not a common password and not the same as the username. |

Click **Create administrator and open the app**: the administrator is created and logged in. The setup page is
then switched off for good (it answers "not found"). Change the name and tagline any time in
**Settings > School / app profile**, and the logo in **Settings > School logo** (Change / Remove).

- **Teachers:** the administrator adds them on the **Teachers** page (*Add teacher*: full name, username, optional
  phone, a typed or generated temporary password). The teacher must choose a new password at the first login.
  Then click **Assign** to give the teacher their subjects: a teacher only sees the classes they are assigned to
  (or have routine periods in).
- **Students:** the administrator creates portal logins on the **Student logins** page, one by one or for a
  whole class at once (username = 6-digit student ID). The temporary passwords are shown **once**: print the
  login slips or download the CSV. The student changes the password at first login. (A single login can also be
  managed in **Student profile > Login**.)
- **What each role sees:** admin = everything; teacher = own classes only (students, routine, attendance, marks for
  assigned subjects, results), no fees/settings/user management; student = own profile, results, attendance, fees
  and class routine only. The server enforces this (403), not only the menu.
- The login page shows only: *"Teachers and students get their logins from the administrator."*
- With `SEED_DEMO_DATA=true` (default `false`; set it to try the app) you get 6 demo students, a published "1st Term" exam with marks,
  5 days of attendance and 3 fee payments, so you can try every screen straight away (the demo data contains
  no user accounts).
- **Server without a browser first (Docker, Render):** set `ADMIN_USERNAME` and `ADMIN_PASSWORD` (section 5)
  and the administrator is created on start instead; the setup page is then never shown.
- **Upgrading** from 1.0 / 1.1.0: your existing accounts keep working and the setup page is not shown.

## 5. Configuration (`.env`)
All settings are optional. Copy `.env.example` to `.env` **inside `Madrasa Admin Project`** and edit it.
Real environment variables win over `.env`.

| Setting | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | auto | Signs the login cookie. Empty = a random key is created once in `data/.secret_key`. To set your own: `py -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_PATH` | `data/madrasa.db` | SQLite database file (relative to the project folder). |
| `ADMIN_USERNAME` | empty | Optional. With `ADMIN_PASSWORD`, creates the first administrator on start (Docker/Render). Empty = setup page. Ignored once an administrator exists. |
| `ADMIN_PASSWORD` | empty | Optional, see `ADMIN_USERNAME` (8+ characters, not a common password). |
| `SEED_DEMO_DATA` | `false` | `true` = also load demo students, marks, attendance, fees and the routine (for trying the app or a demo). `false` = classes, subjects and the default periods only: no demo students, marks, fees or routine. No usable account is ever seeded (the demo routine's four sample teachers are disabled and have no password). |
| `HOST` | `127.0.0.1` | `0.0.0.0` = reachable from other computers. Keep `127.0.0.1` behind nginx. |
| `PORT` | `8000` | Web port. |
| `COOKIE_SECURE` | `false` | Set `true` when the site is served over HTTPS. |
| `SESSION_HOURS` | `12` | Hours before users must log in again. |
| `PBKDF2_ITERATIONS` | `600000` | Password-hash work factor (minimum 100000). |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCK_MINUTES` | `5` / `10` | Failed logins per username+IP before a lock, and lock time. Stored in the database (survives restarts, works with several workers). |
| `DEMO_LOGINS` | `true` (when unset) | **Default on.** The login page shows the Demo sign-in box (usernames and passwords for `demo.admin`, `demo.karim` and `demo.student`) and those accounts are created if missing, without wiping your data. **Set `DEMO_LOGINS=false` for a real school** — the boxes are hidden and the three demo accounts are disabled. |
| `DEMO_MODE` | `false` | **Public demo only.** `/login` shows a Demo sign-in box under the login form (usernames and passwords, plus optional one-click sign-in), passwords and API keys typed in Settings are never stored, no email is sent, and the database is wiped and re-seeded on every start. Refused with `COOKIE_SECURE=true`, `SEED_DEMO_DATA=false` or `ADMIN_USERNAME`/`ADMIN_PASSWORD`; never wipes a database with a real administrator. The 1.0.4 name `DEMO_AUTO_LOGIN=true` still works. See README *Demo access*. |

`SECRET_KEY` also encrypts the SMTP password and the payment / SMS secrets saved in **Settings** (1.0.5). Keep it
stable; if it changes, enter those secrets again. Email, payment gateways, SMS, currencies and languages are set
in the app (**Settings**), not in `.env` (section 10).

## 6. Database setup
**Nothing to do by default.** On first start the app creates `data/madrasa.db` (SQLite), all tables, classes (Grade 1-10, Hifz Level 1-10 with sections), subjects, class default subjects, monthly fee
plans and, if `SEED_DEMO_DATA=true`, the demo records. Then it opens the setup page (section 4).

### Create the database from the SQL files (optional)
The package includes `database/schema.sql` (empty database, matches the app's models exactly) and
`database/seed.sql` (the same demo data). Run from the package root, with the app stopped:
```bat
py -c "import sqlite3; c = sqlite3.connect('Madrasa Admin Project/data/madrasa.db'); c.executescript(open('database/schema.sql', encoding='utf-8').read()); c.executescript(open('database/seed.sql', encoding='utf-8').read()); c.close()"
```
(Linux: replace `py` with `python3`; or use the `sqlite3` tool: `sqlite3 "Madrasa Admin Project/data/madrasa.db" < database/schema.sql`.)
Skip the `seed.sql` part for an empty school database; the app then adds the classes on start. Neither file
creates user accounts, so the first start opens the setup page (section 4).

### Clean start for a real school
Stop the app, delete `data/madrasa.db` (and `madrasa.db-wal`/`-shm` if present), set `SEED_DEMO_DATA=false`
in `.env`, start again and complete the setup page (section 4).

### Backup and restore
Everything is in `data/madrasa.db`. Stop the app and copy that file to back up; copy it back to restore.
(Docker: `docker compose cp web:/app/data/madrasa.db ./madrasa-backup.db`.) Back up daily to another disk or cloud folder.

### Upgrading to 1.0.8 (from 1.0.7)
Replace the application files and keep `Madrasa Admin Project/data/` and `.env`. No new database migration is
required. The login page now shows the Demo sign-in box (Administrator, Teacher, Student) without
`DEMO_MODE`. **For a real school set `DEMO_LOGINS=false`** in `.env` or the host environment — otherwise the
three published demo accounts can sign in. That setting only hides the boxes and disables those accounts; it
does not wipe your data. `DEMO_MODE=true` still wipes and re-seeds the sample school on every start.

### Upgrading to 1.0.7 (from 1.0.6)
Replace the application files and keep `Madrasa Admin Project/data/` and `.env`. No new database migration is
required. The landing page at `/` now shows even before you create an administrator. To see the sample school
and the Demo sign-in boxes, start with `start-demo.bat` or `./start-demo.sh` (sets `DEMO_MODE=true`).

### Upgrading to 1.0.6 (from 1.0.5)
Replace the application files and keep `Madrasa Admin Project/data/` and `.env`. No new database migration is
required. The public landing page, login demo cards and `/tour` page are new. If you run a public demo, the
demo accounts now have passwords (`Admin@2026`, `Teacher@2026`, `Student@2026`) and a Demo sign-in box appears
under the login form. `DEMO_MODE=true` still works the same way.

### Upgrading to 1.0.5 (from 1.0.4)
Replace the application files (run `start.bat` / `start.sh` once, or `pip install --require-hashes -r
requirements.lock`, to install the new `cryptography` package) and keep `Madrasa Admin Project/data/` and `.env`.
On the next start the app saves a copy in `data/backups/`, then (migration 4) adds the `app_settings`,
`currencies`, `languages` and `translations` tables and the colour / landing page / default language columns of
`school_settings`. No data is changed; your currency symbol stays the default currency. The app UI moved from `/`
to `/dashboard`; `/` is now the public landing page (switch it off in **Settings > Branding** if you do not want it).
A public demo service: rename `DEMO_AUTO_LOGIN` to `DEMO_MODE` (optional, both work).

### Upgrading to 1.0.4 (from 1.0.1-1.0.3)
Replace the application files and keep `Madrasa Admin Project/data/` (database and secret key) and `.env`. On the
next start the app saves a copy in `data/backups/`, then adds the `login_attempts` table (migration 3); no data is
changed. If an earlier archive you received contained `data/.secret_key`, delete that file on your server (a new key
is generated; everyone logs in again) or set your own `SECRET_KEY`.

### Upgrading from 1.2.0 (internal numbering)
The app adds the `users.phone` column automatically (no data is changed). After the upgrade:
- teachers see **only their own classes** — make sure every teacher has subject assignments (Teachers > Assign);
- existing teacher accounts appear on the new **Teachers** page, student logins on **Student logins**.

### Upgrading from version 1.0 / 1.1.x
Copy your old `madrasa.db` into `Madrasa Admin Project/data/` and start the app. Missing tables and columns are
added automatically, marks without subject assignments are repaired, and old passwords keep working (they are
upgraded to the stronger hash at the next login).

From 1.1.x to 1.2.0 the upgrade also:
- creates the new routine tables (`periods`, `teacher_subjects`, `routine_slots`) and adds the default periods;
- adds the working days setting (Saturday to Thursday);
- **drops the `sms_logs` table** (the mock SMS feature is gone; back up the database first if you want to keep
  the old log).

After upgrading, assign your teachers to their subjects (**Class routine > Teacher assignments**): from 1.2.0 a
teacher can only enter marks for assigned subjects. Admins are not restricted.

## 7. VPS with nginx + HTTPS (Ubuntu 22.04 / 24.04)
You need a server, a domain (e.g. `school.example.com`) whose DNS A record points to the server IP, and SSH access.

**1) Install packages and copy the app**
```bash
sudo apt update && sudo apt install -y python3 python3-venv nginx certbot python3-certbot-nginx unzip
sudo useradd --system --create-home --home-dir /opt/madrasa-admin madrasa
unzip madrasa-pro-v1.0.8-vibe96.zip -d /tmp
sudo cp -r "/tmp/Madrasa_Admin_1.0.8/Madrasa Admin Project/." /opt/madrasa-admin/
sudo chown -R madrasa:madrasa /opt/madrasa-admin
```
**2) Python environment and settings**
```bash
cd /opt/madrasa-admin
sudo -u madrasa python3 -m venv venv
sudo -u madrasa venv/bin/python -m pip install --require-hashes -r requirements.lock
sudo -u madrasa cp .env.example .env
sudo -u madrasa nano .env
```
In `.env` set: `SECRET_KEY=<random>` (see section 5),
`SEED_DEMO_DATA=false` (real school) , `HOST=127.0.0.1`, `PORT=8000`, `COOKIE_SECURE=true`.
Then `sudo chmod 600 /opt/madrasa-admin/.env`.

**3) Run it as a service** - create `/etc/systemd/system/madrasa-admin.service`:
```ini
[Unit]
Description=Madrasa & School Admin System
After=network.target

[Service]
User=madrasa
Group=madrasa
WorkingDirectory=/opt/madrasa-admin
ExecStart=/opt/madrasa-admin/venv/bin/python main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now madrasa-admin
curl -s http://127.0.0.1:8000/healthz      # {"ok":true,"version":"1.0.8"}
```
**4) nginx reverse proxy** - create `/etc/nginx/sites-available/madrasa-admin`:
```nginx
server {
    listen 80;
    server_name school.example.com;
    client_max_body_size 5m;          # CSV import and logo upload

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/madrasa-admin /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```
**5) HTTPS certificate (free, auto-renewing)**
```bash
sudo certbot --nginx -d school.example.com --redirect
```
Open `https://school.example.com` **right away** and complete the setup page (section 4): until an
administrator exists, anyone who opens the address could do it (or set `ADMIN_USERNAME`/`ADMIN_PASSWORD` in `.env`
before the first start). Firewall: `sudo ufw allow 'Nginx Full'`
and `sudo ufw allow OpenSSH`, then `sudo ufw enable`. Port 8000 stays private.

**Updating** to a new version: back up `data/madrasa.db`, copy the new files over `/opt/madrasa-admin`
(keep `data/` and `.env`), reinstall `requirements.lock`, `sudo systemctl restart madrasa-admin`.
**Logs:** `sudo journalctl -u madrasa-admin -f`.

## 8. Docker
Requires Docker Engine with the Compose plugin. Run from the **package root** (the folder with `docker-compose.yml`):
```bash
cp .env.example .env          # OPTIONAL (Windows: copy .env.example .env); compose starts without it
# optional: edit .env (SECRET_KEY, ADMIN_USERNAME + ADMIN_PASSWORD, SEED_DEMO_DATA=true to try demo data)
docker compose up -d --build
docker compose ps             # STATUS shows "healthy" after ~20 s
```
Open **http://localhost:8000** and complete the setup page (section 4), unless you set `ADMIN_USERNAME` and
`ADMIN_PASSWORD`. The container listens on `127.0.0.1:8000` of the host; the database and
secret key are kept in the Docker volume `madrasa-data`, so they survive `docker compose down` and rebuilds.

- Logs: `docker compose logs -f` · Stop: `docker compose down` · Update: replace the files, then `docker compose up -d --build`.
- Backup: `docker compose cp web:/app/data/madrasa.db ./madrasa-backup.db`
- **Public server with HTTPS:** keep the port bound to 127.0.0.1, put nginx + certbot in front exactly as in
  section 7 steps 4-5 (nginx proxies to `127.0.0.1:8000`) and set `COOKIE_SECURE=true` in `.env`.
- Without Compose: `docker build -t madrasa-pro .` then
  `docker run -d -p 127.0.0.1:8000:8000 -v madrasa-data:/app/data --name madrasa madrasa-pro` (add `--env-file .env` if you made one).

## 9. Render / GitHub (optional)
See **GITHUB-RENDER.md** and `render.yaml`. Note: SQLite needs a persistent disk on Render (paid plan);
without one, data is lost on every redeploy.

## 10. Branding (make it yours)
- **App / institution name and tagline:** chosen on the setup page; change them any time as admin in
  **Settings > School / app profile**. The name is shown on the login page, in the menu, in the browser tab and on
  every printout; the optional tagline is shown under it on the login page.
- **Address, office phone, currency, grading scale:** also in **Settings**; the logo in the **School logo** card (or at first-run setup). The logo appears in the menu, on
  the login page, on result cards and receipts (logo: PNG/JPG/GIF/WebP, max 300 KB).
- **Icon:** replace `static/favicon.svg` (also shown when no logo is uploaded).
- **Colours:** **Settings > Branding**: primary and secondary colour (presets or any `#RRGGBB`), applied to every
  page, the landing page and the login page right after saving. The public landing page at `/` can be switched
  off there too.
- **Layout:** the CSS is prebuilt in `static/app.css` (Tailwind). After changing classes in the
  templates, rebuild it with Node.js 18+ (only needed for this):
  `npm ci && npm run build:css` (Tailwind 3.4.19 from `package-lock.json`). `npm run build:vendor` re-copies
  Alpine.js 3.17.5 from `node_modules` into `static/vendor/alpine.min.js`.
- **Default classes and subjects for new installations:** `app/seed.py`.

### Currencies, languages, email, payment gateways, SMS (Settings, 1.0.5)
- **Currencies:** add currencies (code, symbol, rate against the default, decimals), switch them on/off and choose
  the **default** (fees, receipts, reports). Anyone can view amounts in another active currency with the top-bar
  switch (display only; stored amounts are not converted).
- **Languages:** English, Bangla and Arabic (right-to-left) are built in. Add a language (e.g. `ur`, Urdu, RTL),
  then **Translate** to type its texts; empty fields fall back to the built-in text / English. Users switch the
  language in the top bar, on the login page or on the landing page; **Make default** sets it for new visitors.
- **Email (SMTP):** host, port, encryption (STARTTLS 587 / SSL 465 / none), username, password, From address and
  name; **Send test email** checks them. The password is stored encrypted and never shown again (leave the field
  empty to keep it, tick *Remove the saved value* to delete it).
- **Payment gateways:** Stripe, PayPal, SSLCommerz and bKash, each with on/off, test (sandbox) or live mode and its
  keys (secrets encrypted, masked). Switched-on gateways are offered as payment methods when collecting fees.
  The app does not run an online checkout itself; the keys are kept for your gateway integration.
- **SMS & integrations:** provider, HTTPS API URL, API key / secret (encrypted) and sender ID.

### Working days and periods
- **Working days** (shown on the class routine): **Settings > Working days**. Default: Saturday to Thursday.
- **Periods** of the school day: **Class routine > Periods** (name, start and end time, break). A new installation
  starts with six periods from 08:00 to 13:00 and a tiffin break; change them to your timetable.

## 11. Typical first steps
1. **Settings:** app / institution name, tagline, logo and colours (Branding), address, grading scale and working days
   (General), default currency, language, and if you use them email (SMTP), payment gateways and SMS.
2. **Teachers:** add your teachers (the demo data's sample teachers are disabled: give one a password with
   **Set password**) and assign their subjects with **Assign**.
3. **Classes:** check classes and sections (Grade 1-10 and Hifz Level 1-10 are created for you).
4. **Subjects:** add or edit subjects, then set the **default subjects for each class**.
5. **Students:** add students or import a CSV (`sample/students-import-sample.csv`; from Excel use *Save As > CSV UTF-8*).
6. **Student logins:** create logins for a class and print the login slips.
7. **Exams & Results:** add an exam, enter marks in the grid, check results, print cards, then **Publish**.
8. **Class routine:** set the **Periods**, assign teachers in **Teacher assignments**, then fill the weekly grid per
   class section (tap a period). Print the routine per class or per teacher.
9. **Attendance** daily; **Fees:** set the monthly fee per class, collect payments, print receipts and the due list.

## 12. Running the tests (optional, for developers)
```bat
cd "Madrasa Admin Project"
py -m pip install --require-hashes -r requirements-dev.lock
py -m pytest
py -m ruff check .
py -m pip_audit -r requirements.lock --require-hashes --disable-pip
cd ..
py -m pytest tests
```
The first `pytest` runs the application suite (484 tests); the last one checks the package layout, that
`database/schema.sql` matches the models and that `seed.sql` loads.

## 13. Troubleshooting
- **`py` is not recognised:** reinstall Python from python.org and tick "Add python.exe to PATH" (the `py`
  launcher is installed by default). Then open a new Command Prompt.
- **Port already in use:** set `PORT=8080` in `.env`.
- **`start.bat` says package installation failed:** check the internet connection; delete the `venv` folder and run it again.
- **Login cookie not kept on http://localhost:** `COOKIE_SECURE` must be `false` without HTTPS.
- **"Too many failed attempts":** wait 10 minutes (5 wrong passwords lock that username/IP for 10 minutes).
- **Forgot the admin password:** another admin can reset it in Settings > Administrator accounts. If there is no other
  admin, stop the app, back up `data/madrasa.db`, and run in `Madrasa Admin Project` (with the venv activated),
  replacing `YOUR_ADMIN_USERNAME` with your administrator username:
  ```bat
  py -c "from app.database import SessionLocal; from app.models import User; from app.security import hash_password; db=SessionLocal(); u=db.query(User).filter_by(username='YOUR_ADMIN_USERNAME').one(); u.password_hash=hash_password('TempPass#2026'); u.must_change_password=True; u.is_active=True; db.commit()"
  ```
  Then log in with `TempPass#2026` and choose a new password.

Developer: Syed Abue Tayeb Al-Zeyed
