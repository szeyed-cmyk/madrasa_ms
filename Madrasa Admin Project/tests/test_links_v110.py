"""Regression tests for problems found by the browser click-through of every page (v1.1.0 packaging review)."""

from conftest import first


def test_print_all_results_with_blank_exam_uses_latest_exam(admin):
    # The "Print all result cards" link is built before an exam is picked: "?exam_id=" must not give a 422.
    r = admin.get("/print/results?exam_id=&class_id=0&section_id=0")
    assert r.status_code == 200
    latest = max(admin.get("/api/exams").json(), key=lambda e: e["id"])
    assert latest["name"] in r.text


def test_print_all_results_without_any_exam_is_404(admin):
    # Exams with marks cannot be deleted from the UI, so clear them straight in the test database.
    from app.database import SessionLocal
    from app.models import Exam, Mark

    with SessionLocal() as db:
        db.query(Mark).delete()
        db.query(Exam).delete()
        db.commit()
    assert admin.get("/print/results?exam_id=").status_code == 404
    assert admin.get("/print/results").status_code == 404


def test_print_results_rejects_non_numeric_exam(admin, teacher):
    assert admin.get("/print/results?exam_id=abc").status_code == 400
    assert admin.get("/print/results?exam_id=0").status_code == 400
    assert teacher.get("/print/results?exam_id=").status_code == 200


def test_result_card_with_blank_exam_id(admin, student):
    sid = first(admin.get("/api/students").json(), student_id="000001")["id"]
    assert admin.get(f"/print/result/{sid}?exam_id=").status_code == 200
    assert student.get(f"/print/result/{student.student_pk}?exam_id=").status_code == 200
    assert admin.get(f"/print/result/{sid}?exam_id=x").status_code == 400


def test_export_csv_link_only_rendered_for_admin(admin, teacher):
    assert "/api/students/export.csv" in admin.get("/dashboard").text
    page = teacher.get("/dashboard").text
    assert "/api/students/export.csv" not in page
    assert teacher.get("/api/students/export.csv").status_code == 403


def test_receipt_print_link_not_rendered_for_non_admin(student):
    html = student.get(f"/student/{student.student_pk}").text
    # The receipt link sits in an x-if template (not x-show), so students never get a link that answers 403.
    assert "x-show=\"role === 'admin'\" :href=\"'/print/receipt/" not in html
    assert "<template x-if=\"role === 'admin'\"><a :href=\"'/print/receipt/'" in html
    assert student.get("/print/receipt/1").status_code == 403


def test_unknown_page_shows_friendly_404_page(anon, admin):
    r = anon.get("/no-such-page")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"]
    assert "<html" in r.text.lower()
    r = admin.get("/no-such-page")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"]
    r = admin.get("/api/no-such-endpoint")
    assert r.status_code == 404 and r.json()["detail"] == "Not Found"
    assert admin.get("/static/no-such-file.css").status_code == 404
