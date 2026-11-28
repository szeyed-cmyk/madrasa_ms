"""Attendance and fees."""

from datetime import date, timedelta

from tests.conftest import first

TODAY = date.today().isoformat()


def _g1(c):
    return first(c.get("/api/classes").json(), name="Grade 1")


def test_attendance_roundtrip_keeps_saved_status(teacher):
    g1 = _g1(teacher)
    day = teacher.get(f"/api/attendance?date={TODAY}&class_id={g1['id']}").json()
    assert len(day["students"]) == 3 and not day["already_saved"]
    recs = [{"student_id": s["id"], "status": "Present"} for s in day["students"]]
    recs[1]["status"] = "Absent"
    r = teacher.post("/api/attendance", json={"date": TODAY, "records": recs})
    assert r.status_code == 200 and r.json()["saved"] == 3
    day = teacher.get(f"/api/attendance?date={TODAY}&class_id={g1['id']}").json()
    assert day["already_saved"] and day["students"][1]["status"] == "Absent"  # v1.0 reset this to Present
    recs[1]["status"] = "Late"
    teacher.post("/api/attendance", json={"date": TODAY, "records": recs})
    p = teacher.get(f"/api/students/{recs[1]['student_id']}/profile").json()
    assert p["attendance"]["recent"][0] == {"date": TODAY, "status": "Late", "marked_by": "teacher"}
    assert sum(1 for a in p["attendance"]["recent"] if a["date"] == TODAY) == 1  # no duplicates


def test_attendance_validation(teacher):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    sid = teacher.get("/api/students").json()[0]["id"]
    assert (
        teacher.post(
            "/api/attendance", json={"date": tomorrow, "records": [{"student_id": sid, "status": "Present"}]}
        ).status_code
        == 422
    )
    assert (
        teacher.post(
            "/api/attendance", json={"date": TODAY, "records": [{"student_id": sid, "status": "Sick"}]}
        ).status_code
        == 422
    )
    assert teacher.post("/api/attendance", json={"date": "x", "records": []}).status_code == 422
    assert (
        teacher.post(
            "/api/attendance", json={"date": TODAY, "records": [{"student_id": 99999, "status": "Present"}]}
        ).status_code
        == 404
    )
    assert teacher.post("/api/attendance", json=[{"student_id": sid}]).status_code == 422  # v1.0 crashed with 500
    assert teacher.get("/api/attendance?date=2026-13-01").status_code == 400


def test_attendance_report_and_print(teacher):
    g1 = _g1(teacher)
    day = teacher.get(f"/api/attendance?date={TODAY}&class_id={g1['id']}").json()
    recs = [{"student_id": s["id"], "status": "Absent" if i == 0 else "Present"} for i, s in enumerate(day["students"])]
    teacher.post("/api/attendance", json={"date": TODAY, "records": recs})
    # SMS was removed in 1.2.0
    assert teacher.post("/api/attendance/sms-absent", json={"date": TODAY, "class_id": g1["id"]}).status_code in (
        404,
        405,
    )
    rep = teacher.get(f"/api/attendance/report?month={TODAY[:7]}&class_id={g1['id']}").json()
    assert len(rep["rows"]) == 3 and rep["rows"][0]["total"] >= 1
    assert teacher.get("/api/attendance/report?month=2026-13").status_code == 400
    r = teacher.get(f"/print/attendance?date={TODAY}&class_id={g1['id']}")
    assert r.status_code == 200 and "Daily Attendance" in r.text


def test_payment_and_receipts(admin):
    s = first(admin.get("/api/students").json(), student_id="000004")
    r = admin.post(
        "/api/payments",
        json={"student_id": s["id"], "amount": 1500, "method": "bKash", "fee_month": TODAY[:7], "note": "Nov"},
    )
    assert r.status_code == 201
    p1 = r.json()
    r2 = admin.post("/api/payments", json={"student_id": s["id"], "amount": 500}).json()
    assert p1["receipt_no"] != r2["receipt_no"] and p1["receipt_no"].startswith("RCP-")
    rec = admin.get(f"/api/receipt/{p1['id']}").json()
    assert rec["method"] == "bKash" and rec["class_name"] == "Grade 1" and rec["collected_by"] == "admin"
    page = admin.get(f"/print/receipt/{p1['id']}")
    assert page.status_code == 200 and p1["receipt_no"] in page.text and "1,500.00" in page.text
    assert admin.get("/api/receipt/99999").status_code == 404
    assert admin.get("/print/receipt/99999").status_code == 404
    pays = admin.get(f"/api/payments?student_id={s['id']}").json()
    assert len(pays) == 2


def test_payment_validation(admin):
    sid = admin.get("/api/students").json()[0]["id"]
    for body in (
        {"student_id": sid, "amount": 0},
        {"student_id": sid, "amount": -5},
        {"student_id": sid, "amount": 10, "method": "Gold"},
        {"student_id": sid, "amount": 10, "fee_month": "2026-13"},
        {"student_id": sid},
        {"amount": 10},
    ):
        assert admin.post("/api/payments", json=body).status_code == 422, body
    assert admin.post("/api/payments", json={"student_id": 99999, "amount": 10}).status_code == 404


def test_void_payment_and_dues(admin):
    s = first(admin.get("/api/students").json(), student_id="000005")
    before = admin.get(f"/api/students/{s['id']}/profile").json()["fees"]
    months = date.today().month
    assert before["expected"] == 1500 * months and before["due"] == 1500 * months
    pid = admin.post("/api/payments", json={"student_id": s["id"], "amount": 1000}).json()["id"]
    assert admin.get(f"/api/students/{s['id']}/profile").json()["fees"]["due"] == 1500 * months - 1000
    assert admin.post(f"/api/payments/{pid}/void").status_code == 200
    after = admin.get(f"/api/students/{s['id']}/profile").json()["fees"]
    assert after["due"] == 1500 * months
    dues = admin.get("/api/fees/dues").json()
    assert first(dues, id=s["id"])["due"] == 1500 * months
    assert admin.get(f"/print/receipt/{pid}").text.count("VOID") == 1


def test_fee_plans_and_due_list(admin):
    g1 = _g1(admin)
    assert admin.put("/api/fees/plans", json={"class_id": g1["id"], "amount": 2000}).status_code == 200
    assert first(admin.get("/api/fees/plans").json(), class_id=g1["id"])["monthly_fee"] == 2000
    assert admin.put("/api/fees/plans", json={"class_id": g1["id"], "amount": -1}).status_code == 422
    assert admin.put("/api/fees/plans", json={"class_id": 99999, "amount": 1}).status_code == 404
    dues = admin.get(f"/api/fees/dues?class_id={g1['id']}").json()
    assert dues
    # printable due list replaces the old SMS reminders
    page = admin.get(f"/print/dues?class_id={g1['id']}")
    assert page.status_code == 200 and dues[0]["name"] in page.text and "Contacted" in page.text
    assert admin.get("/print/dues").status_code == 200
    assert admin.post("/api/fees/reminders", json={"student_ids": [dues[0]["id"]]}).status_code in (404, 405)


def test_dashboard_admin(admin):
    d = admin.get("/api/dashboard").json()
    assert d["students"] == 6 and d["classes"] == 20 and d["subjects"] == 8
    assert d["collected"] == 4200 and len(d["recent_payments"]) == 3 and d["dues_total"] >= 0
