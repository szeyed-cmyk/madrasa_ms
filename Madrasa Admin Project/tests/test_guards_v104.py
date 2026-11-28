"""1.0.4 evidence tests for audit #3278/#3282: shared guard on every write route, DELETE role checks,
teacher marks scope, IDOR on student/receipt ids, no-store on password responses, no raw SQL, and
temporary passwords never stored in plain text."""

import re
import sqlite3
from pathlib import Path

import pytest
from conftest import first
from fastapi.routing import APIRoute

from app.api import router as api_router
from app.config import settings
from app.security import current_user, require_admin, require_staff, verify_password
from app.seed import NO_PASSWORD

APP = Path(__file__).resolve().parent.parent / "app"
WRITE = {"POST", "PUT", "DELETE"}
STAFF_WRITES = {  # the only writes a teacher may call; each body also checks the teacher's class scope
    ("POST", "/api/students/{student_pk}/subjects"),
    ("PUT", "/api/students/{student_pk}/subjects"),
    ("POST", "/api/students/{student_pk}/subjects/apply-class-defaults"),
    ("DELETE", "/api/students/{student_pk}/subjects/{subject_id}"),
    ("POST", "/api/students/{student_pk}/marks"),
    ("POST", "/api/marks/bulk"),
    ("POST", "/api/attendance"),
}


def _guards(route: APIRoute) -> set:
    return {d.call for d in route.dependant.dependencies}


ROUTES = [r for r in api_router.routes if isinstance(r, APIRoute)]
WRITE_ROUTES = [(m, r) for r in ROUTES for m in r.methods if m in WRITE]


def test_every_route_carries_csrf_and_a_role_guard():
    from app.security import csrf_protect

    for r in ROUTES:
        g = _guards(r)
        assert csrf_protect in g, r.path
        assert g & {require_admin, require_staff, current_user}, r.path


@pytest.mark.parametrize("method, route", WRITE_ROUTES, ids=[f"{m} {r.path}" for m, r in WRITE_ROUTES])
def test_every_write_route_uses_the_shared_role_guard(method, route):
    g = _guards(route)
    if (method, route.path) in STAFF_WRITES:
        assert require_staff in g
    else:
        assert require_admin in g, f"{method} {route.path} must depend on require_admin"


def test_every_delete_route_is_admin_or_scoped_staff():
    deletes = [(m, r.path) for m, r in WRITE_ROUTES if m == "DELETE"]
    assert len(deletes) >= 9
    for m, r in WRITE_ROUTES:
        if m == "DELETE" and (m, r.path) not in STAFF_WRITES:
            assert require_admin in _guards(r)


def _student(admin, code):
    return first(admin.get("/api/students").json(), student_id=code)


def test_teacher_marks_scope(admin, teacher):
    """Fixture teacher teaches Grade 1 only. Grade 5 student 000005 is out of scope."""
    exam = admin.get("/api/exams").json()[0]["id"]
    own, other = _student(admin, "000001"), _student(admin, "000005")
    own_subject = admin.get(f"/api/students/{own['id']}/subjects").json()[0]["id"]
    other_subject = admin.get(f"/api/students/{other['id']}/subjects").json()[0]["id"]
    ok = teacher.post(
        f"/api/students/{own['id']}/marks", json={"exam_id": exam, "subject_id": own_subject, "marks": 70}
    )
    assert ok.status_code == 200, ok.text
    r = teacher.post(
        f"/api/students/{other['id']}/marks", json={"exam_id": exam, "subject_id": other_subject, "marks": 1}
    )
    assert r.status_code == 403
    r = teacher.post(
        "/api/marks/bulk",
        json={"exam_id": exam, "entries": [{"student_id": other["id"], "subject_id": other_subject, "marks": 1}]},
    )
    assert r.status_code == 403
    g5 = first(admin.get("/api/classes").json(), name="Grade 5")["id"]
    assert teacher.get(f"/api/marks?exam_id={exam}&class_id={g5}").status_code == 403


def test_teacher_attendance_and_student_ids_are_scoped(admin, teacher):
    other = _student(admin, "000005")
    r = teacher.post(
        "/api/attendance", json={"date": "2026-01-10", "records": [{"student_id": other["id"], "status": "Present"}]}
    )
    assert r.status_code == 403
    assert teacher.get(f"/api/students/{other['id']}").status_code == 403
    assert teacher.delete(f"/api/students/{other['id']}/subjects/1").status_code == 403


