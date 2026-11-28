"""1.0.8: Demo sign-in boxes on /login by default (DEMO_LOGINS), no DEMO_MODE required."""

from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import csrf_from
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config as config_module
from app import demo
from app import main as main_module
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import verify_password
from app.seed import NO_PASSWORD


@pytest.fixture()
def logins_on(monkeypatch, no_admin):
    """DEMO_LOGINS=true, DEMO_MODE=false, no real administrator yet."""
    demo_settings = replace(settings, demo_logins=True, demo_auto_login=False)
    monkeypatch.setattr(config_module, "settings", demo_settings)
    monkeypatch.setattr(main_module, "settings", demo_settings)
    with SessionLocal() as db:
        demo.sync_demo_logins(db)
    yield


@pytest.fixture()
def logins_off(monkeypatch, no_admin):
    """DEMO_LOGINS=false after the three accounts were created (they must be disabled)."""
    with SessionLocal() as db:
        demo.ensure_demo_accounts(db, with_passwords=True)
        count_before = db.scalars(select(func.count()).select_from(User)).one()
    demo_settings = replace(settings, demo_logins=False, demo_auto_login=False)
    monkeypatch.setattr(config_module, "settings", demo_settings)
    monkeypatch.setattr(main_module, "settings", demo_settings)
    with SessionLocal() as db:
        demo.sync_demo_logins(db)
    yield count_before


def test_demo_logins_show_boxes_without_demo_mode(logins_on):
    c = TestClient(app)
    r = c.get("/login", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert "data-demo-panel" in html and "data-demo-fill" in html
    for role, user, pw in (
        ("admin", "demo.admin", "Admin@2026"),
        ("teacher", "demo.karim", "Teacher@2026"),
        ("student", "demo.student", "Student@2026"),
    ):
        assert f'data-demo-role="{role}"' in html
        assert f'data-demo-user="{user}"' in html
        assert f'data-demo-password="{pw}"' in html
        assert user in html and pw in html
    assert "/static/js/login-demo.js" in html
    assert "x-on:click" not in html
    assert ":type=" not in html


def test_demo_logins_login_works_for_each_role(logins_on):
    expected = {
        "demo.admin": ("Admin@2026", "/dashboard"),
        "demo.karim": ("Teacher@2026", "/dashboard"),
        "demo.student": ("Student@2026", "/dashboard"),
    }
    for user, (pw, dest) in expected.items():
        c = TestClient(app)
        page = c.get("/login")
        r = c.post(
            "/login",
            data={"username": user, "password": pw, "csrf_token": csrf_from(page.text)},
            follow_redirects=False,
        )
        assert r.status_code == 303 and dest in r.headers["location"], (user, r.status_code, r.headers.get("location"))


def test_login_is_shown_before_setup_when_demo_logins_on(logins_on):
    c = TestClient(app)
    r = c.get("/login", follow_redirects=False)
    assert r.status_code == 200 and "data-demo-panel" in r.text
    # setup is hidden because demo.admin is an active administrator
    setup = c.get("/setup", follow_redirects=False)
    assert setup.status_code in (303, 404) or "Create your administrator account" not in (setup.text or "")


def test_demo_logins_false_hides_boxes_and_disables_accounts(logins_off):
    c = TestClient(app)
    r = c.get("/login", follow_redirects=False)
    # no admin left active -> setup
    assert r.status_code == 303 and r.headers["location"] == "/setup"
    with SessionLocal() as db:
        users = list(db.scalars(select(User).where(User.username.in_(list(demo.DEMO_PASSWORDS)))).all())
        assert users and all(not u.is_active and u.password_hash == NO_PASSWORD for u in users)
        # did not delete accounts or other rows created with them
        assert db.scalars(select(func.count()).select_from(User)).one() >= logins_off
    # published passwords no longer work once the accounts are disabled.


def test_demo_logins_do_not_touch_other_users(fresh_db):
    """A real administrator and teacher created through setup stay as they are."""
    with SessionLocal() as db:
        others = {
            u.username: (u.role, u.is_active, u.password_hash)
            for u in db.scalars(select(User).where(~User.username.in_(list(demo.DEMO_PASSWORDS)))).all()
        }
        assert "admin" in others and "teacher" in others
        demo.ensure_demo_accounts(db, with_passwords=True)
        again = {
            u.username: (u.role, u.is_active, u.password_hash)
            for u in db.scalars(select(User).where(~User.username.in_(list(demo.DEMO_PASSWORDS)))).all()
        }
        assert again == others
        for u in db.scalars(select(User).where(User.username.in_(list(demo.DEMO_PASSWORDS)))).all():
            assert u.is_active and verify_password(demo.DEMO_PASSWORDS[u.username], u.password_hash)


def test_login_demo_js_is_plain_and_fills_password_visibly():
    js = (main_module.BASE_DIR / "static" / "js" / "login-demo.js").read_text(encoding="utf-8")
    assert "window.Alpine" not in js and "Alpine.store" not in js
    assert "getElementById(\"username\")" in js and "getElementById(\"password\")" in js
    assert "HTMLInputElement.prototype" in js
    assert "pw.type = \"text\"" in js or "type = \"text\"" in js
    assert "keydown" in js and "Enter" in js
    assert "requestSubmit" in js
