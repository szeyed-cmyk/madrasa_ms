"""1.0.6: redesigned landing page, demo credential cards with real passwords, and the product tour."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import csrf_from
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config as config_module
from app import demo
from app import main as main_module
from app.api import integrations as integrations_api
from app.api import school_settings as school_settings_api
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import verify_password
from app.seed import NO_PASSWORD


@pytest.fixture()
def demo_on(monkeypatch, fresh_db):
    demo_settings = replace(settings, demo_auto_login=True)
    for mod in (main_module, integrations_api, school_settings_api, config_module):
        monkeypatch.setattr(mod, "settings", demo_settings)
    monkeypatch.setitem(main_module.templates.env.globals, "demo_mode", True)
    with SessionLocal() as db:
        demo.ensure_demo_accounts(db, with_passwords=True)
    yield


def _demo_client(role: str) -> TestClient:
    c = TestClient(app)
    page = c.get("/login")
    r = c.post("/demo/login", data={"role": role, "csrf_token": csrf_from(page.text)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard", r.text
    c.headers["X-CSRF-Token"] = csrf_from(c.get("/dashboard").text)
    return c


PROJECT = Path(__file__).resolve().parent.parent


def test_landing_has_tour_faq_and_how_it_works(anon):
    r = anon.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'href="/tour?autostart=1"' in html
    assert "data-take-tour" in html and "data-live-demo" in html
    for section in (
        'id="features"',
        'id="screens"',
        'id="roles"',
        'id="how"',
        'id="benefits"',
        'id="faq"',
        'id="tech"',
    ):
        assert section in html, section
    assert "Developer: Syed Abue Tayeb Al-Zeyed" in html
    assert "mailto:" not in html and "tel:" not in html
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", html)


def test_login_has_tour_link_and_no_demo_cards_outside_demo(anon):
    html = anon.get("/login").text
    assert "data-take-tour" in html
    assert "data-demo-fill" not in html
    assert "Admin@2026" not in html and "Teacher@2026" not in html and "Student@2026" not in html
    assert "data-demo-role" not in html


def test_demo_cards_show_credentials_and_password_login_works(demo_on):
    c = TestClient(app)  # no `with`: do not re-run demo start-up against the test database
    page = c.get("/login")
    html = page.text
    assert "Demo sign-in" in html or "data-demo-panel" in html
    for role, user, pw in (
        ("admin", demo.DEMO_ADMIN, "Admin@2026"),
        ("teacher", demo.DEMO_TEACHER, "Teacher@2026"),
        ("student", demo.DEMO_STUDENT, "Student@2026"),
    ):
        assert f'data-demo-role="{role}"' in html
        assert f'data-demo-user="{user}"' in html
        assert f'data-demo-password="{pw}"' in html
        assert "data-demo-fill" in html
        assert f'data-demo-oneclick="{role}"' in html
        assert user in html and pw in html
    # the published passwords sign in through the regular form
    r = c.post(
        "/login",
        data={"username": demo.DEMO_ADMIN, "password": "Admin@2026", "csrf_token": csrf_from(html)},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    # a wrong password does not
    c2 = TestClient(app)
    page = c2.get("/login")
    r = c2.post(
        "/login",
        data={"username": demo.DEMO_ADMIN, "password": "Wrong@2026", "csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert r.status_code == 400
    # one-click route still works
    t = _demo_client("teacher")
    assert t.get("/api/users").status_code == 403


def test_demo_passwords_are_hashed_only_in_demo_mode(demo_on):
    with SessionLocal() as db:
        u = db.scalars(select(User).where(User.username == demo.DEMO_ADMIN)).one()
        assert u.password_hash != NO_PASSWORD and "$" in u.password_hash
        assert verify_password("Admin@2026", u.password_hash)
        assert not verify_password("Teacher@2026", u.password_hash)
    # calling the helper without passwords (as a normal install would) stores no published password
    with SessionLocal() as db:
        demo.ensure_demo_accounts(db, with_passwords=False)
        u = db.scalars(select(User).where(User.username == demo.DEMO_ADMIN)).one()
        assert u.password_hash == NO_PASSWORD
    # once the sentinel is back, the published password no longer works
    page = TestClient(app).get("/login")
    r = TestClient(app).post(
        "/login",
        data={"username": demo.DEMO_ADMIN, "password": "Admin@2026", "csrf_token": csrf_from(page.text)},
        follow_redirects=False,
    )
    assert r.status_code != 303


def test_tour_page_and_assets(anon):
    r = anon.get("/tour", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert "data-tour" in html and 'data-autostart="0"' in html
    assert "/static/js/tour.js" in html and "/static/js/tour-data.js" in html
    assert "tour.skip" in html or "Skip" in html
    assert "tour.next" in html or "Next" in html
    r = anon.get("/tour?autostart=1")
    assert r.status_code == 200 and 'data-autostart="1"' in r.text
    shots = PROJECT / "static" / "tour" / "shots"
    for name in ("dashboard", "students", "attendance", "exams", "fees", "routine", "settings", "teacher", "student"):
        path = shots / f"{name}.jpg"
        assert path.is_file() and path.stat().st_size > 10_000, name
    js = (PROJECT / "static" / "js" / "tour.js").read_text(encoding="utf-8")
    assert "cdn" not in js.lower()
    assert "Step " in js and "of " in js


def test_landing_login_tour_have_no_inline_handlers(anon):
    for path in ("/", "/login", "/tour"):
        html = anon.get(path).text
        assert "onclick=" not in html.lower()
        assert "onchange=" not in html.lower()


def test_start_demo_scripts_set_demo_mode():
    bat = (PROJECT / "start-demo.bat").read_text(encoding="utf-8", errors="ignore")
    sh = (PROJECT / "start-demo.sh").read_text(encoding="utf-8")
    assert "DEMO_MODE=true" in bat and "SEED_DEMO_DATA=true" in bat
    assert "DEMO_MODE=true" in sh and "SEED_DEMO_DATA=true" in sh
    css = (PROJECT / "static" / "css" / "login-demo.css").read_text(encoding="utf-8")
    assert "#f1b3ae" in css and "#E8453C" in css and "#fff7f6" in css


def test_fresh_install_shows_landing_not_setup(blank):
    r = blank.get("/", follow_redirects=False)
    assert r.status_code == 200 and "data-landing" in r.text
    assert "data-live-demo" in r.text and "data-take-tour" in r.text
    assert "data-demo-fill" not in r.text
    assert blank.get("/tour", follow_redirects=False).status_code == 200
