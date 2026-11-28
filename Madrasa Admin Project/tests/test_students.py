"""Students are the master database: CRUD, validation, import/export and the profile hub."""

import io

from tests.conftest import first


def _class(admin, name):
    return first(admin.get("/api/classes").json(), name=name)


def _new(admin, **kw):
    g2 = _class(admin, "Grade 2")
    body = {
        "name": "New Student",
        "class_id": g2["id"],
        "section_id": g2["sections"][0]["id"],
        "guardian_phone": "01900000000",
        **kw,
    }
    return admin.post("/api/students", json=body)


def test_list_and_search(admin, teacher):
    rows = admin.get("/api/students").json()
    assert len(rows) == 6
    assert all("subject_count" in r for r in rows)
    assert [r["name"] for r in admin.get("/api/students?q=fatima").json()] == ["Fatima Begum"]
    assert len(admin.get("/api/students?q=000003").json()) == 1
    assert len(teacher.get("/api/students?q=0172222").json()) == 1
    h1 = _class(admin, "Hifz Level 1")
    assert {r["name"] for r in admin.get(f"/api/students?class_id={h1['id']}").json()} == {
        "Omar Farooq",
        "Khadija Islam",
    }


def test_create_student_assigns_class_subjects(admin):
    r = _new(admin, name="Zara Khan")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["student_id"] == "000007"
    assert body["subjects_added"] == 5
    prof = admin.get(f"/api/students/{body['id']}/profile").json()
    assert {s["subject"] for s in prof["subjects"]} == {"Bangla", "English", "Math", "Science", "Islamic Studies"}
    assert prof["admission_no"].startswith("ADM-")


def test_create_without_default_subjects(admin):
    r = _new(admin, apply_class_subjects=False)
    assert r.json()["subjects_added"] == 0


def test_student_validation(admin):
    g1, g2 = _class(admin, "Grade 1"), _class(admin, "Grade 2")
    bad_section = admin.post(
        "/api/students", json={"name": "X", "class_id": g1["id"], "section_id": g2["sections"][0]["id"]}
    )
    assert bad_section.status_code == 400 and "does not belong" in bad_section.json()["detail"]
    assert _new(admin, name="").status_code == 422
    assert _new(admin, guardian_phone="abc").status_code == 422
    assert _new(admin, dob="15/03/2016").status_code == 422
    assert _new(admin, status="Expelled").status_code == 422
    assert _new(admin, student_id="12ab").status_code == 422
    assert admin.post("/api/students", json={"name": "X", "class_id": 9999, "section_id": 1}).status_code == 400
    dup_id = _new(admin, student_id="1")
    assert dup_id.status_code == 400 and "already used" in dup_id.json()["detail"]
    first_adm = admin.get("/api/students").json()[0]["admission_no"]
    dup_adm = _new(admin, admission_no=first_adm)
    assert dup_adm.status_code == 400
    assert (
        admin.post("/api/students", content=b"{not json", headers={"Content-Type": "application/json"}).status_code
        == 422
    )


def test_auto_id_skips_manual_ids(admin):
    assert _new(admin, student_id="000007").status_code == 201
    assert _new(admin).json()["student_id"] == "000008"


def test_update_student_and_class_change_adds_subjects(admin):
    sid = _new(admin, name="Mover").json()["id"]
    h2 = _class(admin, "Hifz Level 2")
    r = admin.put(
        f"/api/students/{sid}",
        json={"name": "Mover Renamed", "class_id": h2["id"], "section_id": h2["sections"][0]["id"], "roll_no": 4},
    )
    assert r.status_code == 200 and r.json()["subjects_added"] == 3  # Quran, Tajweed, Arabic (+Islamic kept)
    s = admin.get(f"/api/students/{sid}").json()
    assert s["name"] == "Mover Renamed" and s["class_name"] == "Hifz Level 2" and s["roll_no"] == 4
    assert (
        admin.put(
            "/api/students/99999", json={"name": "x", "class_id": h2["id"], "section_id": h2["sections"][0]["id"]}
        ).status_code
        == 404
    )


def test_status_change_and_filters(admin):
    s = admin.get("/api/students").json()[0]
    assert admin.post(f"/api/students/{s['id']}/status", json={"status": "Archived"}).json()["status"] == "Archived"
    assert admin.post(f"/api/students/{s['id']}/status", json={"status": "bogus"}).status_code == 422
    assert s["id"] not in [x["id"] for x in admin.get("/api/students?status=current").json()]
    assert [x["id"] for x in admin.get("/api/students?status=Archived").json()] == [s["id"]]
    assert admin.get("/api/dashboard").json()["students"] == 5


def test_delete_student(admin):
    sid = _new(admin).json()["id"]
    assert admin.delete(f"/api/students/{sid}").status_code == 200
    assert admin.get(f"/api/students/{sid}").status_code == 404
    paid = first(admin.get("/api/students").json(), student_id="000001")
    r = admin.delete(f"/api/students/{paid['id']}")
    assert r.status_code == 400 and "Archived" in r.json()["detail"]
    assert admin.delete("/api/students/99999").status_code == 404


def test_profile_is_the_hub(admin):
    s = first(admin.get("/api/students").json(), student_id="000001")
    p = admin.get(f"/api/students/{s['id']}/profile").json()
    for key in ("subjects", "result", "attendance", "fees", "payments", "login", "exams", "class_default_subject_ids"):
        assert key in p
    assert p["result"]["subjects_marked"] == 5 and p["result"]["gpa"] > 0
    assert p["attendance"]["total"] >= 0
    assert p["fees"]["monthly_fee"] == 1500
    assert admin.get("/api/students/99999/profile").status_code == 404


def test_export_csv_is_formula_safe(admin):
    _new(admin, name='=HYPERLINK("http://evil")')
    r = admin.get("/api/students/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in r.text
    assert "Ahmed Rahman" in r.text


def test_import_csv(admin):
    data = (
        b"name,class_name,section_name,guardian_phone,dob\n"
        b"Imported One,Grade 3,A,01811111111,2015-01-01\n"
        b"Imported Two,grade 3,b,,\n"
        b"No Class,Grade 99,A,,\n"
        b"Bad Phone,Grade 3,A,xx,\n"
        b",Grade 3,A,,\n"
    )
    r = admin.post("/api/students/import", files={"file": ("students.csv", io.BytesIO(data), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert len(body["errors"]) == 3
    imported = admin.get("/api/students?q=Imported").json()
    assert len(imported) == 2 and all(x["subject_count"] == 5 for x in imported)


def test_import_rejects_non_csv_and_bad_header(admin):
    r = admin.post("/api/students/import", files={"file": ("s.xlsx", io.BytesIO(b"PK.."), "application/octet-stream")})
    assert r.status_code == 400
    r = admin.post("/api/students/import", files={"file": ("s.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")})
    assert r.status_code == 400


def test_import_sample_file(admin):
    from pathlib import Path

    sample = Path(__file__).resolve().parent.parent / "sample" / "students-import-sample.csv"
    r = admin.post("/api/students/import", files={"file": ("sample.csv", sample.open("rb"), "text/csv")})
    assert r.json() == {"created": 3, "errors": []}


def test_student_pages_render(admin, teacher):
    s = admin.get("/api/students").json()[0]
    for c in (admin, teacher):
        r = c.get(f"/student/{s['id']}")
        assert r.status_code == 200 and s["name"] in r.text
    assert admin.get("/student/99999").status_code == 404
