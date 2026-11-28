"""Exams, subject-wise marks, grades, GPA, positions and result cards."""

import pytest

from app import grading
from tests.conftest import first


def _ctx(c):
    students = c.get("/api/students").json()
    subjects = c.get("/api/subjects").json()
    exam = c.get("/api/exams").json()[0]
    return students, subjects, exam


@pytest.mark.parametrize(
    "marks,letter,gp",
    [
        (80, "A+", 4.0),
        (79.5, "A", 3.75),
        (70, "A-", 3.5),
        (65, "B+", 3.25),
        (60, "B", 3.0),
        (55, "B-", 2.75),
        (50, "C", 2.5),
        (45, "C-", 2.25),
        (40, "D", 2.0),
        (39, "F", 0.0),
        (0, "F", 0.0),
    ],
)
def test_standard_scale(marks, letter, gp):
    assert grading.subject_grade(marks, 100, 33, "standard")[:2] == (letter, gp)


@pytest.mark.parametrize(
    "marks,letter,gp",
    [(80, "A+", 5.0), (70, "A", 4.0), (60, "A-", 3.5), (50, "B", 3.0), (40, "C", 2.0), (33, "D", 1.0), (32, "F", 0.0)],
)
def test_bd5_scale(marks, letter, gp):
    assert grading.subject_grade(marks, 100, 33, "bd5")[:2] == (letter, gp)


def test_pass_marks_and_half_marks():
    assert grading.subject_grade(40, 50, 17, "standard")[:2] == ("A+", 4.0)
    assert grading.subject_grade(45, 100, 50, "standard")[0] == "F"  # below subject pass marks
    assert grading.subject_grade(None, 100, 33, "standard") == ("-", None, None)


def test_summary_rules():
    rows = [
        {"marks": 90, "max": 100, "credits": 3, "grade_point": 4.0, "passed": True},
        {"marks": 60, "max": 100, "credits": 1, "grade_point": 3.0, "passed": True},
    ]
    s = grading.summarize(rows, "standard")
    assert s["gpa"] == 3.75 and s["status"] == "Pass" and s["percentage"] == 75.0 and s["grade"] == "A"
    rows.append({"marks": 10, "max": 100, "credits": 3, "grade_point": 0.0, "passed": False})
    assert grading.summarize(rows, "standard")["status"] == "Fail"
    assert grading.summarize(rows, "bd5")["gpa"] == 0.0
    rows[-1] = {"marks": None, "max": 100, "credits": 3, "grade_point": None, "passed": None}
    assert grading.summarize(rows, "standard")["status"] == "Incomplete"
    assert grading.summarize([], "standard")["status"] == "No marks"


def test_save_mark_validation(teacher):
    students, subjects, exam = _ctx(teacher)
    s = first(students, student_id="000002")
    bangla = first(subjects, name="Bangla")
    quran = first(subjects, name="Quran (Hifz)")
    url = f"/api/students/{s['id']}/marks"
    assert teacher.post(url, json={"exam_id": exam["id"], "subject_id": bangla["id"], "marks": 95}).status_code == 200
    assert teacher.post(url, json={"exam_id": exam["id"], "subject_id": bangla["id"], "marks": 101}).status_code == 400
    assert teacher.post(url, json={"exam_id": exam["id"], "subject_id": bangla["id"], "marks": -1}).status_code == 422
    assert (
        teacher.post(url, json={"exam_id": exam["id"], "subject_id": bangla["id"], "marks": "abc"}).status_code == 422
    )
    r = teacher.post(url, json={"exam_id": exam["id"], "subject_id": quran["id"], "marks": 50})
    assert r.status_code == 400 and "not assigned" in r.json()["detail"]
    assert teacher.post(url, json={"exam_id": 9999, "subject_id": bangla["id"], "marks": 5}).status_code == 404
    assert teacher.post(url, json={"subject_id": bangla["id"], "marks": 5}).status_code == 422
    p = teacher.get(f"/api/students/{s['id']}/profile?exam_id={exam['id']}").json()
    assert first(p["subjects"], subject="Bangla")["marks"] == 95


def test_marks_are_per_exam_and_can_be_cleared(admin):
    students, subjects, exam1 = _ctx(admin)
    exam2 = admin.post("/api/exams", json={"name": "Half Yearly", "exam_date": "2026-06-30"}).json()
    s = first(students, student_id="000001")
    math = first(subjects, name="Math")
    url = f"/api/students/{s['id']}/marks"
    admin.post(url, json={"exam_id": exam2["id"], "subject_id": math["id"], "marks": 41})
    p1 = admin.get(f"/api/students/{s['id']}/profile?exam_id={exam1['id']}").json()
    p2 = admin.get(f"/api/students/{s['id']}/profile?exam_id={exam2['id']}").json()
    assert first(p1["subjects"], subject="Math")["marks"] != 41
    assert first(p2["subjects"], subject="Math")["marks"] == 41
    assert p2["result"]["status"] == "Incomplete"
    admin.post(url, json={"exam_id": exam2["id"], "subject_id": math["id"], "marks": None})
    p2 = admin.get(f"/api/students/{s['id']}/profile?exam_id={exam2['id']}").json()
    assert first(p2["subjects"], subject="Math")["marks"] is None


