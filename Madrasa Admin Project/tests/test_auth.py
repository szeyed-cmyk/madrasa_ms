"""Login, sessions, CSRF, password rules, role checks on every API route."""

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api import router as api_router
from app.main import app
from tests.conftest import ADMIN_PW, TEACHER_TEMP_PW, csrf_from, login

API_ROUTES = sorted({(m, r.path) for r in api_router.routes if isinstance(r, APIRoute) for m in r.methods})
PAGE_ROUTES = sorted(
    {
        r.path
        for r in app.routes
        if isinstance(r, APIRoute)
        and "GET" in r.methods
        and (r.path.startswith("/print/") or r.path.startswith("/student/") or r.path == "/dashboard")
    }
)


def _fill(path: str) -> str:
    return re.sub(r"{[^}]+}", "1", path)


def test_login_page_shows_no_default_credentials(anon):
    r = anon.get("/login")
    assert r.status_code == 200
    for text in ("admin123", "teacher123", "First run", "default password"):
        assert text not in r.text, text
    assert "Teachers and students get their logins from the administrator." in r.text
    assert "Developer" not in r.text or "@" not in r.text


def test_old_default_passwords_do_not_work(anon):
    tok = csrf_from(anon.get("/login").text)
    for user, pw in (("admin", "admin123"), ("teacher", "teacher123")):
        r = anon.post("/login", data={"username": user, "password": pw, "csrf_token": tok})
        assert r.status_code == 400 and "Invalid username or password" in r.text


def test_wrong_password_and_throttle(anon):
    tok = csrf_from(anon.get("/login").text)
    for _ in range(5):
        r = anon.post("/login", data={"username": "admin", "password": "nope", "csrf_token": tok})
        assert r.status_code == 400
        assert "Invalid username or password" in r.text
    r = anon.post("/login", data={"username": "admin", "password": ADMIN_PW, "csrf_token": tok})
    assert r.status_code == 429


def test_login_requires_csrf(anon):
    anon.get("/login")
    r = anon.post("/login", data={"username": "admin", "password": ADMIN_PW})
    assert r.status_code == 403


def test_forged_legacy_cookie_is_rejected(anon):
    # v1.0 trusted a plain "user=admin" cookie: anyone could become admin.
    anon.cookies.set("user", "admin")
    assert anon.get("/api/dashboard").status_code == 401
    assert anon.get("/api/students").status_code == 401
    r = anon.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_tampered_session_cookie_rejected(admin):
    cookie = admin.cookies.get("madrasa_session")
    admin.cookies.clear()
    admin.cookies.set("madrasa_session", cookie[:-6] + ("AAAAAA" if not cookie.endswith("AAAAAA") else "BBBBBB"))
    assert admin.get("/api/dashboard").status_code == 401


def test_password_change_is_enforced(anon):
    # Accounts created by the admin get a temporary password that must be changed at first login.
    tok = csrf_from(anon.get("/login").text)
    r = anon.post(
        "/login", data={"username": "teacher", "password": TEACHER_TEMP_PW, "csrf_token": tok}, follow_redirects=False
    )
    assert r.headers["location"] == "/change-password"
    assert anon.get("/api/dashboard").status_code == 403
    r = anon.get("/dashboard", follow_redirects=False)
    assert r.headers["location"] == "/change-password"


@pytest.mark.parametrize(
    "current,new,confirm,msg",
    [
        ("wrong", "Good#Pass123", "Good#Pass123", "Current password is wrong"),
        (TEACHER_TEMP_PW, "Good#Pass123", "Other#Pass123", "do not match"),
        (TEACHER_TEMP_PW, "short", "short", "at least 8"),
        (TEACHER_TEMP_PW, "password", "password", "too common"),
        (TEACHER_TEMP_PW, TEACHER_TEMP_PW, TEACHER_TEMP_PW, "different"),
    ],
)
def test_change_password_validation(anon, current, new, confirm, msg):
    tok = csrf_from(anon.get("/login").text)
    anon.post("/login", data={"username": "teacher", "password": TEACHER_TEMP_PW, "csrf_token": tok})
    tok = csrf_from(anon.get("/change-password").text)
    r = anon.post(
        "/change-password",
        data={"current_password": current, "new_password": new, "confirm_password": confirm, "csrf_token": tok},
    )
    assert r.status_code == 400
    assert msg in r.text


