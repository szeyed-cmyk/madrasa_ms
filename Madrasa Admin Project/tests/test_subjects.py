"""Subject management: master list, class defaults, per-student assignment."""

from tests.conftest import first


def _subjects(c):
    return c.get("/api/subjects").json()


def test_seeded_subjects_and_class_defaults(admin):
    subs = _subjects(admin)
    assert {s["name"] for s in subs} >= {"Bangla", "English", "Math", "Science", "Islamic Studies", "Quran (Hifz)"}
    classes = admin.get("/api/classes").json()
    g1 = first(classes, name="Grade 1")
    h1 = first(classes, name="Hifz Level 1")
    names = {s["id"]: s["name"] for s in subs}
    assert {names[i] for i in g1["subject_ids"]} == {"Bangla", "English", "Math", "Science", "Islamic Studies"}
    assert {names[i] for i in h1["subject_ids"]} == {"Quran (Hifz)", "Tajweed", "Arabic", "Islamic Studies"}


def test_create_edit_delete_subject(admin):
    g9 = first(admin.get("/api/classes").json(), name="Grade 9")
    r = admin.post(
        "/api/subjects",
        json={"name": "ICT", "code": "ICT", "max_marks": 50, "pass_marks": 17, "credits": 2, "class_ids": [g9["id"]]},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    s = first(_subjects(admin), id=sid)
    assert s["class_ids"] == [g9["id"]] and s["max_marks"] == 50
    assert admin.post("/api/subjects", json={"name": "ict"}).status_code == 400  # case-insensitive duplicate
    assert admin.post("/api/subjects", json={"name": "X", "max_marks": 50, "pass_marks": 60}).status_code == 422
    assert admin.post("/api/subjects", json={"name": "X", "max_marks": 0}).status_code == 422
    assert admin.post("/api/subjects", json={"name": "X", "class_ids": [99999]}).status_code == 400
    r = admin.put(
        f"/api/subjects/{sid}",
        json={"name": "ICT & Computing", "max_marks": 100, "pass_marks": 33, "credits": 3, "class_ids": []},
    )
    assert r.status_code == 200
    s = first(_subjects(admin), id=sid)
    assert s["name"] == "ICT & Computing" and s["class_ids"] == []
    assert admin.delete(f"/api/subjects/{sid}").status_code == 200
    assert admin.delete(f"/api/subjects/{sid}").status_code == 404


def test_subject_with_marks_cannot_be_deleted_or_shrunk(admin):
    bangla = first(_subjects(admin), name="Bangla")
    r = admin.delete(f"/api/subjects/{bangla['id']}")
    assert r.status_code == 400 and "inactive" in r.json()["detail"]
    r = admin.put(f"/api/subjects/{bangla['id']}", json={"name": "Bangla", "max_marks": 50, "pass_marks": 17})
    assert r.status_code == 400
    r = admin.put(f"/api/subjects/{bangla['id']}", json={"name": "Bangla", "max_marks": 100, "is_active": False})
    assert r.status_code == 200 and not first(_subjects(admin), id=bangla["id"])["is_active"]


def test_class_defaults_set_and_apply(admin):
    g1 = first(admin.get("/api/classes").json(), name="Grade 1")
    arabic = first(_subjects(admin), name="Arabic")
    ids = g1["subject_ids"] + [arabic["id"]]
    assert admin.put(f"/api/classes/{g1['id']}/subjects", json={"subject_ids": ids}).status_code == 200
    assert sorted(admin.get(f"/api/classes/{g1['id']}/subjects").json()["subject_ids"]) == sorted(ids)
    r = admin.post(f"/api/classes/{g1['id']}/subjects/apply").json()
    assert r["students"] == 3 and r["assignments_added"] == 3
    again = admin.post(f"/api/classes/{g1['id']}/subjects/apply").json()
    assert again["assignments_added"] == 0
    assert admin.put(f"/api/classes/{g1['id']}/subjects", json={"subject_ids": [99999]}).status_code == 400
    assert admin.put("/api/classes/99999/subjects", json={"subject_ids": []}).status_code == 404


def test_student_subject_assignment(admin, teacher):
    s = first(admin.get("/api/students").json(), student_id="000002")
    arabic = first(_subjects(admin), name="Arabic")
    r = teacher.post(f"/api/students/{s['id']}/subjects", json={"subject_id": arabic["id"]})
    assert r.status_code == 200 and r.json()["added"] is True
    assert teacher.post(f"/api/students/{s['id']}/subjects", json={"subject_id": arabic["id"]}).json()["added"] is False
    names = {x["name"] for x in teacher.get(f"/api/students/{s['id']}/subjects").json()}
    assert "Arabic" in names and len(names) == 6
    assert teacher.delete(f"/api/students/{s['id']}/subjects/{arabic['id']}").status_code == 200
    assert len(teacher.get(f"/api/students/{s['id']}/subjects").json()) == 5
    assert teacher.post(f"/api/students/{s['id']}/subjects", json={"subject_id": 99999}).status_code == 404
    assert teacher.post("/api/students/99999/subjects", json={"subject_id": arabic["id"]}).status_code == 404


def test_set_student_subjects_and_apply_defaults(admin):
    s = first(admin.get("/api/students").json(), student_id="000002")
    math = first(_subjects(admin), name="Math")
    r = admin.put(f"/api/students/{s['id']}/subjects", json={"subject_ids": [math["id"]]})
    assert r.status_code == 200
    assert [x["name"] for x in admin.get(f"/api/students/{s['id']}/subjects").json()] == ["Math"]
    r = admin.post(f"/api/students/{s['id']}/subjects/apply-class-defaults").json()
    assert r["added"] == 4
    assert admin.put(f"/api/students/{s['id']}/subjects", json={"subject_ids": [99999]}).status_code == 400


def test_removed_subject_hidden_from_results_marks_kept(admin):
    s = first(admin.get("/api/students").json(), student_id="000001")
    math = first(_subjects(admin), name="Math")
    before = admin.get(f"/api/students/{s['id']}/profile").json()["result"]["subjects_total"]
    admin.delete(f"/api/students/{s['id']}/subjects/{math['id']}")
    after = admin.get(f"/api/students/{s['id']}/profile").json()
    assert after["result"]["subjects_total"] == before - 1
    admin.post(f"/api/students/{s['id']}/subjects", json={"subject_id": math["id"]})
    back = admin.get(f"/api/students/{s['id']}/profile").json()
    assert first(back["subjects"], subject="Math")["marks"] is not None
