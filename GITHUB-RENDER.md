# GitHub + Render deployment (optional)

The recommended production setups are a VPS with nginx + HTTPS or Docker (see HowToSetup.md, sections 7-8).
Render is an easy alternative if you already use GitHub.

## 1. Put the code on GitHub (private repository)
1. Create a **private** repository on GitHub.
2. Upload the **contents** of the package root (README.md, Dockerfile, render.yaml, `Madrasa Admin Project/`, ...).
3. The included `.gitignore` keeps out `.env`, `*.db`, `data/.secret_key`, `venv/` and caches. Never upload a
   real `.env` or your `madrasa.db`; Render does not read `.env` files, settings go into the Render dashboard.

## 2. Create the Render service
1. Render dashboard > **New > Blueprint** > pick your repository. Render reads `render.yaml`:
   Docker runtime, health check `/healthz`, a 1 GB persistent disk at `/app/data`, and the settings below.
2. When asked for `ADMIN_USERNAME` and `ADMIN_PASSWORD`, either enter your administrator username and a strong
   password (8+ characters), or leave both empty.
3. Deploy, then open `https://<your-service>.onrender.com`. If you left them empty, the first-run setup page opens:
   choose the app / institution name and your administrator username and password **straight away**, because
   until then anyone who opens the address could do it. There are no default passwords.

Manual alternative: **New > Web Service** > your repo > Runtime **Docker**, Dockerfile path `./Dockerfile`,
add a **Disk** mounted at `/app/data`, and set the environment variables below.

## 3. Environment variables on Render
| Key | Value |
|---|---|
| `SECRET_KEY` | Generate (Render button). Always use a fresh value. Never reuse a key from an earlier upload; see docs/SECURITY-EVIDENCE.md section 0. |
| `COOKIE_SECURE` | `true` (Render serves HTTPS) |
| `HOST` | `0.0.0.0` |
| `PORT` | `8000` |
| `DATABASE_PATH` | `/app/data/madrasa.db` |
| `SEED_DEMO_DATA` | `false` for a real school (render.yaml default); `true` only for the demo service |
| `DEMO_LOGINS` | Default **true** if unset. **Set `false` for a real school** (hides the Demo sign-in box and disables `demo.admin` / `demo.karim` / `demo.student`). render.yaml has this as a comment. |
| `DEMO_MODE` | `false` (render.yaml default). `true` only on a public demo service, see section 5 (old name `DEMO_AUTO_LOGIN` also works) |
| `ADMIN_USERNAME` | your administrator username (optional; empty = setup page) |
| `ADMIN_PASSWORD` | your administrator password (optional; empty = setup page) |
| `SESSION_HOURS` | `12` |

## 4. Important
- **Persistent disk is required** for real data (paid plan). Without a disk, the free plan wipes the SQLite
  database on every deploy or restart. For a public demo that is acceptable (`SEED_DEMO_DATA=true` recreates it).
- Back up the disk regularly (Render shell: copy `/app/data/madrasa.db`).

## 5. Public demo service (demo sign-in cards)
For a sales/Vibe96 demo link (like https://madrasa-ms.onrender.com/) create a **separate** service and set, in its
Render dashboard only:

| Key | Value |
|---|---|
| `DEMO_MODE` | `true` |
| `SEED_DEMO_DATA` | `true` |
| `COOKIE_SECURE` | `false` (required: the app refuses demo mode together with `COOKIE_SECURE=true`) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | leave **empty** (refused in demo mode) |

`/` shows the public landing page; its **Live Demo** button opens `/login`, which shows a Demo sign-in box
with username and password for Administrator, Teacher and Student (`demo.admin` / `Admin@2026`,
`demo.karim` / `Teacher@2026`, `demo.student` / `Student@2026`). Clicking a card fills the form; one-click
sign-in is also available. **Take the tour** opens `/tour?autostart=1`.
Use the landing page address (e.g. https://madrasa-ms.onrender.com/) as the live demo link. Passwords and API keys
typed into Settings are never stored in demo mode and test emails are not sent.
If the service had `DEMO_AUTO_LOGIN=true` from 1.0.4, either keep it or replace it with `DEMO_MODE=true`. On every start the database is wiped and re-seeded with the
sample classes, timetable, attendance, results and fees, so no disk is needed. The app refuses to wipe a database
that contains a real (non-demo) administrator. Never enable demo mode on a real school's service.

Developer: Syed Abue Tayeb Al-Zeyed
