# Routes and access guards

Every route of Madrasa Pro 1.0.8 and who may use it. The rules are enforced on the server (not just hidden in the menu).

## Quick evidence (1.0.8)

- **Shared guards** (app/security.py), declared on every route as a FastAPI dependency: `csrf_protect` (router-level, `app/api/__init__.py`), `require_admin`, `require_staff`, `current_user`.
- **57 write routes** (POST/PUT/DELETE): 50 use `Depends(require_admin)`, 7 use `Depends(require_staff)` and then check the teacher's class scope in the body; none uses only `current_user`.
- **11 DELETE routes**: all `require_admin` except `DELETE /api/students/{student_pk}/subjects/{subject_id}` (`require_staff` + `ensure_student_access`).
- **Teacher marks scope**: `app/api/exams.py` `_save_mark()` -> `services.can_enter_marks()` -> 403 unless the teacher is assigned that subject in the student's class/section; the marks sheet calls `_check_class_scope()`.
- **Proof by tests**: `tests/test_guards_v104.py` (guard on every write/DELETE route, marks scope, attendance scope, IDOR on student/receipt ids, no-store), `tests/test_auth.py` (every route x anonymous/teacher/student).

### Write routes and their guard (generated from the code)

| Method | Route | Guard | Module |
|---|---|---|---|
| POST | /api/students | `require_admin` | app/api/students.py |
| POST | /api/students/import | `require_admin` | app/api/students.py |
| PUT | /api/students/{student_pk} | `require_admin` | app/api/students.py |
| POST | /api/students/{student_pk}/status | `require_admin` | app/api/students.py |
| DELETE | /api/students/{student_pk} | `require_admin` | app/api/students.py |
| POST | /api/students/{student_pk}/subjects | `require_staff` | app/api/students.py |
| PUT | /api/students/{student_pk}/subjects | `require_staff` | app/api/students.py |
| POST | /api/students/{student_pk}/subjects/apply-class-defaults | `require_staff` | app/api/students.py |
| DELETE | /api/students/{student_pk}/subjects/{subject_id} | `require_staff` | app/api/students.py |
| POST | /api/students/{student_pk}/marks | `require_staff` | app/api/exams.py |
| POST | /api/exams | `require_admin` | app/api/exams.py |
| PUT | /api/exams/{exam_id} | `require_admin` | app/api/exams.py |
| DELETE | /api/exams/{exam_id} | `require_admin` | app/api/exams.py |
| POST | /api/marks/bulk | `require_staff` | app/api/exams.py |
| POST | /api/classes | `require_admin` | app/api/academics.py |
| PUT | /api/classes/{class_id} | `require_admin` | app/api/academics.py |
| DELETE | /api/classes/{class_id} | `require_admin` | app/api/academics.py |
| POST | /api/sections | `require_admin` | app/api/academics.py |
| DELETE | /api/sections/{section_id} | `require_admin` | app/api/academics.py |
| POST | /api/subjects | `require_admin` | app/api/academics.py |
| PUT | /api/subjects/{subject_id} | `require_admin` | app/api/academics.py |
| DELETE | /api/subjects/{subject_id} | `require_admin` | app/api/academics.py |
| PUT | /api/classes/{class_id}/subjects | `require_admin` | app/api/academics.py |
| POST | /api/classes/{class_id}/subjects/apply | `require_admin` | app/api/academics.py |
| POST | /api/attendance | `require_staff` | app/api/attendance.py |
| POST | /api/payments | `require_admin` | app/api/fees.py |
| POST | /api/payments/{payment_id}/void | `require_admin` | app/api/fees.py |
| PUT | /api/fees/plans | `require_admin` | app/api/fees.py |
| POST | /api/settings | `require_admin` | app/api/school_settings.py |
| POST | /api/users | `require_admin` | app/api/accounts.py |
| PUT | /api/users/{user_id} | `require_admin` | app/api/accounts.py |
| POST | /api/students/{student_pk}/create-login | `require_admin` | app/api/accounts.py |
| POST | /api/students/{student_pk}/disable-login | `require_admin` | app/api/accounts.py |
| POST | /api/students/{student_pk}/enable-login | `require_admin` | app/api/accounts.py |
| POST | /api/teachers | `require_admin` | app/api/accounts.py |
| PUT | /api/teachers/{teacher_id} | `require_admin` | app/api/accounts.py |
| POST | /api/teachers/{teacher_id}/reset-password | `require_admin` | app/api/accounts.py |
| POST | /api/teachers/{teacher_id}/status | `require_admin` | app/api/accounts.py |
| POST | /api/student-logins/bulk | `require_admin` | app/api/accounts.py |
| POST | /api/assignments | `require_admin` | app/api/routine.py |
| DELETE | /api/assignments/{assignment_id} | `require_admin` | app/api/routine.py |
| POST | /api/periods | `require_admin` | app/api/routine.py |
| PUT | /api/periods/{period_id} | `require_admin` | app/api/routine.py |
| DELETE | /api/periods/{period_id} | `require_admin` | app/api/routine.py |
| PUT | /api/routine/slot | `require_admin` | app/api/routine.py |
| DELETE | /api/routine/slot/{slot_id} | `require_admin` | app/api/routine.py |
| PUT | /api/config/{section} | `require_admin` | app/api/integrations.py |
| POST | /api/config/smtp/test | `require_admin` | app/api/integrations.py |
| POST | /api/currencies | `require_admin` | app/api/integrations.py |
| PUT | /api/currencies/{currency_id} | `require_admin` | app/api/integrations.py |
| DELETE | /api/currencies/{currency_id} | `require_admin` | app/api/integrations.py |
| POST | /api/currencies/{currency_id}/default | `require_admin` | app/api/integrations.py |
| POST | /api/languages | `require_admin` | app/api/integrations.py |
| PUT | /api/languages/{language_id} | `require_admin` | app/api/integrations.py |
| DELETE | /api/languages/{language_id} | `require_admin` | app/api/integrations.py |
| POST | /api/languages/{language_id}/default | `require_admin` | app/api/integrations.py |
| PUT | /api/languages/{language_id}/translations | `require_admin` | app/api/integrations.py |

