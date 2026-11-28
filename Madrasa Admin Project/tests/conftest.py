"""Test setup: a throw-away SQLite database with demo data for every test."""

import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="madrasa-test-")
os.environ["DATABASE_PATH"] = str(Path(_TMP) / "test.db")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789abcdef"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""
# Product default is DEMO_LOGINS=true; tests opt in. Keeps /setup and "no demo cards" cases stable.
os.environ["DEMO_LOGINS"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.database import Base, SessionLocal, engine, migrate  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

security.PBKDF2_ITERATIONS = 1_000  # fast hashing in tests only

ADMIN_PW = "Admin#Pass2026"
TEACHER_TEMP_PW = "Teach#Temp2026"  # temporary password the admin gives the teacher (must be changed)
TEACHER_PW = "Teacher#Pass2026"
STUDENT_PW = "Student#Pass2026"
APP_NAME = "Test Madrasa"


def csrf_from(html: str) -> str:
    m = re.search(r'name="csrf-token" content="([^"]+)"', html) or re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "csrf token not found"
    return m.group(1)


def login(client: TestClient, username: str, password: str, new_password: str | None = None):
    page = client.get("/login")
    r = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    if r.headers["location"] == "/change-password":
        assert new_password, "password change required"
        page = client.get("/change-password")
        r = client.post(
            "/change-password",
            data={
                "current_password": password,
                "new_password": new_password,
                "confirm_password": new_password,
                "csrf_token": csrf_from(page.text),
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
    home = client.get("/dashboard")
    client.headers["X-CSRF-Token"] = csrf_from(home.text)
    return client


def run_setup(client: TestClient, username: str = "admin", password: str = ADMIN_PW, app_name: str = APP_NAME):
    """Complete the first-run /setup page like a buyer would (the admin is logged in afterwards)."""
    page = client.get("/setup")
    assert page.status_code == 200, page.text
    r = client.post(
        "/setup",
        data={
            "app_name": app_name,
            "tagline": "Test tagline",
            "username": username,
            "full_name": "Administrator",
            "password": password,
            "confirm_password": password,
            "csrf_token": csrf_from(page.text),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/dashboard", r.text
    return client


def _reset_db(demo: bool = True):
    Base.metadata.drop_all(bind=engine)
    migrate()
    db = SessionLocal()
    seed(db, demo=demo)
    db.close()
    security.login_throttle.reset()


@pytest.fixture()
def no_admin():
    """Fresh database before the first-run setup: demo data, no admin, no usable login (sample teachers disabled)."""
    _reset_db()
    yield


@pytest.fixture()
def fresh_db(no_admin):
    """Fresh database after setup: admin created through /setup, teacher created by the admin."""
    with TestClient(app) as c:
        run_setup(c)
        home = c.get("/dashboard")
        c.headers["X-CSRF-Token"] = csrf_from(home.text)
        r = c.post(
            "/api/users",
            json={"username": "teacher", "full_name": "Class Teacher", "role": "teacher", "password": TEACHER_TEMP_PW},
        )
        assert r.status_code == 201, r.text
        # 1.2.0: teachers may only enter marks for subjects assigned to them -> give "teacher" all of Grade 1
        tid = r.json()["id"]
        g1 = next(c_ for c_ in c.get("/api/classes").json() if c_["name"] == "Grade 1")
        for sid in g1["subject_ids"]:
            a = c.post("/api/assignments", json={"teacher_id": tid, "class_id": g1["id"], "subject_id": sid})
            assert a.status_code == 201, a.text
    security.login_throttle.reset()
    yield


@pytest.fixture()
def blank(no_admin):
    """Anonymous client on a database that still needs the first-run setup."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def anon(fresh_db):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin(fresh_db):
    with TestClient(app) as c:
        yield login(c, "admin", ADMIN_PW)


@pytest.fixture()
def teacher(fresh_db):
    with TestClient(app) as c:
        yield login(c, "teacher", TEACHER_TEMP_PW, TEACHER_PW)


@pytest.fixture()
def student(admin):
    """Student account for demo student 000001 (Ahmed Rahman)."""
    sid = next(s["id"] for s in admin.get("/api/students").json() if s["student_id"] == "000001")
    r = admin.post(f"/api/students/{sid}/create-login", json={"username": "ahmed", "password": "TempPass#123"})
    assert r.status_code == 200, r.text
    with TestClient(app) as c:
        login(c, "ahmed", "TempPass#123", STUDENT_PW)
        c.student_pk = sid
        yield c


def first(items, **match):
    return next(i for i in items if all(i.get(k) == v for k, v in match.items()))