def test_marks_sheet_and_bulk_save(teacher):
    students, subjects, exam = _ctx(teacher)
    g1 = first(teacher.get("/api/classes").json(), name="Grade 1")
    sheet = teacher.get(f"/api/marks?exam_id={exam['id']}&class_id={g1['id']}").json()
    assert len(sheet["students"]) == 3 and len(sheet["subjects"]) == 5
    st = sheet["students"][0]
    sub = sheet["subjects"][0]
    assert str(sub["id"]) in st["marks"]
    r = teacher.post(
        "/api/marks/bulk",
        json={
            "exam_id": exam["id"],
            "entries": [
                {"student_id": st["id"], "subject_id": sub["id"], "marks": 77},
                {"student_id": sheet["students"][1]["id"], "subject_id": sub["id"], "marks": ""},
            ],
        },
    )
    assert r.status_code == 200 and r.json()["saved"] == 2
    sheet = teacher.get(f"/api/marks?exam_id={exam['id']}&class_id={g1['id']}").json()
    assert sheet["students"][0]["marks"][str(sub["id"])] == 77
    assert str(sub["id"]) not in sheet["students"][1]["marks"]
    bad = teacher.post(
        "/api/marks/bulk",
        json={"exam_id": exam["id"], "entries": [{"student_id": st["id"], "subject_id": sub["id"], "marks": 500}]},
    )
    assert bad.status_code == 400
    assert teacher.get(f"/api/marks?exam_id={exam['id']}&class_id=99999").status_code == 404


def test_results_gpa_position_and_fail(teacher):
    _, _, exam = _ctx(teacher)
    g1 = first(teacher.get("/api/classes").json(), name="Grade 1")
    data = teacher.get(f"/api/results?exam_id={exam['id']}&class_id={g1['id']}").json()
    rows = data["results"]
    assert len(rows) == 3
    maryam = first(rows, student_name="Maryam Akter")
    assert maryam["status"] == "Fail" and maryam["grade"] == "F" and maryam["position"] is None
    passed = sorted((r for r in rows if r["status"] == "Pass"), key=lambda r: r["position"])
    assert [r["position"] for r in passed] == [1, 2]
    assert passed[0]["gpa"] >= passed[1]["gpa"]
    for r in rows:
        assert len(r["subjects"]) == 5 and r["total_max"] == 500
    # 1.3.0: a teacher's "all classes" view covers only the classes they teach (Grade 1 here)
    all_rows = teacher.get("/api/results").json()["results"]
    assert len(all_rows) == 3 and {r["student_pk"] for r in all_rows} == {r["student_pk"] for r in rows}


def test_grading_scale_switch(admin):
    _, _, exam = _ctx(admin)
    assert admin.post("/api/settings", json={"grading_scale": "bd5"}).status_code == 200
    rows = admin.get(f"/api/results?exam_id={exam['id']}").json()["results"]
    assert max(r["gpa"] for r in rows) > 4.0
    assert first(rows, student_name="Maryam Akter")["gpa"] == 0.0
    assert admin.post("/api/settings", json={"grading_scale": "nope"}).status_code == 400


def test_exam_crud_and_publish(admin, student):
    r = admin.post("/api/exams", json={"name": "Final", "exam_date": "2026-12-01"})
    assert r.status_code == 201
    eid = r.json()["id"]
    assert admin.post("/api/exams", json={"name": "final"}).status_code == 400
    assert admin.post("/api/exams", json={"name": "X", "exam_date": "31-12-2026"}).status_code == 422
    assert eid not in [e["id"] for e in student.get("/api/exams").json()]  # drafts hidden from students
    assert student.get(f"/api/my/results?exam_id={eid}").status_code == 404
    assert student.get(f"/print/result/{student.student_pk}?exam_id={eid}").status_code == 404
    assert admin.put(f"/api/exams/{eid}", json={"name": "Final", "is_published": True}).status_code == 200
    assert eid in [e["id"] for e in student.get("/api/exams").json()]
    assert student.get(f"/api/my/results?exam_id={eid}").status_code == 200
    assert admin.delete(f"/api/exams/{eid}").status_code == 200
    seeded = admin.get("/api/exams").json()[0]
    assert admin.delete(f"/api/exams/{seeded['id']}").status_code == 400  # has marks


def test_student_my_results(student, admin):
    r = student.get("/api/my/results").json()
    assert r["exam"]["name"] == "1st Term" and r["subjects_total"] == 5
    assert admin.get("/api/my/results").status_code == 403


def test_result_card_print_pages(admin, teacher, student):
    _, _, exam = _ctx(admin)
    s = first(admin.get("/api/students").json(), student_id="000001")
    r = teacher.get(f"/print/result/{s['id']}?exam_id={exam['id']}")
    assert r.status_code == 200 and "Academic Result Card" in r.text and "Ahmed Rahman" in r.text and "GPA" in r.text
    g1 = first(admin.get("/api/classes").json(), name="Grade 1")
    r = admin.get(f"/print/results?exam_id={exam['id']}&class_id={g1['id']}")
    assert r.status_code == 200 and r.text.count("Academic Result Card") == 3
    assert admin.get("/print/results?exam_id=9999").status_code == 404
    assert student.get(f"/print/result/{student.student_pk}").status_code == 200
    assert student.get(f"/print/results?exam_id={exam['id']}").status_code == 403


def test_profile_defaults_to_latest_exam_with_marks(admin):
    s = first(admin.get("/api/students").json(), student_id="000001")
    admin.post("/api/exams", json={"name": "Empty Exam"})
    p = admin.get(f"/api/students/{s['id']}/profile").json()
    assert p["exam"]["name"] == "1st Term" and p["result"]["subjects_marked"] == 5
    assert len(p["exams"]) == 2
    r = admin.get(f"/print/result/{s['id']}")
    assert "1st Term" in r.text