## Rules

- **Signed-in user** = a valid signed session cookie (`madrasa_session`) for an active account that has already changed its first-login password. Otherwise API calls get `401`/`403` and pages redirect to `/login` or `/change-password`.
- **Roles**: `admin` (everything), `teacher` (only their own classes — see *Teacher scope*), `student` (own profile, own published results, own attendance, own fees and own class routine; never another student's data).
- **Teacher scope (1.3.0)**: a teacher's classes are the class/sections of their subject assignments plus the sections where they have routine periods (a class-wide assignment covers every section). Students, attendance (read and save), marks sheets, results, class lists, class routines, printouts and dashboard numbers are limited to that scope; other classes answer `403` or are left out of lists. A teacher's `/api/teachers` and `/api/assignments` only return themselves. Fees, settings, user/teacher management and student logins are admin-only. Implemented in `app/services.py` (`teacher_scope`, `student_condition`, `can_view_student`) and `ensure_student_access` in `app/security.py`.
- **Marks restriction (1.2.0)**: a teacher may only save marks for subjects an admin assigned to them for that class (or section); other subjects answer `403`. Admins are not restricted.
- **CSRF**: every mutating request needs the CSRF token: API calls send the `X-CSRF-Token` header (added by `static/js/common.js`), HTML forms send the hidden `csrf_token` field. Requests without it get `403`.
- Role checks live in `app/security.py` (`current_user`, `require_admin`, `require_staff`, `ensure_student_access`) and in `page_user()` in `app/main.py`.
- The root test `tests/test_package_layout.py` fails if a mutating `/api` route has no admin/teacher role guard, or if this table misses a route.

## Pages and print views (`app/main.py`)

| Method | Path | Who may use it | Mutating | Notes |
|---|---|---|---|---|
| GET | `/healthz` | Public | - | Health check for Docker/Render: `{"ok": true, "version": ...}` |
| GET | `/setup` | Public, only while no administrator exists (afterwards: 303 redirect to `/dashboard`) | - | First-run setup: app / institution name, optional tagline, optional school logo (1.3.0), administrator username and password. Every page redirects here until it is done. |
| POST | `/setup` | Public, only while no administrator exists (404 afterwards, checked before anything else) | yes | Multipart form. Validates the form (password min. 8 characters, not common, confirmed; logo PNG/JPEG/GIF/WebP max 300 KB), saves the name and logo, creates the administrator and logs them in. |
| GET | `/login` | Public. Shown whenever `DEMO_LOGINS` is true (the default) or `DEMO_MODE` is true, even if no school administrator has been created yet. Otherwise redirects to `/setup` while no administrator exists. | - | Login page with the chosen app name and tagline. A **Demo sign-in** box under the form lists the three demo usernames and passwords when `DEMO_LOGINS` or `DEMO_MODE` is on. Clicking a card fills the form. Set `DEMO_LOGINS=false` for a real school (no boxes). |
| POST | `/login` | Public (CSRF form token, login throttling: 5 failures / 10 min) | yes | Starts a signed session. |
| POST | `/logout` | Signed-in session (CSRF form token) | yes | Clears the session. |
| GET | `/logout` | Public | - | Only redirects to `/` (landing page); logging out needs the POST form. |
| GET | `/change-password` | Signed-in session | - | Forced at first login. |
| POST | `/change-password` | Signed-in session (CSRF form token) | yes | Checks current password and password rules. |
| GET | `/` | Public | - | Landing page (hero, features, screenshots, roles, how it works, FAQ, technology, **Live Demo** / **Take the tour**). No data and no contact details. Shown even before an administrator exists (1.0.7). Redirects to `/dashboard` (or `/setup` if there is no admin) only when Settings > Branding switches the landing page off. |
| GET | `/tour` | Public | - | Product tour (screenshot walkthrough of the real app). `?autostart=1` starts playing. Linked from the landing page and the login page. No login required. |
| GET | `/dashboard` | Admin, Teacher (students are redirected to their own profile; anonymous visitors to `/login`) | - | 1.0.5: the single-page admin UI (Alpine.js); it was `/` before. |
| POST | `/set-language` | Public (CSRF form token) | yes | 1.0.5. Interface language for this browser session (`lang` = an active language code, otherwise `400`). `next` must be a local path (`/...`, not `//` or `\`), otherwise `/`. |
| POST | `/demo/login` | Demo mode only (`DEMO_MODE=true`, old name `DEMO_AUTO_LOGIN`); `404` on every normal install. CSRF form token. | yes | One-click sign-in as the demo administrator, teacher or student. Visitors are never logged in automatically. The same accounts can also sign in through `POST /login` with the published demo passwords (set only in demo mode). |
| GET | `/student/{student_pk}` | Any signed-in user + record check | - | Student profile hub. Students: own record only. Teachers: students of their classes only. |
| GET | `/print/result/{student_pk}` | Any signed-in user + record check | - | Result card. Students: own card, published exams only. Teachers: their classes only. |
| GET | `/print/results` | Admin, Teacher | - | Print all result cards of an exam / class / section. Teachers: their classes only. |
| GET | `/print/receipt/{payment_id}` | Admin | - | Fee receipt. |
| GET | `/print/attendance` | Admin, Teacher | - | Printable attendance sheet. Teachers: their classes only. |
| GET | `/print/students` | Admin, Teacher | - | Printable student list. Teachers: their classes only. |
| GET | `/print/dues` | Admin | - | Printable fee-due list per class (replaces the SMS fee reminders of 1.1.x). |
| GET | `/print/routine` | Any signed-in user | - | Weekly routine of one class section (A4 landscape). Students always get their own section; teachers only sections they teach. |
| GET | `/print/routine/teacher/{teacher_id}` | Admin (any teacher), Teacher (own routine only) | - | Weekly routine of one teacher (A4 landscape). |
| GET | `/static/...` | Public | - | CSS, JavaScript, icons (no data). |

## JSON API (`app/api/<module>.py`, all under `/api`, all need a signed-in user)

| Method | Path | Who may use it | Mutating | Notes |
|---|---|---|---|---|
| GET | `/api/me` | Any signed-in user | - | Who is logged in. |
| GET | `/api/config/{section}` | Admin | - | 1.0.5 Settings: `smtp`, `payments` (Stripe, PayPal, SSLCommerz, bKash) or `sms`. Secret fields come back as `""` plus `<field>_set` / `<field>_mask`; the value itself is never sent. Unknown section: `404`. |
| PUT | `/api/config/{section}` | Admin | yes | 1.0.5. Saves the fields sent (validated: host, port 1-65535, email, `https://` URL, choices, booleans). Secrets are Fernet-encrypted (key from SECRET_KEY); an empty secret keeps the stored one, `<field>_clear: true` removes it. **Demo mode** saves the other fields but never stores secrets (`skipped_secrets`). |
| POST | `/api/config/smtp/test` | Admin | yes | 1.0.5. Sends one test email with the saved SMTP settings (STARTTLS / SSL / none). `403` in demo mode, `400` if host or From address are missing, `502` with the SMTP error if sending fails. |
| GET | `/api/currencies` | Any signed-in user | - | 1.0.5. Currencies with symbol, rate and the default one (fees and receipts). |
| POST | `/api/currencies` | Admin | yes | 1.0.5. Add (3-letter code, name, symbol, rate against the default, decimals). |
| PUT | `/api/currencies/{currency_id}` | Admin | yes | 1.0.5. Edit; the default currency cannot be switched off. |
| DELETE | `/api/currencies/{currency_id}` | Admin | yes | 1.0.5. Not the default currency (`400`). |
| POST | `/api/currencies/{currency_id}/default` | Admin | yes | 1.0.5. Make it the school currency (symbol on fees, receipts, reports); other rates are re-based. Stored amounts are not converted. |
| GET | `/api/languages` | Any signed-in user | - | 1.0.5. Interface languages (English, Bangla, Arabic RTL built in). |
| POST | `/api/languages` | Admin | yes | 1.0.5. Add a language (code, name, native name, right-to-left). |
| PUT | `/api/languages/{language_id}` | Admin | yes | 1.0.5. Rename, RTL, switch on/off (not the default one). The code cannot change. |
| DELETE | `/api/languages/{language_id}` | Admin | yes | 1.0.5. Removes the language and its translations; not English and not the default (`400`). |
| POST | `/api/languages/{language_id}/default` | Admin | yes | 1.0.5. School default language for visitors who did not choose one. |
| GET | `/api/languages/{language_id}/translations` | Admin | - | 1.0.5. Every interface key with the English text, the built-in translation and the admin's own text. |
| PUT | `/api/languages/{language_id}/translations` | Admin | yes | 1.0.5. `{key: text}`; unknown keys `400`; empty text = use the built-in text again. Texts are always HTML-escaped when shown. |
| GET | `/api/dashboard` | Admin, Teacher | - | Teachers: numbers and activity of their own classes; no fee figures. |
| GET | `/api/students` | Admin, Teacher | - | Teachers: students of their classes only. |
| POST | `/api/students` | Admin | yes |  |
| GET | `/api/students/export.csv` | Admin | - |  |
| POST | `/api/students/import` | Admin | yes |  |
| GET | `/api/students/{student_pk}` | Any signed-in user + record check | - | Students: own record only. Teachers: their classes. |
| PUT | `/api/students/{student_pk}` | Admin | yes |  |
| POST | `/api/students/{student_pk}/status` | Admin | yes |  |
| DELETE | `/api/students/{student_pk}` | Admin | yes |  |
| GET | `/api/students/{student_pk}/profile` | Any signed-in user + record check | - | Students: own record, published exams only. Teachers: their classes, no fees / login. |
| GET | `/api/students/{student_pk}/subjects` | Any signed-in user + record check | - | Students: own record only. |
| POST | `/api/students/{student_pk}/subjects` | Admin, Teacher | yes | Teachers: students of their classes only. |
| PUT | `/api/students/{student_pk}/subjects` | Admin, Teacher | yes | Teachers: students of their classes only. |
| POST | `/api/students/{student_pk}/subjects/apply-class-defaults` | Admin, Teacher | yes | Teachers: students of their classes only. |
| DELETE | `/api/students/{student_pk}/subjects/{subject_id}` | Admin, Teacher | yes | Teachers: students of their classes only. |
| POST | `/api/students/{student_pk}/marks` | Admin, Teacher | yes | Teachers: assigned subjects only. |
| GET | `/api/classes` | Admin, Teacher | - | Teachers: only their classes/sections, no fee amounts. |
| POST | `/api/classes` | Admin | yes |  |
| PUT | `/api/classes/{class_id}` | Admin | yes |  |
| DELETE | `/api/classes/{class_id}` | Admin | yes |  |
| POST | `/api/sections` | Admin | yes |  |
| DELETE | `/api/sections/{section_id}` | Admin | yes |  |
| GET | `/api/subjects` | Admin, Teacher | - |  |
| POST | `/api/subjects` | Admin | yes |  |
| PUT | `/api/subjects/{subject_id}` | Admin | yes |  |
| DELETE | `/api/subjects/{subject_id}` | Admin | yes |  |
| GET | `/api/classes/{class_id}/subjects` | Admin, Teacher | - |  |
| PUT | `/api/classes/{class_id}/subjects` | Admin | yes |  |
| POST | `/api/classes/{class_id}/subjects/apply` | Admin | yes |  |
| GET | `/api/exams` | Any signed-in user | - | Students only get published exams. |
| POST | `/api/exams` | Admin | yes |  |
| PUT | `/api/exams/{exam_id}` | Admin | yes |  |
| DELETE | `/api/exams/{exam_id}` | Admin | yes |  |
| GET | `/api/marks` | Admin, Teacher | - | Teachers: their classes only (403 otherwise). |
| POST | `/api/marks/bulk` | Admin, Teacher | yes | Teachers: assigned subjects only (403 otherwise). |
| GET | `/api/results` | Admin, Teacher | - | Teachers: their classes only. |
| GET | `/api/my/results` | Any signed-in user | - | Student's own published results. |
| GET | `/api/attendance` | Admin, Teacher | - | Teachers: their classes only. |
| POST | `/api/attendance` | Admin, Teacher | yes | Teachers: students of their classes only (403 otherwise). |
| GET | `/api/attendance/report` | Admin, Teacher | - | Teachers: their classes only. |
| GET | `/api/payments` | Admin | - |  |
| POST | `/api/payments` | Admin | yes |  |
| POST | `/api/payments/{payment_id}/void` | Admin | yes |  |
| GET | `/api/receipt/{payment_id}` | Admin | - |  |
| GET | `/api/fees/plans` | Admin | - |  |
| PUT | `/api/fees/plans` | Admin | yes |  |
| GET | `/api/fees/dues` | Admin | - |  |
| GET | `/api/teachers` | Admin, Teacher | - | Teacher and admin accounts that can be put on the routine. A teacher only gets themselves. |
| GET | `/api/assignments` | Admin, Teacher | - | Teacher-subject assignments (filter by class / teacher). A teacher only gets their own. |
| POST | `/api/assignments` | Admin | yes | Assign a teacher to a subject of a class (section optional). Replaces the previous teacher of that class/section/subject. |
| DELETE | `/api/assignments/{assignment_id}` | Admin | yes |  |
| GET | `/api/periods` | Any signed-in user | - | Periods of the school day (start/end time, break flag). |
| POST | `/api/periods` | Admin | yes | End after start, no overlap with another period. |
| PUT | `/api/periods/{period_id}` | Admin | yes | A period that has classes cannot become a break. |
| DELETE | `/api/periods/{period_id}` | Admin | yes | Also removes the routine entries in that period. |
| GET | `/api/routine` | Any signed-in user | - | Weekly routine of a class section. Staff choose the section (teachers: sections they teach); students always get their own. |
| GET | `/api/my/routine` | Admin, Teacher | - | A teacher's own weekly routine and today's classes. Only admins may pass `teacher_id`. |
| PUT | `/api/routine/slot` | Admin | yes | Set subject, teacher (defaults to the assigned teacher) and room of one day/period. Blocks: break periods, non-working days, a section of another class, unassigned teachers and double-booked teachers. |
| DELETE | `/api/routine/slot/{slot_id}` | Admin | yes |  |
| GET | `/api/settings` | Any signed-in user | - | School name, logo, scale, currency, working days; 1.0.5: brand colours, landing page on/off, default language, currencies, payment methods (incl. switched-on gateways), demo flag. |
| POST | `/api/settings` | Admin | yes | 1.0.5 adds `primary_color` / `secondary_color` (`#RRGGBB`, applied to every page) and `landing_enabled`. |
| GET | `/api/users` | Admin | - |  |
| POST | `/api/users` | Admin | yes | Admin or teacher account (the Settings page adds administrators). |
| PUT | `/api/users/{user_id}` | Admin | yes | Reset password / enable / disable. An admin cannot disable themselves. |
| POST | `/api/students/{student_pk}/create-login` | Admin | yes | Create or reset a student login (username default = 6-digit student ID; a reset keeps the username). Blank password = generated, returned once. |
| POST | `/api/students/{student_pk}/disable-login` | Admin | yes |  |
| GET | `/api/students/{student_pk}/login-status` | Admin | - |  |
| POST | `/api/students/{student_pk}/enable-login` | Admin | yes | 1.3.0. Re-enable a disabled student login (not for archived students). |
| GET | `/api/teachers/manage` | Admin | - | 1.3.0 Teachers page: every teacher with phone, login status, last login, assigned subjects/classes, periods per week. |
| POST | `/api/teachers` | Admin | yes | 1.3.0. Add a teacher (full name, username, optional phone, optional password; blank = generated and returned once). Must change the password at first login. Duplicate usernames (any case) answer 400. |
| PUT | `/api/teachers/{teacher_id}` | Admin | yes | 1.3.0. Edit name, username, phone. Teacher accounts only. |
| POST | `/api/teachers/{teacher_id}/reset-password` | Admin | yes | 1.3.0. New temporary password (typed or generated, returned once); must change at next login; open sessions are logged out. |
| POST | `/api/teachers/{teacher_id}/status` | Admin | yes | 1.3.0. Enable / disable the login (a teacher without a password cannot be enabled). |
| GET | `/api/student-logins` | Admin | - | 1.3.0 Student logins page: students of a class/section with login status. |
| POST | `/api/student-logins/bulk` | Admin | yes | 1.3.0. Create logins (username = student ID) for every current student of a class/section; optionally reset existing ones. Temporary passwords are returned once for the printable slips; only hashes are stored. |

## Summary

- 57 mutating API routes: every one requires the **Admin** role or the **Admin/Teacher** role, plus the CSRF header.
- No API route is public. Students can only read their own record (`own-record check`); all writes are staff-only.
- Uploaded logos are validated (PNG/JPEG/GIF/WebP magic bytes, max 300 KB) and stored as a data URL; nothing is written to disk.

Developer: Syed Abue Tayeb Al-Zeyed
