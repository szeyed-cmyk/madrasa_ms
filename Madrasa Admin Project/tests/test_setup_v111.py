"""First-run setup (v1.1.1): no default credentials, buyer-chosen app name and tagline."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import SchoolSettings, User
from tests.conftest import ADMIN_PW, APP_NAME, csrf_from, login, run_setup

PROJECT = Path(__file__).resolve().parent.parent


def _usable(u: User) -> bool:
    """A login that can actually be used: active with a real password hash (demo teachers have neither)."""
    return bool(u.is_active) and "$" in (u.password_hash or "")


def _users():
    with SessionLocal() as db:
        return [(u.username, u.role, bool(u.must_change_password)) for u in db.query(User).all() if _usable(u)]


def _logins() -> int:
    with SessionLocal() as db:
        return sum(1 for u in db.query(User).all() if _usable(u))


def _setup_form(page_html: str, **over):
    data = {
        "app_name": "Al-Noor Madrasa",
        "tagline": "Learning with excellence",
        "username": "principal",
        "full_name": "Head Teacher",
        "password": "Strong#Pass2026",
        "confirm_password": "Strong#Pass2026",
        "csrf_token": csrf_from(page_html) if page_html else "",
    }
    data.update(over)
    return data


def test_no_accounts_exist_before_setup(blank):
    assert _users() == []
    # 1.2.0 demo teachers exist for the routine, but are disabled and have no password
    with SessionLocal() as db:
        demo = db.query(User).all()
        assert demo and all(u.role == "teacher" and not u.is_active and "$" not in u.password_hash for u in demo)
        assert all(u.username.startswith("demo.") for u in demo)


def test_setup_page_appears_when_no_admin(blank):
    landing = blank.get("/", follow_redirects=False)
    assert landing.status_code == 200 and "data-landing" in landing.text
    for path in ("/login", "/student/1", "/print/students", "/change-password"):
        r = blank.get(path)
        assert r.status_code == 200 and str(r.url).endswith("/setup"), (path, r.url)
    r = blank.get("/setup")
    assert "Create your administrator account. Choose the name shown across the app" in r.text
    assert 'name="app_name"' in r.text and 'name="confirm_password"' in r.text
    for text in ("admin123", "teacher123", "First run:"):
        assert text not in r.text
    assert blank.get("/api/dashboard").status_code == 401
    # A login attempt before setup goes to the setup page as well.
    tok = csrf_from(blank.get("/setup").text)
    r = blank.post(
        "/login", data={"username": "admin", "password": "admin123", "csrf_token": tok}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == "/setup"


def test_setup_creates_admin_and_sets_name(blank):
    r = blank.post("/setup", data=_setup_form(blank.get("/setup").text), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    assert _users() == [("principal", "admin", False)]  # no forced password change, no demo teacher
    with SessionLocal() as db:
        s = db.query(SchoolSettings).first()
        assert (s.name, s.tagline) == ("Al-Noor Madrasa", "Learning with excellence")
    home = blank.get("/dashboard")  # logged in straight away
    assert home.status_code == 200 and "Al-Noor Madrasa" in home.text and 'data-nav="settings"' in home.text
    assert "<title>Al-Noor Madrasa</title>" in home.text
    with TestClient(app) as other:
        login(other, "principal", "Strong#Pass2026")
        assert other.get("/api/dashboard").status_code == 200


def test_setup_is_disabled_after_completion_get_and_post(blank):
    run_setup(blank)
    # 1.0.1/1.0.2: the finished setup page sends visitors home; posting to it is still refused (404).
    r = blank.get("/setup", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    with TestClient(app) as stranger:
        r = stranger.get("/setup", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/dashboard"
        tok = csrf_from(stranger.get("/login").text)
        r = stranger.post("/setup", data={**_setup_form("", username="hacker"), "csrf_token": tok})
        assert r.status_code == 404
        r = stranger.post("/setup", data=_setup_form("", username="hacker", csrf_token="x"))
        assert r.status_code == 404
        assert stranger.post("/setup").status_code == 404  # empty POST: 404, not a form error
        assert stranger.post("/setup", data={"app_name": "x" * 500}).status_code == 404
    assert [u[0] for u in _users()] == ["admin"]
    with SessionLocal() as db:
        assert db.query(SchoolSettings).first().name == APP_NAME


def test_setup_requires_csrf(blank):
    page = blank.get("/setup").text
    form = _setup_form(page)
    del form["csrf_token"]
    assert blank.post("/setup", data=form).status_code == 403
    assert blank.post("/setup", data={**form, "csrf_token": "forged"}).status_code == 403
    with TestClient(app) as other:  # token from another session is rejected too
        assert other.post("/setup", data=_setup_form(page)).status_code == 403
    assert _users() == []


@pytest.mark.parametrize(
    "over,msg",
    [
        ({"confirm_password": "Other#Pass2026"}, "do not match"),
        ({"password": "short", "confirm_password": "short"}, "at least 8"),
        ({"password": "password", "confirm_password": "password"}, "too common"),
        ({"password": "admin123", "confirm_password": "admin123"}, "too common"),
        ({"username": "ab"}, "Username"),
        ({"username": "bad name!"}, "Username"),
        ({"app_name": "   "}, "name"),
        ({"app_name": "N" * 121}, "max. 120"),
        ({"tagline": "T" * 161}, "max. 160"),
        ({"password": "P#" * 70, "confirm_password": "P#" * 70}, "at most 128"),
        ({"username": "Principal2026", "password": "principal2026", "confirm_password": "principal2026"}, "different"),
    ],
)
def test_setup_validation(blank, over, msg):
    r = blank.post("/setup", data=_setup_form(blank.get("/setup").text, **over))
    assert r.status_code == 400 and msg in r.text
    assert _users() == []
    assert blank.get("/setup").status_code == 200  # still open


def test_name_and_tagline_from_settings_show_everywhere(admin, anon):
    r = admin.post("/api/settings", json={"name": "Darul Uloom Academy", "tagline": "Since 1990"})
    assert r.status_code == 200
    assert admin.get("/api/settings").json()["tagline"] == "Since 1990"
    login_page = anon.get("/login").text
    assert "<title>Log in — Darul Uloom Academy</title>" in login_page
    assert "Darul Uloom Academy</p>" in login_page and "Since 1990" in login_page
    home = admin.get("/dashboard").text
    assert home.count("Darul Uloom Academy") >= 3  # tab title, mobile header, sidebar
    sid = admin.get("/api/students").json()[0]["id"]
    assert "Darul Uloom Academy" in admin.get(f"/print/result/{sid}").text
    assert "Darul Uloom Academy" in admin.get(f"/student/{sid}").text
    assert "Darul Uloom Academy" in admin.get("/print/dues").text
    assert (
        "Darul Uloom Academy"
        in admin.get(f"/print/routine?section_id={admin.get('/api/classes').json()[0]['sections'][0]['id']}").text
    )
    # Clearing the tagline hides it.
    assert admin.post("/api/settings", json={"tagline": ""}).status_code == 200
    assert "data-brand-tagline" not in anon.get("/login").text
    assert admin.post("/api/settings", json={"name": ""}).status_code == 422  # the name is required


def test_seed_creates_no_users_and_env_bootstrap(no_admin, monkeypatch):
    from app.config import settings
    from app.seed import bootstrap_admin, seed

    with SessionLocal() as db:
        seed(db, demo=True)
    assert _logins() == 0
    with SessionLocal() as db:
        monkeypatch.setattr(settings, "bootstrap_admin_username", "boss")
        monkeypatch.setattr(settings, "bootstrap_admin_password", "admin123")  # too common: skipped
        assert bootstrap_admin(db) is None and _logins() == 0
        monkeypatch.setattr(settings, "bootstrap_admin_password", "Boot#Strap2026")
        user = bootstrap_admin(db)
        assert user and user.role == "admin" and not user.must_change_password
        assert bootstrap_admin(db) is None  # only once
        assert _logins() == 1
    with TestClient(app) as c:
        assert c.get("/setup", follow_redirects=False).headers["location"] == "/dashboard"
        login(c, "boss", "Boot#Strap2026")
        assert c.get("/api/users").status_code == 200


def test_admin_created_by_setup_is_not_forced_to_change_password(admin):
    r = admin.get("/dashboard", follow_redirects=False)
    assert r.status_code == 200
    me = next(u for u in admin.get("/api/users").json() if u["username"] == "admin")
    assert me["must_change_password"] is False


def test_no_default_credential_text_in_app_files():
    bad = ("admin123", "teacher123", "admin / admin", "First run:")
    for folder in ("templates", "static/js", "app"):
        for path in (PROJECT / folder).rglob("*"):
            if path.is_file() and path.suffix in {".html", ".js", ".py"}:
                text = path.read_text(encoding="utf-8")
                for b in bad:
                    if b in ("admin123", "teacher123") and path.name == "security.py":
                        continue  # listed only as a blocked, too-common password
                    assert b not in text, f"{path.relative_to(PROJECT)} contains {b!r}"
    assert ADMIN_PW not in (PROJECT / "templates/setup.html").read_text(encoding="utf-8")
