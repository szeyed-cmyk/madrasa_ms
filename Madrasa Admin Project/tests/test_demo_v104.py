"""1.0.4: demo-mode safety rules and the demo data set (audit #3278 R8/3.2, #3282 R8/3.1)."""

import sqlite3
from dataclasses import replace

import pytest
from conftest import csrf_from
from sqlalchemy import func, select

from app import demo
from app.config import settings, validate_settings
from app.database import SessionLocal
from app.models import Attendance, Class, Exam, FeePlan, Mark, Payment, Period, RoutineSlot, Student, User
from app.seed import NO_PASSWORD


def _demo_settings(**kw):
    base = replace(
        settings,
        demo_auto_login=True,
        seed_demo_data=True,
        cookie_secure=False,
        bootstrap_admin_username="",
        bootstrap_admin_password="",
    )
    return replace(base, **kw)


def test_normal_install_is_never_blocked():
    validate_settings(replace(settings, demo_auto_login=False, cookie_secure=True, seed_demo_data=False))


def test_demo_mode_with_safe_settings_starts():
    validate_settings(_demo_settings())


@pytest.mark.parametrize(
    "kw, text",
    [
        ({"cookie_secure": True}, "COOKIE_SECURE"),
        ({"seed_demo_data": False}, "SEED_DEMO_DATA"),
        ({"bootstrap_admin_username": "boss"}, "ADMIN_USERNAME"),
        ({"bootstrap_admin_password": "x"}, "ADMIN_USERNAME"),
    ],
)
def test_demo_mode_refuses_production_settings(kw, text):
    with pytest.raises(RuntimeError, match=text):
        validate_settings(_demo_settings(**kw))


def _make_db(path, admins):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, role TEXT)")
    con.executemany("INSERT INTO users (username, role) VALUES (?, 'admin')", [(a,) for a in admins])
    con.commit()
    con.close()


def test_demo_reset_refuses_to_wipe_real_data(tmp_path):
    db = tmp_path / "real.db"
    _make_db(db, ["principal"])
    with pytest.raises(RuntimeError, match="not created by demo mode"):
        demo.reset_database_files(db)
    assert db.is_file(), "real database must not be deleted"


def test_demo_reset_recreates_a_demo_database(tmp_path):
    db = tmp_path / "demo.db"
    _make_db(db, [demo.DEMO_ADMIN])
    demo.reset_database_files(db)
    assert not db.exists() and demo.marker_path(db).is_file()
    _make_db(db, ["visitor-made-admin"])  # marker present: wiped on the next restart anyway
    demo.reset_database_files(db)
    assert not db.exists()


def test_demo_data_has_classes_timetable_attendance_results_and_fees(admin):
    with SessionLocal() as db:
        count = lambda m: db.scalar(select(func.count()).select_from(m))  # noqa: E731
        assert count(Class) >= 20 and count(Period) >= 5 and count(RoutineSlot) >= 30
        assert count(Student) >= 6 and count(Attendance) >= 6 and count(Mark) >= 6
        assert count(Exam) >= 1 and count(FeePlan) >= 20 and count(Payment) >= 3
        demo.ensure_demo_accounts(db)
        for name in (demo.DEMO_ADMIN, demo.DEMO_TEACHER, demo.DEMO_STUDENT):
            u = db.scalars(select(User).where(User.username == name)).one()
            assert u.password_hash == NO_PASSWORD and "$" not in u.password_hash


def test_demo_accounts_cannot_use_the_password_form(anon):
    with SessionLocal() as db:
        demo.ensure_demo_accounts(db)
    page = anon.get("/login")
    for name in (demo.DEMO_ADMIN, demo.DEMO_TEACHER, demo.DEMO_STUDENT):
        for pw in ("", NO_PASSWORD, "demo"):
            r = anon.post(
                "/login",
                data={"username": name, "password": pw, "csrf_token": csrf_from(page.text)},
                follow_redirects=False,
            )
            assert r.status_code != 303


def test_demo_login_route_is_404_outside_demo_mode(anon):
    page = anon.get("/login")
    r = anon.post("/demo/login", data={"role": "admin", "csrf_token": csrf_from(page.text)}, follow_redirects=False)
    assert r.status_code == 404
