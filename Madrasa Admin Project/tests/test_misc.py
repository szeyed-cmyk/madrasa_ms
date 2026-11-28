"""Classes, settings, users, printing safety, error pages and upgrading a v1.0 database."""

import base64
import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import first, login

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def test_classes_and_sections(admin):
    r = admin.post("/api/classes", json={"name": "Grade 11"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert admin.post("/api/classes", json={"name": "grade 11"}).status_code == 400
    assert admin.post("/api/classes", json={"name": "   "}).status_code == 422
    c = first(admin.get("/api/classes").json(), id=cid)
    assert [s["name"] for s in c["sections"]] == ["A"]
    r = admin.post("/api/sections", json={"class_id": cid, "name": "B"})
    assert r.status_code == 201
    assert admin.post("/api/sections", json={"class_id": cid, "name": "b"}).status_code == 400
    assert admin.post("/api/sections", json={"class_id": 99999, "name": "Z"}).status_code == 404
    assert admin.put(f"/api/classes/{cid}", json={"name": "Grade Eleven"}).status_code == 200
    assert admin.put(f"/api/classes/{cid}", json={"name": "Grade 1"}).status_code == 400
    assert admin.delete(f"/api/sections/{r.json()['id']}").status_code == 200
    assert admin.delete(f"/api/classes/{cid}").status_code == 200
    g1 = first(admin.get("/api/classes").json(), name="Grade 1")
    assert admin.delete(f"/api/classes/{g1['id']}").status_code == 400  # has students
    assert admin.delete(f"/api/sections/{g1['sections'][0]['id']}").status_code == 400
    assert admin.delete("/api/classes/99999").status_code == 404


def test_settings_and_logo_validation(admin, teacher):
    assert (
        admin.post(
            "/api/settings",
            json={
                "name": "Darul Uloom Madrasa",
                "address": "Sylhet",
                "currency": "Tk",
                "logo": f"data:image/png;base64,{PNG}",
            },
        ).status_code
        == 200
    )
    s = teacher.get("/api/settings").json()
    assert s["name"] == "Darul Uloom Madrasa" and s["logo"].startswith("data:image/png") and s["currency"] == "Tk"
    svg = base64.b64encode(b"<svg onload=alert(1)>").decode()
    assert admin.post("/api/settings", json={"logo": f"data:image/svg+xml;base64,{svg}"}).status_code == 400
    assert admin.post("/api/settings", json={"logo": 'x" onerror="alert(1)'}).status_code == 400
    assert admin.post("/api/settings", json={"logo": f"data:image/jpeg;base64,{PNG}"}).status_code == 400  # wrong magic
    big = base64.b64encode(b"\x89PNG" + b"\x00" * 400_000).decode()
    assert admin.post("/api/settings", json={"logo": f"data:image/png;base64,{big}"}).status_code == 400
    assert admin.post("/api/settings", json={"name": ""}).status_code == 422
    assert admin.post("/api/settings", json={"logo": ""}).status_code == 200
    assert admin.get("/api/settings").json()["logo"] is None


def test_users_management(admin):
    r = admin.post(
        "/api/users",
        json={"username": "ustad", "full_name": "Ustad Karim", "role": "teacher", "password": "Ustad#Pass1"},
    )
    assert r.status_code == 201
    uid = r.json()["id"]
    assert (
        admin.post(
            "/api/users", json={"username": "USTAD", "full_name": "x", "role": "teacher", "password": "Ustad#Pass1"}
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/users", json={"username": "x y", "full_name": "x", "role": "teacher", "password": "Ustad#Pass1"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/users", json={"username": "boss", "full_name": "x", "role": "superuser", "password": "Ustad#Pass1"}
        ).status_code
        == 422
    )
    with TestClient(app) as t:
        login(t, "ustad", "Ustad#Pass1", "Ustad#Pass2")
        assert t.get("/api/students").status_code == 200
    assert admin.put(f"/api/users/{uid}", json={"password": "short"}).status_code == 400
    assert admin.put(f"/api/users/{uid}", json={"password": "Reset#Pass1"}).status_code == 200
    assert first(admin.get("/api/users").json(), id=uid)["must_change_password"] is True
    me = first(admin.get("/api/users").json(), username="admin")
    r = admin.put(f"/api/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400


def test_student_login_management(admin):
    s = first(admin.get("/api/students").json(), student_id="000002")
    r = admin.post(f"/api/students/{s['id']}/create-login", json={}).json()
    assert r["username"] == "000002" and len(r["temporary_password"]) >= 8
    st = admin.get(f"/api/students/{s['id']}/login-status").json()
    assert st == {"has_login": True, "username": "000002", "is_active": True, "must_change": True}
    assert admin.post(f"/api/students/{s['id']}/create-login", json={"password": "123"}).status_code == 400
    assert admin.post(f"/api/students/{s['id']}/create-login", json={"username": "admin"}).status_code == 400
    with TestClient(app) as c:
        login(c, "000002", r["temporary_password"], "Fatima#Pass1")
        assert c.get(f"/api/students/{s['id']}/profile").status_code == 200
        assert admin.post(f"/api/students/{s['id']}/disable-login").status_code == 200
        assert c.get(f"/api/students/{s['id']}/profile").status_code == 401


def test_print_pages_escape_html(admin):
    g2 = first(admin.get("/api/classes").json(), name="Grade 2")
    evil = "<script>alert(1)</script>"
    sid = admin.post(
        "/api/students",
        json={"name": evil, "class_id": g2["id"], "section_id": g2["sections"][0]["id"], "guardian_name": evil},
    ).json()["id"]
    pid = admin.post("/api/payments", json={"student_id": sid, "amount": 10, "note": evil}).json()["id"]
    exam = admin.get("/api/exams").json()[0]
    for url in (
        f"/print/result/{sid}?exam_id={exam['id']}",
        f"/print/receipt/{pid}",
        f"/student/{sid}",
        f"/print/students?class_id={g2['id']}",
        f"/print/attendance?class_id={g2['id']}",
    ):
        r = admin.get(url)
        assert r.status_code == 200, url
        assert evil not in r.text and "&lt;script&gt;" in r.text, url


def test_index_page_renders_for_staff(admin, teacher):
    r = admin.get("/dashboard")
    assert r.status_code == 200 and "adminApp()" in r.text and "Settings" in r.text
    r = teacher.get("/dashboard")
    assert r.status_code == 200 and "adminApp()" in r.text
    for marker in (
        'data-nav="settings"',
        'data-nav="fees"',
        'data-nav="classes"',
        "page === 'fees'",
        "page === 'settings'",
        "Recent payments",
    ):
        assert marker not in r.text, marker


def test_no_contact_details_in_ui(admin):
    html = admin.get("/dashboard").text + admin.get("/login").text
    assert "Developer: Syed Abue Tayeb Al-Zeyed" in html
    assert "@gmail" not in html and "mailto:" not in html


def test_error_pages_and_static(anon, admin):
    assert anon.get("/healthz").json()["ok"] is True
    r = admin.get("/student/abc")
    assert r.status_code == 422 and "<html" in r.text
    assert admin.get("/api/students/abc").status_code == 422
    assert admin.get("/nope").status_code == 404
    for f in (
        "/static/app.css",
        "/static/js/app.js",
        "/static/js/common.js",
        "/static/js/student.js",
        "/static/js/print.js",
        "/static/vendor/alpine.min.js",
        "/static/favicon.svg",
    ):
        assert anon.get(f).status_code == 200, f


def _legacy_db(path):
    """The exact v1.0 schema plus a little data, including the v1.0 password-hash format."""
    import hashlib

    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR UNIQUE, password_hash VARCHAR, role VARCHAR,
        full_name VARCHAR, is_active BOOLEAN, student_id INTEGER, must_change_password BOOLEAN);
    CREATE TABLE school_settings (id INTEGER PRIMARY KEY, name VARCHAR, logo_path VARCHAR, address VARCHAR);
    CREATE TABLE academic_years (id INTEGER PRIMARY KEY, name VARCHAR, is_current BOOLEAN);
    CREATE TABLE classes (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE, "order" INTEGER);
    CREATE TABLE sections (id INTEGER PRIMARY KEY, name VARCHAR, class_id INTEGER);
    CREATE TABLE students (id INTEGER PRIMARY KEY, student_id VARCHAR UNIQUE, admission_no VARCHAR UNIQUE, name VARCHAR,
        dob VARCHAR, gender VARCHAR, class_id INTEGER, section_id INTEGER, admission_date VARCHAR, status VARCHAR,
        address VARCHAR, guardian_name VARCHAR, guardian_relation VARCHAR, guardian_phone VARCHAR, guardian_address VARCHAR);
    CREATE TABLE attendance (id INTEGER PRIMARY KEY, student_id INTEGER, date VARCHAR, status VARCHAR, marked_by VARCHAR, updated_at DATETIME);
    CREATE TABLE fee_plans (id INTEGER PRIMARY KEY, class_id INTEGER, fee_head VARCHAR, amount FLOAT);
    CREATE TABLE payments (id INTEGER PRIMARY KEY, student_id INTEGER, amount FLOAT, date VARCHAR, method VARCHAR,
        receipt_no VARCHAR UNIQUE, note VARCHAR, collected_by VARCHAR);
    CREATE TABLE subjects (id INTEGER PRIMARY KEY, name VARCHAR UNIQUE, max_marks FLOAT, credits FLOAT);
    CREATE TABLE student_subjects (id INTEGER PRIMARY KEY, student_id INTEGER, subject_id INTEGER, is_active BOOLEAN);
    CREATE TABLE exams (id INTEGER PRIMARY KEY, name VARCHAR, academic_year_id INTEGER);
    CREATE TABLE marks (id INTEGER PRIMARY KEY, student_id INTEGER, exam_id INTEGER, subject_id INTEGER,
        marks_obtained FLOAT, max_marks FLOAT);
    CREATE TABLE sms_logs (id INTEGER PRIMARY KEY, to_number VARCHAR, message VARCHAR, date DATETIME, type VARCHAR, status VARCHAR);
    INSERT INTO school_settings VALUES (1, 'Old Madrasa', NULL, 'Dhaka');
    INSERT INTO academic_years VALUES (1, '2026', 1);
    INSERT INTO classes VALUES (1, 'Grade 1', 1);
    INSERT INTO sections VALUES (1, 'A', 1);
    INSERT INTO students VALUES (1, '000001', 'ADM-1', 'Legacy Kid', NULL, 'Male', 1, 1, '2026-01-10', 'Active', NULL,
        'Dad', 'Father', '01711111111', NULL);
    INSERT INTO subjects VALUES (1, 'Bangla', 100, 3.0), (2, 'Math', 100, 3.0);
    INSERT INTO exams VALUES (1, '1st Term', 1);
    INSERT INTO marks VALUES (1, 1, 1, 1, 85, 100), (2, 1, 1, 2, 72, 100);
    INSERT INTO payments VALUES (1, 1, 1500, '2026-02-01', 'Cash', 'RCP-2026-00001', NULL, 'admin');
    """)
    salt = "f" * 32
    legacy = f"{salt}${hashlib.pbkdf2_hmac('sha256', b'Legacy#Admin1', salt.encode(), 100000).hex()}"
    con.execute("INSERT INTO users VALUES (1, 'admin', ?, 'admin', 'Administrator', 1, NULL, 0)", (legacy,))
    con.commit()
    con.close()


def test_upgrade_from_v1_database(tmp_path):
    from sqlalchemy.orm import sessionmaker

    from app.database import make_engine, migrate
    from app.models import Payment, StudentSubject
    from app.seed import seed
    from app.services import student_result

    path = tmp_path / "legacy.db"
    _legacy_db(path)
    eng = make_engine(path)
    added = migrate(eng)
    assert "students.roll_no" in added and "subjects.pass_marks" in added and "payments.fee_month" in added
    assert migrate(eng) == []  # idempotent
    from sqlalchemy import inspect

    tables = set(inspect(eng).get_table_names())
    assert "sms_logs" not in tables  # SMS removed in 1.2.0
    assert {"periods", "teacher_subjects", "routine_slots"} <= tables
    assert "school_settings.working_days" in added
    db = sessionmaker(bind=eng)()
    seed(db, demo=False)
    # v1.0 marks had no subject assignment, so results were empty: now repaired
    assert db.query(StudentSubject).count() == 2
    from app.models import Exam, Student

    r = student_result(db, db.get(Student, 1), db.get(Exam, 1), "standard")
    assert r["subjects_total"] == 2 and r["status"] == "Pass" and r["total_obtained"] == 157
    assert db.get(Payment, 1).fee_month == "2026-02"
    from app.models import User
    from app.security import verify_password

    assert verify_password("Legacy#Admin1", db.get(User, 1).password_hash)
    db.close()
    eng.dispose()
