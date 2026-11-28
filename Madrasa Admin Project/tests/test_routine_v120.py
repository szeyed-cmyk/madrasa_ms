"""v1.2.0: teacher-subject assignments, periods, weekly class routine, marks restriction, SMS removal."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import first


def _cls(c, name="Grade 1"):
    return first(c.get("/api/classes").json(), name=name)


def _subj(c, name):
    return first(c.get("/api/subjects").json(), name=name)


def _teacher_id(c, username="teacher"):
    return first(c.get("/api/teachers").json(), username=username)["id"]


def _teaching_period(c):
    return next(p for p in c.get("/api/periods").json() if not p["is_break"])


def _break_period(c):
    return next(p for p in c.get("/api/periods").json() if p["is_break"])


def _slot(c, cls, sec, day, period, subject, teacher=None, room=""):
    body = {"class_id": cls, "section_id": sec, "day": day, "period_id": period, "subject_id": subject, "room": room}
    if teacher is not None:
        body["teacher_id"] = teacher
    return c.put("/api/routine/slot", json=body)


# ------------------------------------------------------------------ demo data and defaults
def test_demo_periods_routine_and_assignments(admin):
    periods = admin.get("/api/periods").json()
    assert len(periods) == 7 and sum(p["is_break"] for p in periods) == 1
    assert [p["start_time"] for p in periods] == sorted(p["start_time"] for p in periods)
    g5 = _cls(admin, "Grade 5")
    r = admin.get(f"/api/routine?class_id={g5['id']}&section_id={g5['sections'][0]['id']}").json()
    assert r["days"] == ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
    assert len(r["slots"]) == 36  # 6 days x 6 teaching periods
    assert all(s["teacher_name"] for s in r["slots"])
    assert r["default_teachers"] and r["subject_ids"]
    assert admin.get("/api/assignments").json()
    assert admin.get("/api/routine").status_code == 400  # staff must choose a section


def test_no_teacher_is_double_booked_in_demo(admin):
    seen = set()
    for c in admin.get("/api/classes").json():
        for sec in c["sections"]:
            for s in admin.get(f"/api/routine?section_id={sec['id']}").json()["slots"]:
                if s["teacher_id"]:
                    key = (s["teacher_id"], s["day"], s["period_id"])
                    assert key not in seen, key
                    seen.add(key)


def test_working_days_setting(admin):
    s = admin.get("/api/settings").json()
    assert s["working_days"] == ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"] and len(s["all_days"]) == 7
    assert admin.post("/api/settings", json={"working_days": ["Thu", "Sat", "Fri"]}).status_code == 200
    assert admin.get("/api/settings").json()["working_days"] == ["Sat", "Thu", "Fri"]
    assert admin.post("/api/settings", json={"working_days": ["Xyz"]}).status_code == 422
    assert admin.post("/api/settings", json={"working_days": []}).status_code == 422
    g1 = _cls(admin)
    assert admin.get(f"/api/routine?section_id={g1['sections'][0]['id']}").json()["days"] == ["Sat", "Thu", "Fri"]


# ------------------------------------------------------------------ assignments
def test_assignment_crud_and_replace(admin):
    g1, tid = _cls(admin), _teacher_id(admin)
    eng = _subj(admin, "English")
    mine = admin.get(f"/api/assignments?teacher_id={tid}").json()
    assert {a["subject_id"] for a in mine} == set(g1["subject_ids"])  # conftest assigned all of Grade 1
    # assigning another teacher replaces the previous one for the same class/subject
    other = _teacher_id(admin, "demo.karim")
    r = admin.post("/api/assignments", json={"teacher_id": other, "class_id": g1["id"], "subject_id": eng["id"]})
    assert r.status_code == 201 and r.json()["replaced"] == "Class Teacher"
    rows = admin.get(f"/api/assignments?class_id={g1['id']}").json()
    assert [a["teacher_id"] for a in rows if a["subject_id"] == eng["id"] and a["section_id"] is None] == [other]
    # section-specific assignment wins over the class-wide one
    sec = g1["sections"][0]["id"]
    r = admin.post(
        "/api/assignments", json={"teacher_id": tid, "class_id": g1["id"], "section_id": sec, "subject_id": eng["id"]}
    )
    assert r.status_code == 201 and not r.json()["replaced"]
    assert admin.get(f"/api/routine?section_id={sec}").json()["default_teachers"][str(eng["id"])] == tid
    aid = r.json()["id"]
    assert admin.delete(f"/api/assignments/{aid}").status_code == 200
    assert admin.delete(f"/api/assignments/{aid}").status_code == 404


@pytest.mark.parametrize(
    "over,code",
    [
        ({"teacher_id": 99999}, 404),
        ({"class_id": 99999}, 404),
        ({"subject_id": 99999}, 404),
        ({"section_id": 99999}, 404),
    ],
)
def test_assignment_validation(admin, over, code):
    g1 = _cls(admin)
    body = {"teacher_id": _teacher_id(admin), "class_id": g1["id"], "subject_id": g1["subject_ids"][0], **over}
    assert admin.post("/api/assignments", json=body).status_code == code


def test_assignment_rejects_student_account_and_wrong_section(admin, student):
    g1, g2 = _cls(admin), _cls(admin, "Grade 2")
    users = admin.get("/api/users").json()
    stu_user = first(users, username="ahmed")["id"]
    body = {"teacher_id": stu_user, "class_id": g1["id"], "subject_id": g1["subject_ids"][0]}
    assert admin.post("/api/assignments", json=body).status_code == 400
    body = {
        "teacher_id": _teacher_id(admin),
        "class_id": g1["id"],
        "section_id": g2["sections"][0]["id"],
        "subject_id": g1["subject_ids"][0],
    }
    assert admin.post("/api/assignments", json=body).status_code == 400


# ------------------------------------------------------------------ periods
def test_period_validation(admin):
    assert (
        admin.post("/api/periods", json={"name": "Late", "start_time": "14:00", "end_time": "13:00"}).status_code == 422
    )
    assert (
        admin.post("/api/periods", json={"name": "Bad", "start_time": "25:00", "end_time": "26:00"}).status_code == 422
    )
    # overlaps the demo 1st period (08:00-08:45)
    r = admin.post("/api/periods", json={"name": "Overlap", "start_time": "08:30", "end_time": "09:00"})
    assert r.status_code == 400 and "overlap" in r.text.lower()
    r = admin.post("/api/periods", json={"name": "Extra", "start_time": "13:00", "end_time": "13:40", "order": 8})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert (
        admin.put(
            f"/api/periods/{pid}", json={"name": "Extra class", "start_time": "13:05", "end_time": "13:45"}
        ).status_code
        == 200
    )
    assert first(admin.get("/api/periods").json(), id=pid)["name"] == "Extra class"
    # a period that has classes cannot become a break; deleting it removes its classes
    p = _teaching_period(admin)
    r = admin.put(f"/api/periods/{p['id']}", json={**p, "is_break": True})
    assert r.status_code == 400
    r = admin.delete(f"/api/periods/{p['id']}")
    assert r.status_code == 200 and r.json()["slots_removed"] > 0


# ------------------------------------------------------------------ routine slots
def test_slot_defaults_to_assigned_teacher_and_upserts(admin):
    g1, tid = _cls(admin), _teacher_id(admin)
    sec, per = g1["sections"][0]["id"], _teaching_period(admin)["id"]
    bangla = _subj(admin, "Bangla")["id"]
    r = _slot(admin, g1["id"], sec, "Sat", per, bangla, room="Room 9")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["teacher_id"] == tid and s["room"] == "Room 9" and s["warning"] is None
    # same cell again -> update, never a duplicate
    math = (
        _subj(admin, "Mathematics")["id"]
        if any(x["name"] == "Mathematics" for x in admin.get("/api/subjects").json())
        else g1["subject_ids"][1]
    )
    r = _slot(admin, g1["id"], sec, "Sat", per, math)
    assert r.status_code == 200 and r.json()["id"] == s["id"]
    slots = [
        x
        for x in admin.get(f"/api/routine?section_id={sec}").json()["slots"]
        if x["day"] == "Sat" and x["period_id"] == per
    ]
    assert len(slots) == 1
    assert admin.delete(f"/api/routine/slot/{s['id']}").status_code == 200
    assert admin.delete(f"/api/routine/slot/{s['id']}").status_code == 404


def test_slot_validations(admin):
    g1, g2 = _cls(admin), _cls(admin, "Grade 2")
    tid = _teacher_id(admin)
    sec1, sec2 = g1["sections"][0]["id"], g2["sections"][0]["id"]
    per, brk = _teaching_period(admin)["id"], _break_period(admin)["id"]
    sub = g1["subject_ids"][0]
    # section of another class
    r = _slot(admin, g1["id"], sec2, "Sat", per, sub)
    assert r.status_code == 400 and "does not belong" in r.text
    # Friday is not a working day by default
    r = _slot(admin, g1["id"], sec1, "Fri", per, sub)
    assert r.status_code == 400 and "not a working day" in r.text
    assert _slot(admin, g1["id"], sec1, "Xyz", per, sub).status_code == 422
    # breaks cannot hold classes
    r = _slot(admin, g1["id"], sec1, "Sat", brk, sub)
    assert r.status_code == 400 and "break" in r.text
    # a teacher who is not assigned to the subject is blocked clearly
    karim = _teacher_id(admin, "demo.karim")
    r = _slot(admin, g1["id"], sec1, "Sat", per, sub, teacher=karim)
    assert r.status_code == 400 and "not assigned" in r.text and "Abdul Karim" in r.text
    # double booking: teacher teaches Grade 1 on Sat/period; Grade 2 at the same time is refused
    assert _slot(admin, g1["id"], sec1, "Sat", per, sub, teacher=tid).status_code == 200
    g2sub = g2["subject_ids"][0]
    assert (
        admin.post("/api/assignments", json={"teacher_id": tid, "class_id": g2["id"], "subject_id": g2sub}).status_code
        == 201
    )
    r = _slot(admin, g2["id"], sec2, "Sat", per, g2sub, teacher=tid)
    assert r.status_code == 400 and "already teaches Grade 1" in r.text
    # a different period is fine
    other = [p["id"] for p in admin.get("/api/periods").json() if not p["is_break"] and p["id"] != per][0]
    assert _slot(admin, g2["id"], sec2, "Sat", other, g2sub, teacher=tid).status_code == 200


def test_slot_warning_when_assignment_changes(admin):
    g1 = _cls(admin)
    sec, per, sub = g1["sections"][0]["id"], _teaching_period(admin)["id"], g1["subject_ids"][0]
    assert _slot(admin, g1["id"], sec, "Sun", per, sub).status_code == 200
    karim = _teacher_id(admin, "demo.karim")
    admin.post("/api/assignments", json={"teacher_id": karim, "class_id": g1["id"], "subject_id": sub})
    slot = next(
        s
        for s in admin.get(f"/api/routine?section_id={sec}").json()["slots"]
        if s["day"] == "Sun" and s["period_id"] == per
    )
    assert slot["warning"] and "no longer assigned" in slot["warning"]


# ------------------------------------------------------------------ views per role
def test_teacher_my_routine_and_today(admin, teacher):
    g1, tid = _cls(admin), _teacher_id(admin)
    sec, per = g1["sections"][0]["id"], _teaching_period(admin)["id"]
    today = admin.get("/api/dashboard").json()["today_day"]
    day = today if today in admin.get("/api/settings").json()["working_days"] else "Sat"
    assert _slot(admin, g1["id"], sec, day, per, g1["subject_ids"][0]).status_code == 200
    mine = teacher.get("/api/my/routine").json()
    assert mine["teacher_id"] == tid and any(s["day"] == day and s["period_id"] == per for s in mine["slots"])
    # a teacher cannot look at somebody else's routine (the id is ignored)
    assert teacher.get(f"/api/my/routine?teacher_id={_teacher_id(admin, 'demo.karim')}").json()["teacher_id"] == tid
    assert admin.get(f"/api/my/routine?teacher_id={tid}").json()["teacher_id"] == tid
    if day == today:
        assert mine["today_classes"] and teacher.get("/api/dashboard").json()["my_classes_today"]
    # teachers read class routines but cannot change them
    assert teacher.get(f"/api/routine?section_id={sec}").status_code == 200
    assert _slot(teacher, g1["id"], sec, "Mon", per, g1["subject_ids"][0]).status_code == 403


def test_student_sees_only_own_class_routine(admin, student):
    g1, g5 = _cls(admin), _cls(admin, "Grade 5")
    own = student.get("/api/routine").json()
    assert own["class_name"] == "Grade 1" and own["slots"] and "default_teachers" not in own
    # asking for another class still returns the student's own section
    other = student.get(f"/api/routine?class_id={g5['id']}&section_id={g5['sections'][0]['id']}").json()
    assert other["section_id"] == g1["sections"][0]["id"]
    assert student.get("/api/my/routine").status_code == 403
    assert student.get("/api/assignments").status_code == 403
    page = student.get(f"/print/routine?section_id={g5['sections'][0]['id']}")
    assert page.status_code == 200 and "Grade 1" in page.text and "Grade 5" not in page.text


# ------------------------------------------------------------------ printing
def test_print_routine_pages(admin, teacher):
    g1, tid = _cls(admin), _teacher_id(admin)
    sec = g1["sections"][0]["id"]
    r = admin.get(f"/print/routine?section_id={sec}")
    assert r.status_code == 200 and "Class routine" in r.text and "landscape" in r.text and "Tiffin break" in r.text
    assert admin.get("/print/routine?section_id=99999").status_code == 404
    assert admin.get(f"/print/routine/teacher/{tid}").status_code == 200
    assert teacher.get(f"/print/routine/teacher/{tid}").status_code == 200
    other = _teacher_id(admin, "demo.karim")
    assert teacher.get(f"/print/routine/teacher/{other}").status_code == 403
    assert teacher.get(f"/print/routine?section_id={sec}").status_code == 200


def test_print_dues_is_admin_only(admin, teacher):
    r = admin.get("/print/dues")
    assert r.status_code == 200 and "Fee due list" in r.text
    assert teacher.get("/print/dues").status_code == 403


# ------------------------------------------------------------------ marks restriction
def test_teacher_marks_limited_to_assigned_subjects(admin, teacher):
    g1, g5 = _cls(admin), _cls(admin, "Grade 5")
    exam = admin.get("/api/exams").json()[0]["id"]
    sheet = teacher.get(f"/api/marks?exam_id={exam}&class_id={g1['id']}").json()
    assert set(sheet["editable_subject_ids"]) == set(g1["subject_ids"])
    # Grade 5: nothing assigned to this teacher -> 1.3.0: the class is not theirs (403), saving is refused too
    assert teacher.get(f"/api/marks?exam_id={exam}&class_id={g5['id']}").status_code == 403
    sheet5 = admin.get(f"/api/marks?exam_id={exam}&class_id={g5['id']}").json()
    st = sheet5["students"][0]
    sub = st["subject_ids"][0]
    r = teacher.post(
        "/api/marks/bulk", json={"exam_id": exam, "entries": [{"student_id": st["id"], "subject_id": sub, "marks": 50}]}
    )
    assert r.status_code == 403 and "not assigned to teach" in r.text
    r = teacher.post(f"/api/students/{st['id']}/marks", json={"exam_id": exam, "subject_id": sub, "marks": 50})
    assert r.status_code == 403
    # admin is never restricted
    full = admin.get(f"/api/marks?exam_id={exam}&class_id={g5['id']}").json()
    assert set(full["editable_subject_ids"]) == {s["id"] for s in full["subjects"]}
    r = admin.post(
        "/api/marks/bulk", json={"exam_id": exam, "entries": [{"student_id": st["id"], "subject_id": sub, "marks": 50}]}
    )
    assert r.status_code == 200
    # once assigned, the teacher may enter marks
    admin.post("/api/assignments", json={"teacher_id": _teacher_id(admin), "class_id": g5["id"], "subject_id": sub})
    r = teacher.post(
        "/api/marks/bulk", json={"exam_id": exam, "entries": [{"student_id": st["id"], "subject_id": sub, "marks": 61}]}
    )
    assert r.status_code == 200
    # an assignment to another section does not count
    g1sub = g1["subject_ids"][0]
    admin.post(
        "/api/assignments",
        json={"teacher_id": _teacher_id(admin, "demo.karim"), "class_id": g1["id"], "subject_id": g1sub},
    )
    st1 = sheet["students"][0]
    r = teacher.post(
        "/api/marks/bulk",
        json={"exam_id": exam, "entries": [{"student_id": st1["id"], "subject_id": g1sub, "marks": 40}]},
    )
    assert r.status_code == 403


# ------------------------------------------------------------------ CSRF and removed SMS
NEW_MUTATIONS = [
    ("POST", "/api/assignments", {"teacher_id": 1, "class_id": 1, "subject_id": 1}),
    ("DELETE", "/api/assignments/1", None),
    ("POST", "/api/periods", {"name": "P", "start_time": "07:00", "end_time": "07:30"}),
    ("PUT", "/api/periods/1", {"name": "P", "start_time": "07:00", "end_time": "07:30"}),
    ("DELETE", "/api/periods/1", None),
    ("PUT", "/api/routine/slot", {"class_id": 1, "section_id": 1, "day": "Sat", "period_id": 1, "subject_id": 1}),
    ("DELETE", "/api/routine/slot/1", None),
]


@pytest.mark.parametrize("method,path,body", NEW_MUTATIONS)
def test_new_routes_need_csrf(admin, method, path, body):
    token = admin.headers.pop("X-CSRF-Token")
    try:
        r = admin.request(method, path, json=body)
        assert r.status_code == 403 and "CSRF" in r.text, (method, path, r.text)
    finally:
        admin.headers["X-CSRF-Token"] = token


@pytest.mark.parametrize("method,path,body", NEW_MUTATIONS)
def test_new_routes_need_login(anon, method, path, body):
    assert anon.request(method, path, json=body).status_code in (401, 403)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/sms"),
        ("POST", "/api/sms/test"),
        ("POST", "/api/attendance/sms-absent"),
        ("POST", "/api/fees/reminders"),
    ],
)
def test_sms_routes_are_gone(admin, method, path):
    assert admin.request(method, path, json={}).status_code in (404, 405)


def test_no_sms_left_in_ui(admin, teacher):
    # 1.2.0 removed SMS sending. 1.0.5 adds only SMS gateway *settings* (Settings > SMS & integrations, admin only).
    html = teacher.get("/dashboard").text + admin.get("/static/js/app.js").text
    assert "SMS" not in html and "sms" not in html.lower().replace("sms-", "")
    admin_html = admin.get("/dashboard").text
    settings = admin_html[admin_html.index("page === 'settings'") :]
    assert "SMS" not in admin_html.replace(settings, "")


# ------------------------------------------------------------------ upgrade from 1.1.x
def test_upgrade_from_v111_database(tmp_path, monkeypatch):
    from sqlalchemy import inspect
    from sqlalchemy.orm import sessionmaker

    from app.database import make_engine, migrate
    from app.models import Period, SchoolSettings
    from app.seed import seed

    path = tmp_path / "v111.db"
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE school_settings (id INTEGER PRIMARY KEY, name VARCHAR, tagline VARCHAR, address VARCHAR);
        CREATE TABLE classes (id INTEGER PRIMARY KEY, name VARCHAR, "order" INTEGER);
        CREATE TABLE sms_logs (id INTEGER PRIMARY KEY, to_number VARCHAR, message VARCHAR, date DATETIME,
            type VARCHAR, status VARCHAR);
        INSERT INTO school_settings VALUES (1, 'Old School', NULL, 'Dhaka');
        INSERT INTO classes VALUES (1, 'Grade 1', 1);
        INSERT INTO sms_logs VALUES (1, '01700000000', 'hi', '2026-01-01', 'test', 'mock');
        """
    )
    con.commit()
    con.close()
    eng = make_engine(path)
    added = migrate(eng)
    tables = set(inspect(eng).get_table_names())
    assert "sms_logs" not in tables and {"periods", "teacher_subjects", "routine_slots"} <= tables
    assert "school_settings.working_days" in added
    db = sessionmaker(bind=eng)()
    seed(db, demo=False, default_periods=True)
    assert db.query(Period).count() == 7
    assert db.get(SchoolSettings, 1).name == "Old School"
    assert db.get(SchoolSettings, 1).working_days in (None, "Sat,Sun,Mon,Tue,Wed,Thu")
    # running the upgrade again changes nothing and does not duplicate periods
    assert migrate(eng) == []
    seed(db, demo=False, default_periods=True)
    assert db.query(Period).count() == 7
    db.close()


def test_routine_page_and_tabs_render(admin, teacher, student):
    home = admin.get("/dashboard").text
    for marker in (
        'data-nav="routine"',
        'data-rt-tab="assign"',
        'data-rt-tab="periods"',
        "data-routine-grid",
        "data-working-days",
    ):
        assert marker in home, marker
    t = teacher.get("/dashboard").text
    assert 'data-nav="routine"' in t and 'data-rt-tab="assign"' not in t and "data-working-days" not in t
    with TestClient(app):
        p = student.get(f"/student/{student.student_pk}").text
        assert "data-routine-grid" in p