def test_fee_and_receipt_ids_are_admin_only(admin, teacher, student):
    pay = admin.get("/api/payments").json()
    pid = (pay["payments"] if isinstance(pay, dict) else pay)[0]["id"]
    for c in (teacher, student):
        assert c.get(f"/api/receipt/{pid}").status_code == 403
        assert c.post(f"/api/payments/{pid}/void").status_code == 403
        assert c.get(f"/print/receipt/{pid}", follow_redirects=False).status_code in (303, 403)


def test_student_cannot_open_another_student(admin, student):
    other = _student(admin, "000002")
    assert student.get(f"/api/students/{other['id']}").status_code == 403
    assert student.get(f"/api/students/{other['id']}/profile").status_code == 403
    assert student.get(f"/api/students/{student.student_pk}").status_code == 200


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_delete_routes_refuse_non_admins(admin, teacher, student, role):
    c = teacher if role == "teacher" else student
    exam = admin.get("/api/exams").json()[0]["id"]
    for path in (
        f"/api/exams/{exam}",
        "/api/classes/1",
        "/api/sections/1",
        "/api/subjects/1",
        "/api/assignments/1",
        "/api/periods/1",
        "/api/routine/slot/1",
        "/api/students/1",
    ):
        assert c.delete(path).status_code == 403, path


def test_password_responses_are_never_cached(admin):
    r = admin.post("/api/teachers", json={"username": "nocache.t", "full_name": "No Cache"})
    assert r.status_code == 201 and r.json()["temporary_password"]
    assert r.headers["cache-control"] == "no-store"
    tid = r.json()["id"]
    r = admin.post(f"/api/teachers/{tid}/reset-password", json={})
    assert r.headers["cache-control"] == "no-store"


def test_temporary_password_is_only_stored_as_a_hash(admin):
    r = admin.post("/api/teachers", json={"username": "hash.t", "full_name": "Hash Check"})
    temp = r.json()["temporary_password"]
    sid = _student(admin, "000003")["id"]
    temp2 = admin.post(f"/api/students/{sid}/create-login", json={}).json()["temporary_password"]
    raw = b"".join(
        Path(str(settings.database_path) + s).read_bytes()
        for s in ("", "-wal")
        if Path(str(settings.database_path) + s).exists()
    )
    assert temp.encode() not in raw and temp2.encode() not in raw
    con = sqlite3.connect(settings.database_path)
    cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
    con.close()
    assert "password" not in cols and "password_hash" in cols


def test_no_password_sentinel_never_verifies():
    for pw in ("", NO_PASSWORD, "!no-password-set", "password"):
        assert not verify_password(pw, NO_PASSWORD)


SQL_FSTRING = re.compile(r"""f["'][^"']*\b(SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b""", re.I)


def test_no_text_sql_or_fstring_sql_in_app_code():
    """Evidence for docs/SECURITY-EVIDENCE.md: queries are SQLAlchemy expressions with bound parameters.
    The single allowed exception is migration 1 in app/database.py (ALTER TABLE ... ADD COLUMN), whose
    names come from app/models.py and pass _quote() (regex-whitelisted + dialect-quoted)."""
    for py in APP.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        text_calls = re.findall(r"(?<![\w.])text\(", src)
        hits = SQL_FSTRING.findall(src)
        if py.name == "database.py":
            assert len(text_calls) == 1 and "conn.execute(text(ddl + _sql_default(column)))" in src
            assert (
                hits == ["ALTER"]
                and "ALTER TABLE {_quote(eng, table.name)} ADD COLUMN {_quote(eng, column.name)}" in src
            )
            continue
        assert not text_calls, py
        assert not hits, py
        assert ".query(" not in src, py


def test_every_bulk_delete_has_a_where_clause():
    for py in APP.rglob("*.py"):
        for m in re.finditer(r"(?<![.\w])delete\((\w+)\)(.*)", py.read_text(encoding="utf-8")):
            assert ".where(" in m.group(2), f"{py.name}: delete({m.group(1)}) without where"


def test_login_throttle_is_persistent_across_restarts(fresh_db):
    from app.security import LoginThrottle

    first_process = LoginThrottle(limit=3, window=600)
    for _ in range(3):
        first_process.fail("10.0.0.9", "Admin")
    restarted = LoginThrottle(limit=3, window=600)  # new process / worker, same database
    assert restarted.blocked("10.0.0.9", "admin")
    assert not restarted.blocked("10.0.0.10", "admin")
    restarted.reset("10.0.0.9", "admin")
    assert not first_process.blocked("10.0.0.9", "admin")
