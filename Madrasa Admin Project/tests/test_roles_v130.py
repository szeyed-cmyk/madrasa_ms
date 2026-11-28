"""v1.3.0: Teachers page, student logins (single + bulk), role-scoped data for teachers and students, school logo."""

import base64
import sqlite3

import pytest
from conftest import ADMIN_PW, TEACHER_PW, csrf_from, first, login
from fastapi.testclient import TestClient

from app import __version__
from app.main import app

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()


def _cls(c, name="Grade 1"):
    return first(c.get("/api/classes").json(), name=name)


def _student_in(admin, class_name):
    cid = _cls(admin, class_name)["id"]
    return next(s for s in admin.get(f"/api/students?class_id={cid}").json())


def _new_client():
    return TestClient(app)


def test_version():
    assert __version__ == "1.0.8"


# ------------------------------------------------------------------ Teachers page (admin)
def test_add_teacher_with_generated_password_and_first_login(admin):
    r = admin.post("/api/teachers", json={"full_name": "Ustad Rahim", "username": "rahim", "phone": "01711111111"})
    assert r.status_code == 201, r.text
    body = r.json()
    temp = body["temporary_password"]
    assert temp and len(temp) >= 10 and body["username"] == "rahim"
    rows = admin.get("/api/teachers/manage").json()
    t = first(rows, username="rahim")
    assert t["phone"] == "01711111111" and t["is_active"] and t["must_change_password"] and t["assignments"] == []
    # first login must change the password, then lands on the dashboard
    with _new_client() as c:
        page = c.get("/login")
        r = c.post(
            "/login",
            data={"username": "rahim", "password": temp, "csrf_token": csrf_from(page.text)},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/change-password"
        assert c.get("/api/me").status_code == 403  # nothing works before the change
    with _new_client() as c:
        login(c, "rahim", temp, "Rahim#Pass2026")
        me = c.get("/api/me").json()
        assert me["role"] == "teacher" and me["phone"] == "01711111111"
        assert c.get("/dashboard").status_code == 200


def test_add_teacher_with_typed_password_and_validation(admin):
    ok = {"full_name": "Hafiz Bilal", "username": "bilal", "password": "Bilal#Pass2026"}
    r = admin.post("/api/teachers", json=ok)
    assert r.status_code == 201 and r.json()["temporary_password"] is None
    # duplicate username (case-insensitive), also against admins
    assert admin.post("/api/teachers", json={**ok, "username": "BILAL"}).status_code == 400
    assert admin.post("/api/teachers", json={**ok, "username": "admin"}).status_code == 400
    # password rules
    assert admin.post("/api/teachers", json={**ok, "username": "b2", "password": "short"}).status_code in (400, 422)
    assert admin.post("/api/teachers", json={**ok, "username": "b3x", "password": "short"}).status_code == 400
    assert admin.post("/api/teachers", json={**ok, "username": "b4x", "password": "password"}).status_code == 400
    # username and phone format
    assert admin.post("/api/teachers", json={**ok, "username": "bad name"}).status_code == 422
    assert admin.post("/api/teachers", json={**ok, "username": "b5x", "phone": "call me"}).status_code == 422
    assert admin.post("/api/teachers", json={"username": "b6x"}).status_code == 422


def test_edit_reset_disable_enable_teacher(admin, teacher):
    tid = first(admin.get("/api/teachers/manage").json(), username="teacher")["id"]
    r = admin.put(
        f"/api/teachers/{tid}", json={"full_name": "Class Teacher 2", "username": "teacher", "phone": "01800000000"}
    )
    assert r.status_code == 200
    assert admin.put(f"/api/teachers/{tid}", json={"full_name": "x", "username": "ADMIN"}).status_code == 400
    t = first(admin.get("/api/teachers/manage").json(), id=tid)
    assert t["full_name"] == "Class Teacher 2" and t["phone"] == "01800000000"
    assert t["classes"] == ["Grade 1"] and len(t["assignments"]) == 5
    # disable logs the teacher out at once; enable again
    assert admin.post(f"/api/teachers/{tid}/status", json={"is_active": False}).status_code == 200
    assert teacher.get("/api/dashboard").status_code == 401
    assert admin.post(f"/api/teachers/{tid}/status", json={"is_active": True}).status_code == 200
    # reset: new temporary password, must change again, old password stops working
    r = admin.post(f"/api/teachers/{tid}/reset-password", json={})
    temp = r.json()["temporary_password"]
    assert r.status_code == 200 and temp
    with _new_client() as c:
        page = c.get("/login")
        bad = c.post("/login", data={"username": "teacher", "password": TEACHER_PW, "csrf_token": csrf_from(page.text)})
        assert bad.status_code == 401 or "Invalid" in bad.text or "incorrect" in bad.text.lower()
    with _new_client() as c:
        login(c, "teacher", temp, "Teacher#Again2026")
    # typed password must follow the rules
    assert admin.post(f"/api/teachers/{tid}/reset-password", json={"password": "123"}).status_code == 400


def test_demo_teacher_needs_password_before_enable(admin):
    karim = first(admin.get("/api/teachers/manage").json(), username="demo.karim")
    assert not karim["has_password"] and not karim["is_active"] and karim["assignments"]
    assert admin.post(f"/api/teachers/{karim['id']}/status", json={"is_active": True}).status_code == 400
    r = admin.post(f"/api/teachers/{karim['id']}/reset-password", json={"password": "Karim#Pass2026"})
    assert r.status_code == 200 and r.json()["is_active"] is True
    with _new_client() as c:
        login(c, "demo.karim", "Karim#Pass2026", "Karim#New2026x")
        assert c.get("/api/dashboard").status_code == 200


def test_teacher_endpoints_reject_non_admin_and_admin_targets(admin, teacher, student):
    admin_id = first(admin.get("/api/users").json(), username="admin")["id"]
    assert admin.post(f"/api/teachers/{admin_id}/reset-password", json={}).status_code == 404
    assert admin.post(f"/api/teachers/{admin_id}/status", json={"is_active": False}).status_code == 404
    assert admin.put("/api/teachers/99999", json={"full_name": "x", "username": "xyz"}).status_code == 404
    for c in (teacher, student):
        assert c.get("/api/teachers/manage").status_code == 403
        assert c.post("/api/teachers", json={"full_name": "x", "username": "xyz"}).status_code == 403
        assert c.post(f"/api/teachers/{admin_id}/reset-password", json={}).status_code == 403
        assert c.post(f"/api/teachers/{admin_id}/status", json={"is_active": False}).status_code == 403
        assert c.put(f"/api/teachers/{admin_id}", json={"full_name": "x", "username": "xyz"}).status_code == 403
        assert c.get("/api/student-logins").status_code == 403
        assert c.post("/api/student-logins/bulk", json={"class_id": 1}).status_code == 403
        assert c.post("/api/students/1/enable-login").status_code == 403
        assert c.get("/api/users").status_code == 403


def test_new_endpoints_need_csrf(admin):
    tok = admin.headers.pop("X-CSRF-Token")
    try:
        assert admin.post("/api/teachers", json={"full_name": "x", "username": "xyz"}).status_code == 403
        assert admin.post("/api/student-logins/bulk", json={"class_id": 1}).status_code == 403
        assert admin.post("/api/teachers/1/reset-password", json={}).status_code == 403
    finally:
        admin.headers["X-CSRF-Token"] = tok


# ------------------------------------------------------------------ student logins
def test_bulk_student_logins_and_slip_data(admin):
    g1 = _cls(admin)
    rows = admin.get(f"/api/student-logins?class_id={g1['id']}").json()
    assert rows and not any(r["has_login"] for r in rows)
    r = admin.post("/api/student-logins/bulk", json={"class_id": g1["id"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] == len(rows) and data["reset"] == 0 and not data["skipped"]
    creds = data["credentials"]
    assert {c["username"] for c in creds} == {r["student_id"] for r in rows}
    assert all(len(c["password"]) >= 10 and c["class_name"] == "Grade 1" for c in creds)
    # passwords are never stored or listed in clear text
    listed = admin.get(f"/api/student-logins?class_id={g1['id']}").json()
    assert all(r["has_login"] and r["is_active"] and r["must_change"] for r in listed)
    assert creds[0]["password"] not in str(listed)
    # second run: nothing new; reset_existing gives everyone a new password
    again = admin.post("/api/student-logins/bulk", json={"class_id": g1["id"]}).json()
    assert again["created"] == 0 and again["credentials"] == []
    reset = admin.post("/api/student-logins/bulk", json={"class_id": g1["id"], "reset_existing": True}).json()
    assert reset["reset"] == len(rows) and reset["credentials"][0]["password"] != creds[0]["password"]
    # a slip credential works and forces a password change; the student lands on their own profile
    c0 = next(c for c in reset["credentials"] if c["student_pk"] == creds[0]["student_pk"])
    with _new_client() as c:
        login(c, c0["username"], c0["password"], "Student#New2026")
        r = c.get("/dashboard", follow_redirects=False)
        assert r.headers["location"] == f"/student/{c0['student_pk']}"
    # validation
    assert admin.post("/api/student-logins/bulk", json={"class_id": 99999}).status_code == 404
    g5 = _cls(admin, "Grade 5")
    assert (
        admin.post(
            "/api/student-logins/bulk", json={"class_id": g1["id"], "section_id": g5["sections"][0]["id"]}
        ).status_code
        == 400
    )


def test_single_student_login_reset_keeps_username_and_enable(admin):
    s = _student_in(admin, "Grade 5")
    r = admin.post(f"/api/students/{s['id']}/create-login", json={"username": "kid5"}).json()
    assert r["username"] == "kid5" and r["temporary_password"]
    r2 = admin.post(f"/api/students/{s['id']}/create-login", json={}).json()
    assert r2["username"] == "kid5" and r2["temporary_password"] != r["temporary_password"]
    assert admin.post(f"/api/students/{s['id']}/disable-login").status_code == 200
    assert admin.get(f"/api/students/{s['id']}/login-status").json()["is_active"] is False
    assert admin.post(f"/api/students/{s['id']}/enable-login").status_code == 200
    assert admin.get(f"/api/students/{s['id']}/login-status").json()["is_active"] is True
    other = _student_in(admin, "Grade 1")
    assert admin.post(f"/api/students/{other['id']}/enable-login").status_code == 400  # no login yet
    assert admin.post("/api/students/99999/enable-login").status_code == 404


# ------------------------------------------------------------------ teacher scope (server-side)
def test_teacher_sees_only_own_classes(admin, teacher):
    g1, g5 = _cls(admin), _cls(admin, "Grade 5")
    own, other = _student_in(admin, "Grade 1"), _student_in(admin, "Grade 5")
    studs = teacher.get("/api/students").json()
    assert studs and {s["class_name"] for s in studs} == {"Grade 1"}
    assert teacher.get(f"/api/students?class_id={g5['id']}").json() == []
    assert [c["name"] for c in teacher.get("/api/classes").json()] == ["Grade 1"]
    assert teacher.get("/api/classes").json()[0]["monthly_fee"] is None
    # profile / record / page / print of a student outside their classes
    assert teacher.get(f"/api/students/{own['id']}/profile").status_code == 200
    for url in (
        f"/api/students/{other['id']}",
        f"/api/students/{other['id']}/profile",
        f"/api/students/{other['id']}/subjects",
        f"/student/{other['id']}",
        f"/print/result/{other['id']}",
    ):
        assert teacher.get(url).status_code == 403, url
    assert teacher.post(f"/api/students/{other['id']}/subjects", json={"subject_id": 1}).status_code == 403
    assert teacher.delete(f"/api/students/{other['id']}/subjects/1").status_code == 403
    assert teacher.put(f"/api/students/{other['id']}/subjects", json={"subject_ids": []}).status_code == 403
    assert teacher.post(f"/api/students/{other['id']}/subjects/apply-class-defaults").status_code == 403
    # attendance and marks for another class
    today = "2026-01-10"
    assert teacher.get(f"/api/attendance?date={today}&class_id={g5['id']}").status_code == 403
    all_att = teacher.get(f"/api/attendance?date={today}").json()["students"]
    assert all_att and {s["class_name"] for s in all_att} == {"Grade 1"}
    r = teacher.post(
        "/api/attendance", json={"date": today, "records": [{"student_id": other["id"], "status": "Present"}]}
    )
    assert r.status_code == 403
    assert teacher.get(f"/api/attendance/report?month=2026-01&class_id={g5['id']}").status_code == 403
    exam = admin.get("/api/exams").json()[0]["id"]
    assert teacher.get(f"/api/marks?exam_id={exam}&class_id={g5['id']}").status_code == 403
    assert teacher.get(f"/api/results?exam_id={exam}&class_id={g5['id']}").status_code == 403
    # routine: own sections only; other teachers and their assignments are hidden
    assert teacher.get(f"/api/routine?section_id={g5['sections'][0]['id']}").status_code == 403
    assert teacher.get(f"/api/routine?section_id={g1['sections'][0]['id']}").status_code == 200
    assert teacher.get(f"/print/routine?section_id={g5['sections'][0]['id']}").status_code == 403
    me = teacher.get("/api/me").json()["id"]
    assert [t["id"] for t in teacher.get("/api/teachers").json()] == [me]
    karim = first(admin.get("/api/teachers").json(), username="demo.karim")["id"]
    asg = teacher.get(f"/api/assignments?teacher_id={karim}").json()
    assert asg and all(a["teacher_id"] == me for a in asg)
    # printouts are scoped too
    page = teacher.get("/print/students").text
    assert own["name"] in page and other["name"] not in page
    # fees, settings, user management stay admin-only
    for url in ("/api/payments", "/api/fees/dues", "/api/users", "/api/teachers/manage", "/print/dues"):
        assert teacher.get(url).status_code == 403, url


def test_teacher_dashboard_is_scoped(admin, teacher):
    d = teacher.get("/api/dashboard").json()
    a = admin.get("/api/dashboard").json()
    assert d["students"] < a["students"] and d["classes"] == 1 and d["my_assignments"] == 5
    assert "collected" not in d and "recent_payments" not in d
    assert all(x["kind"] != "payment" for x in d["activity"])


def test_teacher_without_assignments_sees_nothing(admin):
    admin.post("/api/teachers", json={"full_name": "New Ustad", "username": "newustad", "password": "Ustad#Pass2026"})
    with _new_client() as c:
        login(c, "newustad", "Ustad#Pass2026", "Ustad#New20261")
        assert c.get("/api/students").json() == []
        assert c.get("/api/classes").json() == []
        assert c.get("/api/results").json()["results"] == []
        d = c.get("/api/dashboard").json()
        assert d["students"] == 0 and d["my_assignments"] == 0
        assert c.get("/dashboard").status_code == 200


def test_section_assignment_limits_scope_to_that_section(admin):
    g1 = _cls(admin)
    admin.post("/api/sections", json={"class_id": g1["id"], "name": "B"})
    g1 = _cls(admin)
    sec_b = first(g1["sections"], name="B")["id"]
    sec_a = first(g1["sections"], name="A")["id"]
    r = admin.post("/api/teachers", json={"full_name": "Sec B", "username": "secb", "password": "SecB#Pass2026"})
    tid = r.json()["id"]
    sub = g1["subject_ids"][0]
    assert (
        admin.post(
            "/api/assignments", json={"teacher_id": tid, "class_id": g1["id"], "section_id": sec_b, "subject_id": sub}
        ).status_code
        == 201
    )
    with _new_client() as c:
        login(c, "secb", "SecB#Pass2026", "SecB#New20261")
        assert c.get("/api/students").json() == []  # every Grade 1 student is in section A
        cls = c.get("/api/classes").json()
        assert [s["id"] for s in cls[0]["sections"]] == [sec_b]
        assert c.get(f"/api/attendance?date=2026-01-10&class_id={g1['id']}&section_id={sec_a}").status_code == 403
        assert c.get(f"/api/attendance?date=2026-01-10&class_id={g1['id']}&section_id={sec_b}").status_code == 200


# ------------------------------------------------------------------ student scope (IDOR)
def test_student_only_sees_own_data(admin, student):
    own = student.student_pk
    others = [s["id"] for s in admin.get("/api/students").json() if s["id"] != own]
    for oid in others[:5]:
        for url in (f"/api/students/{oid}/profile", f"/api/students/{oid}/subjects", f"/print/result/{oid}"):
            assert student.get(url).status_code == 403, url
    # routine: always their own section, whatever section_id is asked for
    g5 = _cls(admin, "Grade 5")
    r = student.get(f"/api/routine?section_id={g5['sections'][0]['id']}").json()
    me = admin.get(f"/api/students/{own}").json()
    assert r["section_id"] == me["section_id"]
    assert student.get("/api/my/results").status_code == 200
    p = student.get(f"/api/students/{own}/profile").json()
    assert "fees" in p and "login" not in p
    for url in (
        "/api/students",
        "/api/dashboard",
        "/api/attendance?date=2026-01-10",
        "/api/payments",
        "/api/assignments",
        "/api/teachers",
        "/api/results",
        "/print/students",
        "/print/attendance",
    ):
        assert student.get(url).status_code == 403, url


# ------------------------------------------------------------------ menus / landing per role
def test_menus_per_role(admin, teacher, student):
    a = admin.get("/dashboard").text
    for label in ('data-nav="teachers"', 'data-nav="logins"', 'data-nav="fees"', 'data-nav="settings"', "School logo"):
        assert label in a
    t = teacher.get("/dashboard").text
    assert "My students" in t and "My routine" in t and "My subjects" in t
    for label in (
        'data-nav="teachers"',
        'data-nav="logins"',
        'data-nav="fees"',
        'data-nav="settings"',
        "data-teacher-form",
    ):
        assert label not in t
    s = student.get(f"/student/{student.student_pk}").text
    assert "My results" in s and "My attendance" in s and "My fees" in s
    assert 'data-nav="students"' not in s
    # the login card (and its admin-only links) is rendered on the server for administrators only
    assert "Student portal login" not in s and "/#logins" not in s
    assert "Student portal login" in admin.get(f"/student/{student.student_pk}").text


# ------------------------------------------------------------------ school logo
def test_logo_change_remove_and_shown_everywhere(admin, anon):
    assert admin.post("/api/settings", json={"logo": PNG_URL}).status_code == 200
    assert admin.get("/api/settings").json()["logo"] == PNG_URL
    assert PNG_URL in admin.get("/dashboard").text  # sidebar
    sid = admin.get("/api/students").json()[0]["id"]
    assert PNG_URL in admin.get(f"/print/result/{sid}").text  # print header
    with TestClient(app) as c:
        assert PNG_URL in c.get("/login").text  # login page
    assert admin.post("/api/settings", json={"logo": "data:image/png;base64,AAAA"}).status_code == 400
    assert admin.post("/api/settings", json={"logo": ""}).status_code == 200
    assert admin.get("/api/settings").json()["logo"] is None
    assert PNG_URL not in admin.get("/dashboard").text


def _setup_post(client, **files):
    page = client.get("/setup")
    data = {
        "app_name": "Logo Madrasa",
        "tagline": "",
        "username": "admin",
        "full_name": "Admin",
        "password": ADMIN_PW,
        "confirm_password": ADMIN_PW,
        "csrf_token": csrf_from(page.text),
    }
    return client.post("/setup", data=data, files=files or None, follow_redirects=False)


def test_setup_with_logo(blank):
    assert 'name="logo"' in blank.get("/setup").text and "multipart/form-data" in blank.get("/setup").text
    r = _setup_post(blank, logo=("logo.png", PNG, "image/png"))
    assert r.status_code == 303, r.text
    assert blank.get("/api/settings").json()["logo"] == PNG_URL


@pytest.mark.parametrize(
    "payload,message",
    [(b"not an image at all", "PNG, JPEG"), (b"\x89PNG" + b"0" * (301 * 1024), "too large")],
)
def test_setup_rejects_bad_logo(blank, payload, message):
    r = _setup_post(blank, logo=("logo.png", payload, "image/png"))
    assert r.status_code == 400 and message in r.text
    assert blank.get("/setup").status_code == 200  # nothing was created


def test_setup_without_logo_still_works(blank):
    r = _setup_post(blank)
    assert r.status_code == 303
    assert blank.get("/api/settings").json()["logo"] is None


# ------------------------------------------------------------------ migration from 1.2.0
def test_migration_adds_user_phone_without_data_loss(tmp_path):
    from app.database import make_engine, migrate

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE,
          password_hash VARCHAR(255) NOT NULL,
          role VARCHAR(16) NOT NULL, full_name VARCHAR(120), is_active BOOLEAN, student_id INTEGER,
          must_change_password BOOLEAN, created_at DATETIME, last_login DATETIME);
        INSERT INTO users (username, password_hash, role, full_name, is_active, must_change_password)
          VALUES ('oldteacher', 'x$y', 'teacher', 'Old Teacher', 1, 0);
        """
    )
    con.commit()
    con.close()
    eng = make_engine(db)
    added = migrate(eng)
    assert "users.phone" in added
    eng.dispose()
    con = sqlite3.connect(db)
    row = con.execute("SELECT username, full_name, role, phone FROM users").fetchone()
    con.close()
    assert row == ("oldteacher", "Old Teacher", "teacher", None)
