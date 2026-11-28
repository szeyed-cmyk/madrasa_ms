# Madrasa Pro — API reference

Endpoints are grouped by module (code: `Madrasa Admin Project/app/api/<module>.py`; the complete route + guard table is `docs/ROUTES.md`). Role column shows who may call the route. Demo mode adds `POST /demo/login` (404 on normal installs).

## Auth

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/login` | public | Login form. Redirects to `/setup` if no admin exists. |
| POST | `/login` | public | Username + password. Sets session cookie. |
| POST | `/logout` | any | Clears session. |
| GET | `/setup` | public | First-run setup. Disabled after an admin exists. |
| POST | `/setup` | public | Creates the first administrator. |

## Dashboard

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/` | admin, teacher | Home dashboard. Students redirect to their portal. |
| GET | `/api/dashboard` | admin, teacher | Summary counts. Teachers see only their classes. |

## Students

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/students` | admin, teacher | List. Teachers scoped to assigned classes. |
| POST | `/api/students` | admin | Create student. |
| GET | `/api/students/{id}` | admin, teacher, student | Student sees only own record. |
| PUT | `/api/students/{id}` | admin | Update. |
| DELETE | `/api/students/{id}` | admin | Delete. |

## Teachers

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/teachers` | admin | List teachers. |
| POST | `/api/teachers` | admin | Create teacher account. |
| PUT | `/api/teachers/{id}` | admin | Update. |
| POST | `/api/teachers/{id}/reset-password` | admin | Reset password. |

## Student logins

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/student-logins` | admin | List student accounts. |
| POST | `/api/students/{id}/create-login` | admin | Create login for one student. |

## Subjects

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/subjects` | admin, teacher | List. |
| POST | `/api/subjects` | admin | Create. |
| PUT | `/api/subjects/{id}` | admin | Update. |
| DELETE | `/api/subjects/{id}` | admin | Delete. |

## Classes

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/classes` | admin, teacher | List classes and sections. |
| POST | `/api/classes` | admin | Create class. |
| POST | `/api/classes/{id}/sections` | admin | Add section. |

## Attendance

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/attendance` | admin, teacher | By class, section, date. Teachers scoped. |
| POST | `/api/attendance` | admin, teacher | Save marks. Teachers only for own classes. |

## Exams and results

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/exams` | admin, teacher | List exams. |
| POST | `/api/exams` | admin | Create exam. |
| POST | `/api/marks` | admin, teacher | Enter marks. Teachers scoped. |
| GET | `/api/results` | admin, teacher, student | Student sees only own results. |

## Fees

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/fees/plans` | admin | Fee plans by class. |
| PUT | `/api/fees/plans` | admin | Update plans. |
| GET | `/api/fees/dues` | admin | Outstanding dues. |
| GET | `/api/payments` | admin | Payment list. |
| POST | `/api/payments` | admin | Record payment. |
| POST | `/api/payments/{id}/void` | admin | Void a receipt. |

## Routine

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/routine` | admin, teacher | Weekly timetable. Teachers see own periods. |
| PUT | `/api/routine/slot` | admin | Set subject and teacher for a cell. |
| GET | `/api/periods` | admin | List periods. |
| POST | `/api/periods` | admin | Create period. |

## Settings

| Method | Path | Role | Notes |
|--------|------|------|-------|
| GET | `/api/settings` | admin | School profile. |
| POST | `/api/settings` | admin | Update name, tagline, currency, grading, logo. |
| GET | `/api/users` | admin | Administrator accounts. |
| POST | `/api/users` | admin | Create admin user. |

## Record-level scoping

- **Admin** — full access.
- **Teacher** — students, attendance, marks and routine limited to assigned classes/sections.
- **Student** — only their own profile, attendance, results, fees and routine.
