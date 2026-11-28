# Security evidence — Madrasa Pro 1.0.8

Short, checkable answers to the Vibe96 findings (runs #3278 and #3282). Every statement is backed by a test that
fails if it stops being true (`Madrasa Admin Project/tests/test_guards_v104.py`, `tests/test_auth.py`,
`tests/test_demo_v104.py`, root `tests/test_package_layout.py`).

## 0. Secret key file (run #3282 finding 1.1)

- The archive ships **no** `data/.secret_key`, no `.env` and no database: `data/` holds only `.gitkeep` and
  `README.txt` (root test `test_package_layout.py` fails the build otherwise). `.gitignore` and `.dockerignore`
  cover `**/data/*`, `**/data/.secret_key`, `**/*.db`. The Dockerfile also runs `rm -f /app/data/.secret_key`.
- An earlier upload contained a generated key. Treat that key as public: **set your own `SECRET_KEY`**
  (Render: "Generate"; elsewhere `python -c "import secrets; print(secrets.token_urlsafe(48))"`) or delete
  `data/.secret_key` so a new one is generated on the next start. Changing the key only signs everyone out.
- If you keep the project in git and an old commit contains `data/.secret_key`, remove it from history with
  `git filter-repo --path "Madrasa Admin Project/data/.secret_key" --invert-paths` and rotate the key as above.
  The same applies to the live demo service: give it its own fresh `SECRET_KEY`.

## 1. Shared guard on every route (R6)

```python
# app/api/__init__.py - router-level CSRF for every /api route
router = APIRouter(prefix="/api", dependencies=[Depends(csrf_protect)])
# every route then declares its role guard, e.g. app/api/fees.py
@router.post("/payments/{payment_id}/void")
def void_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
```

- 76 API routes; **46 write routes**: 39 `require_admin`, 7 `require_staff`
  (marks, attendance, per-student subjects; the body then checks the teacher's class scope). No write route relies
  on `current_user` alone. Full table: top of `docs/ROUTES.md`; per module: docstring of each `app/api/*.py`.
- Tests: `test_every_route_carries_csrf_and_a_role_guard`, `test_every_write_route_uses_the_shared_role_guard`
  (one case per write route), `test_teacher_cannot_use_admin_routes` / `test_student_cannot_use_staff_routes`
  (every route called as teacher and student).

## 2. DELETE routes and their role checks

| Method | Route | Guard | Handler |
|---|---|---|---|
| DELETE | `/api/students/{student_pk}` | `require_admin` | app/api/students.py `delete_student` |
| DELETE | `/api/students/{student_pk}/subjects/{subject_id}` | `require_staff` | app/api/students.py `remove_student_subject` |
| DELETE | `/api/exams/{exam_id}` | `require_admin` | app/api/exams.py `delete_exam` |
| DELETE | `/api/classes/{class_id}` | `require_admin` | app/api/academics.py `delete_class` |
| DELETE | `/api/sections/{section_id}` | `require_admin` | app/api/academics.py `delete_section` |
| DELETE | `/api/subjects/{subject_id}` | `require_admin` | app/api/academics.py `delete_subject` |
| DELETE | `/api/assignments/{assignment_id}` | `require_admin` | app/api/routine.py `delete_assignment` |
| DELETE | `/api/periods/{period_id}` | `require_admin` | app/api/routine.py `delete_period` |
| DELETE | `/api/routine/slot/{slot_id}` | `require_admin` | app/api/routine.py `delete_slot` |

Test: `test_every_delete_route_is_admin_or_scoped_staff`, `test_delete_routes_refuse_non_admins` (teacher and student
get 403 on every admin DELETE).

## 3. Scoped writes/deletes for fees, attendance, exams and marks (R7)

| Data | Write/delete path | Check |
|---|---|---|
| Fees | `POST /api/payments`, `POST /api/payments/{id}/void`, `PUT /api/fees/plans`; **no hard delete** (payments are voided, kept for audit) | `require_admin`; payment fetched by primary key; `students.id <- payments` is `ON DELETE RESTRICT` and `DELETE /api/students/{id}` refuses a student with payments |
| Receipts | `GET /api/receipt/{id}`, `/print/receipt/{id}` | admin only (`test_fee_and_receipt_ids_are_admin_only`: teacher/student get 403) |
| Attendance | `POST /api/attendance` (upsert; duplicate rows of the same student+date removed) | `require_staff`; teachers: every student id must be inside `services.student_condition()` or the whole request is refused with 403 (`test_teacher_attendance_and_student_ids_are_scoped`) |
| Exams | `DELETE /api/exams/{id}` | `require_admin`; refused with 400 while marks exist; `marks.exam_id` is `ON DELETE RESTRICT` |
| Marks | `POST /api/students/{id}/marks`, `POST /api/marks/bulk` (empty value deletes that one mark) | `require_staff` + `_save_mark()` -> `services.can_enter_marks()`: a teacher may only write subjects assigned to them in the student's class/section, else 403 (`test_teacher_marks_scope`) |
| Students | `DELETE /api/students/{id}` | `require_admin`; child rows deleted with `delete(Model).where(Model.student_id == id)` |

Every bulk delete in the code has a WHERE clause on a primary/foreign key (`test_every_bulk_delete_has_a_where_clause`).

## 4. No string-built SQL (grep evidence)

All queries are SQLAlchemy 2 expressions (`select()`, `delete().where()`, `insert().values()`), so values are bound
parameters. Output of the scan on the shipped code:

```text
$ grep -rnE "(^|[^.a-zA-Z_])text\(" app/
app/database.py:102:            conn.execute(text(ddl + _sql_default(column)))

$ grep -rnE "f\"...(SELECT|INSERT|UPDATE|DELETE|ALTER|DROP)" app/
app/database.py:101:            ddl = f"ALTER TABLE {_quote(eng, table.name)} ADD COLUMN {_quote(eng, column.name)} {coltype}"

$ grep -rn "\.query(\|execute(\"\|exec_driver_sql\|executescript" app/
app/database.py:32:        cur.execute("PRAGMA foreign_keys=ON")
app/database.py:33:        cur.execute("PRAGMA journal_mode=WAL")
```

The only SQL text is in `app/database.py`: two constant PRAGMAs and migration 1's
`ALTER TABLE <table> ADD COLUMN <column>`, whose names come from `app/models.py` and pass `_quote()` (regex
whitelist `^[a-z_][a-z0-9_]*$` + dialect quoting); no request data reaches it. `test_no_text_sql_or_fstring_sql_in_app_code`
fails on any new `text(` / f-string SQL / `.query(`.

## 5. Passwords and temporary passwords

- `users.password_hash` = salted PBKDF2-SHA256 (600,000 iterations); there is no plaintext password column.
- Temporary passwords are generated in `services.choose_password()`, hashed by `services.issue_password()` (which
  also sets `must_change_password=True`), returned once in the API response and never logged.
  `test_temporary_password_is_only_stored_as_a_hash` scans the raw SQLite file (and WAL) for the plaintext.
- Typed passwords must pass `security.password_problem()` (length, common-password list) before hashing.
- All `/api/*` and `/print/*` responses carry `Cache-Control: no-store` (`test_password_responses_are_never_cached`).
- Sentinel `!no-password-set` never verifies (`test_no_password_sentinel_never_verifies`).
- Login throttle is stored in the `login_attempts` table: survives restarts, shared by workers
  (`test_login_throttle_is_persistent_across_restarts`).

## 6. Demo mode and secrets

- 1.0.5 integration secrets (SMTP password, Stripe / PayPal / SSLCommerz / bKash secrets, SMS API key/secret) are
  stored Fernet-encrypted in `app_settings` (`app/secret_store.py`, key = HKDF-SHA256 of `SECRET_KEY`); the API
  returns only `""` + `<field>_set` + a fixed mask, never the value or part of it. In demo mode secrets are never
  stored and the test email answers 403. Tests: `tests/test_v105.py` (`test_smtp_settings_are_saved_and_password_is_encrypted`,
  `test_payment_gateways_masked_and_used_as_payment_methods`, `test_demo_mode_never_stores_secrets_and_sends_no_email`,
  `test_config_is_admin_only`).
- `POST /set-language` is CSRF-checked and only redirects to local paths (`test_set_language_rules`); admin
  translations are always HTML-escaped (`test_add_language_translate_and_delete`); pages contain no inline event
  handlers, so the CSP needs no `unsafe-inline` for scripts.

- `DEMO_MODE` (old name `DEMO_AUTO_LOGIN`) is false by default and refused together with `COOKIE_SECURE=true`, `SEED_DEMO_DATA=false` or
  `ADMIN_USERNAME/ADMIN_PASSWORD`; demo mode never wipes a database with a real administrator (`tests/test_demo_v104.py`).
- `data/.secret_key` is generated at runtime when `SECRET_KEY` is empty, is ignored by `.gitignore`/`.dockerignore`,
  removed in the Dockerfile and **not shipped**: `data/` contains only `.gitkeep` and `README.txt`. If an older
  archive ever contained a key file, delete it on the server (a new one is generated; all sessions end) or set
  `SECRET_KEY`.

Developer: Syed Abue Tayeb Al-Zeyed