def test_password_change_logs_out_other_sessions(admin):
    with TestClient(app) as other:
        login(other, "admin", ADMIN_PW)
        assert other.get("/api/dashboard").status_code == 200
        tok = csrf_from(admin.get("/change-password").text)
        r = admin.post(
            "/change-password",
            data={
                "current_password": ADMIN_PW,
                "new_password": "Brand#New2026",
                "confirm_password": "Brand#New2026",
                "csrf_token": tok,
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert other.get("/api/dashboard").status_code == 401
        assert admin.get("/api/dashboard").status_code == 200


def test_logout_requires_post_with_csrf(admin):
    r = admin.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert admin.get("/api/dashboard").status_code == 200  # GET does not log out
    r = admin.post("/logout", data={"csrf_token": "bad"})
    assert r.status_code == 403
    tok = csrf_from(admin.get("/dashboard").text)
    r = admin.post("/logout", data={"csrf_token": tok}, follow_redirects=False)
    assert r.headers["location"] == "/login"
    assert admin.get("/api/dashboard").status_code == 401


def test_api_writes_need_csrf_header(admin):
    good = admin.headers.pop("X-CSRF-Token")
    assert admin.post("/api/classes", json={"name": "X1"}).status_code == 403
    assert admin.post("/api/classes", json={"name": "X1"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert admin.post("/api/classes", json={"name": "X1"}, headers={"X-CSRF-Token": good}).status_code == 201


def test_legacy_password_hash_still_works_and_is_upgraded(anon):
    import hashlib

    from app.database import SessionLocal
    from app.models import User

    salt = "abcd" * 8
    legacy = f"{salt}${hashlib.pbkdf2_hmac('sha256', b'Legacy#Pass1', salt.encode(), 100000).hex()}"
    db = SessionLocal()
    db.add(
        User(
            username="old",
            password_hash=legacy,
            role="teacher",
            full_name="Old",
            must_change_password=False,
            is_active=True,
        )
    )
    db.commit()
    login(anon, "old", "Legacy#Pass1")
    db.expire_all()
    assert db.query(User).filter_by(username="old").one().password_hash.startswith("pbkdf2_sha256$")
    db.close()


def test_security_headers(anon):
    r = anon.get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    cookie = r.headers.get("set-cookie", "")
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()


def test_docs_disabled(anon):
    assert anon.get("/docs").status_code == 404
    assert anon.get("/openapi.json").status_code == 404


def test_api_route_count():
    assert len(API_ROUTES) >= 55


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_every_page_redirects_to_login(anon, path):
    r = anon.get(_fill(path) + "?exam_id=1", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login", (path, r.status_code)


@pytest.mark.parametrize("method,path", API_ROUTES)
def test_every_api_route_requires_login(anon, method, path):
    tok = csrf_from(anon.get("/login").text)
    r = anon.request(method, _fill(path), headers={"X-CSRF-Token": tok})
    assert r.status_code == 401, (method, path, r.status_code, r.text)


ADMIN_ONLY = [
    ("POST", "/api/students", {"name": "X", "class_id": 1, "section_id": 1}),
    ("PUT", "/api/students/1", {"name": "X", "class_id": 1, "section_id": 1}),
    ("DELETE", "/api/students/1", None),
    ("POST", "/api/students/1/status", {"status": "Archived"}),
    ("GET", "/api/students/export.csv", None),
    ("POST", "/api/classes", {"name": "Z"}),
    ("PUT", "/api/classes/1", {"name": "Z"}),
    ("DELETE", "/api/classes/1", None),
    ("POST", "/api/sections", {"class_id": 1, "name": "Z"}),
    ("DELETE", "/api/sections/1", None),
    ("POST", "/api/subjects", {"name": "Z"}),
    ("PUT", "/api/subjects/1", {"name": "Z"}),
    ("DELETE", "/api/subjects/1", None),
    ("PUT", "/api/classes/1/subjects", {"subject_ids": []}),
    ("POST", "/api/classes/1/subjects/apply", None),
    ("POST", "/api/exams", {"name": "Z"}),
    ("PUT", "/api/exams/1", {"name": "Z"}),
    ("DELETE", "/api/exams/1", None),
    ("GET", "/api/payments", None),
    ("POST", "/api/payments", {"student_id": 1, "amount": 10}),
    ("POST", "/api/payments/1/void", None),
    ("GET", "/api/receipt/1", None),
    ("GET", "/api/fees/plans", None),
    ("PUT", "/api/fees/plans", {"class_id": 1, "amount": 5}),
    ("GET", "/api/fees/dues", None),
    ("POST", "/api/assignments", {"teacher_id": 1, "class_id": 1, "subject_id": 1}),
    ("DELETE", "/api/assignments/1", None),
    ("POST", "/api/periods", {"name": "P", "start_time": "07:00", "end_time": "07:30"}),
    ("PUT", "/api/periods/1", {"name": "P", "start_time": "07:00", "end_time": "07:30"}),
    ("DELETE", "/api/periods/1", None),
    ("PUT", "/api/routine/slot", {"class_id": 1, "section_id": 1, "day": "Sat", "period_id": 1, "subject_id": 1}),
    ("DELETE", "/api/routine/slot/1", None),
    ("POST", "/api/settings", {"name": "Hacked"}),
    ("GET", "/api/users", None),
    ("POST", "/api/users", {"username": "zz", "full_name": "z", "role": "admin", "password": "x" * 9}),
    ("PUT", "/api/users/1", {"is_active": False}),
    ("POST", "/api/students/1/create-login", {}),
    ("POST", "/api/students/1/disable-login", None),
    ("GET", "/api/students/1/login-status", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY)
def test_teacher_cannot_use_admin_routes(teacher, method, path, body):
    r = teacher.request(method, path, json=body)
    assert r.status_code == 403, (method, path, r.text)


STAFF_ONLY = [
    ("GET", "/api/dashboard", None),
    ("GET", "/api/students", None),
    ("GET", "/api/classes", None),
    ("GET", "/api/subjects", None),
    ("GET", "/api/results", None),
    ("GET", "/api/marks?exam_id=1&class_id=1", None),
    ("POST", "/api/marks/bulk", {"exam_id": 1, "entries": []}),
    ("POST", "/api/students/1/marks", {"exam_id": 1, "subject_id": 1, "marks": 100}),
    ("POST", "/api/students/1/subjects", {"subject_id": 1}),
    ("PUT", "/api/students/1/subjects", {"subject_ids": []}),
    ("DELETE", "/api/students/1/subjects/1", None),
    ("POST", "/api/students/1/subjects/apply-class-defaults", None),
    ("GET", "/api/attendance?date=2026-01-01", None),
    ("POST", "/api/attendance", {"date": "2026-01-01", "records": []}),
    ("GET", "/api/attendance/report?month=2026-01", None),
    ("GET", "/api/teachers", None),
    ("GET", "/api/assignments", None),
    ("GET", "/api/my/routine", None),
]


@pytest.mark.parametrize("method,path,body", STAFF_ONLY + ADMIN_ONLY)
def test_student_cannot_use_staff_routes(student, method, path, body):
    r = student.request(method, path, json=body)
    assert r.status_code == 403, (method, path, r.text)


def test_student_sees_only_own_record(student, admin):
    own = student.student_pk
    other = next(s["id"] for s in admin.get("/api/students").json() if s["id"] != own)
    assert student.get(f"/api/students/{own}/profile").status_code == 200
    assert student.get(f"/api/students/{own}").status_code == 200
    assert student.get(f"/api/students/{other}/profile").status_code == 403
    assert student.get(f"/api/students/{other}").status_code == 403
    assert student.get(f"/student/{other}").status_code == 403
    assert student.get(f"/print/result/{other}").status_code == 403
    r = student.get("/dashboard", follow_redirects=False)
    assert r.headers["location"] == f"/student/{own}"
    profile = student.get(f"/api/students/{own}/profile").json()
    assert "login" not in profile and "fees" in profile


def test_teacher_profile_has_no_fees_or_login(teacher):
    sid = teacher.get("/api/students").json()[0]["id"]
    p = teacher.get(f"/api/students/{sid}/profile").json()
    assert "fees" not in p and "login" not in p and p["subjects"]
    d = teacher.get("/api/dashboard").json()
    assert "collected" not in d


def test_disabled_user_is_logged_out(admin, teacher):
    users = admin.get("/api/users").json()
    tid = next(u["id"] for u in users if u["username"] == "teacher")
    assert admin.put(f"/api/users/{tid}", json={"is_active": False}).status_code == 200
    assert teacher.get("/api/dashboard").status_code == 401
