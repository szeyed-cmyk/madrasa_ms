"""1.0.5: landing page, one-click demo logins, admin settings (SMTP, payment gateways, SMS, branding,
currencies, languages + translations), encrypted secrets, RTL and the new dashboard data (Vibe96 SUB-2026-1065)."""

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import csrf_from
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config as config_module
from app import demo, i18n, secret_store
from app import main as main_module
from app.api import integrations as integrations_api
from app.api import school_settings as school_settings_api
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import AppSetting

PROJECT = Path(__file__).resolve().parent.parent
RCPT = "tester" + "@" + "example.org"  # built at runtime: no email-like text in the package


@pytest.fixture()
def demo_on(monkeypatch, fresh_db):
    """Run the app as the public demo (DEMO_MODE=true) for one test."""
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


# ------------------------------------------------------------------ landing page
def test_landing_page_is_public_with_live_demo_button(anon):
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 200
    html = r.text
    assert "data-live-demo" in html and 'href="/login"' in html
    for section in ('id="features"', 'id="screens"', 'id="roles"', 'id="benefits"', 'id="tech"'):
        assert section in html, section
    assert "Developer: Syed Abue Tayeb Al-Zeyed" in html
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", html)
    assert "mailto:" not in html and "tel:" not in html


def test_landing_images_exist():
    for name in ("dashboard", "students", "results", "fees", "settings", "mobile"):
        path = PROJECT / "static" / "img" / "landing" / f"{name}.webp"
        assert path.is_file() and path.stat().st_size > 5_000, name


def test_landing_can_be_switched_off(admin, anon):
    assert admin.post("/api/settings", json={"landing_enabled": False}).status_code == 200
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    assert admin.post("/api/settings", json={"landing_enabled": True}).status_code == 200
    assert anon.get("/", follow_redirects=False).status_code == 200


def test_fresh_install_root_opens_setup(blank):
    r = blank.get("/", follow_redirects=False)
    assert r.status_code == 200 and "data-landing" in r.text
    s = blank.get("/setup", follow_redirects=False)
    assert s.status_code == 200
    login = blank.get("/login", follow_redirects=False)
    assert login.status_code == 303 and login.headers["location"] == "/setup"


# ------------------------------------------------------------------ demo logins
def test_no_demo_buttons_outside_demo_mode(anon):
    html = anon.get("/login").text
    assert "data-demo-role" not in html


def test_demo_buttons_for_every_role(demo_on):
    anon = TestClient(app)  # no `with`: the demo start-up reset must not run on the test database
    html = anon.get("/login").text
    for role in ("admin", "teacher", "student"):
        assert f'data-demo-role="{role}"' in html, role
    # no automatic login any more: a visitor sees the landing page and the login page first
    assert anon.get("/dashboard", follow_redirects=False).headers["location"] == "/login"
    assert anon.get("/", follow_redirects=False).status_code == 200
    a = _demo_client("admin")
    assert a.get("/api/users").status_code == 200
    t = _demo_client("teacher")
    assert t.get("/api/users").status_code == 403
    s = _demo_client("student")
    r = s.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/student/")


def test_demo_mode_env_name(tmp_path):
    code = "from app.config import settings; print(settings.demo_auto_login)"
    env = {**os.environ, "DEMO_MODE": "true", "DEMO_AUTO_LOGIN": "", "DATABASE_PATH": str(tmp_path / "x.db")}
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "True", out.stderr
    env["DEMO_MODE"] = ""
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


# ------------------------------------------------------------------ secrets
def test_secret_store_roundtrip_and_mask():
    token = secret_store.encrypt("s3cret-value")
    assert token.startswith("enc:v1:") and "s3cret-value" not in token
    assert secret_store.decrypt(token) == "s3cret-value"
    assert secret_store.decrypt(token, secret_key="another-key-0123456789") is None
    assert secret_store.decrypt("plain") is None and secret_store.decrypt(None) is None
    assert secret_store.mask(True) and "s3cret" not in secret_store.mask(True) and secret_store.mask(False) == ""


def test_smtp_settings_are_saved_and_password_is_encrypted(admin):
    body = {
        "enabled": True,
        "host": "smtp.example.org",
        "port": 465,
        "security": "ssl",
        "username": "mailer",
        "password": "Mail#Pass-2026",
        "from_email": RCPT,
        "from_name": "Madrasa Pro",
    }
    r = admin.put("/api/config/smtp", json=body)
    assert r.status_code == 200 and "password" in r.json()["saved"], r.text
    got = admin.get("/api/config/smtp").json()
    assert got["host"] == "smtp.example.org" and got["port"] == 465 and got["security"] == "ssl"
    assert got["password"] == "" and got["password_set"] is True and "Mail#Pass" not in json.dumps(got)
    with SessionLocal() as db:
        row = db.get(AppSetting, "smtp.password")
        assert row.is_secret and row.value.startswith("enc:v1:") and "Mail#Pass" not in row.value
    # empty password keeps the stored one; _clear removes it
    assert admin.put("/api/config/smtp", json={"password": "", "host": "mail.example.org"}).status_code == 200
    assert admin.get("/api/config/smtp").json()["password_set"] is True
    assert admin.put("/api/config/smtp", json={"password_clear": True}).status_code == 200
    assert admin.get("/api/config/smtp").json()["password_set"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"port": 0},
        {"security": "tls13"},
        {"host": "bad host!"},
        {"from_email": "nobody"},
        {"unknown": 1},
        {"enabled": "yes"},
    ],
)
def test_smtp_validation(admin, body):
    assert admin.put("/api/config/smtp", json=body).status_code == 400


def test_smtp_test_email(admin, monkeypatch):
    assert admin.post("/api/config/smtp/test", json={"to": RCPT}).status_code == 400  # nothing saved yet
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **kw):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent.append(("starttls",))

        def login(self, user, pw):
            sent.append(("login", user, pw))

        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr("app.integrations.smtplib.SMTP", FakeSMTP)
    admin.put(
        "/api/config/smtp",
        json={
            "host": "smtp.example.org",
            "port": 587,
            "security": "starttls",
            "username": "mailer",
            "password": "pw-123",
            "from_email": RCPT,
        },
    )
    r = admin.post("/api/config/smtp/test", json={"to": RCPT})
    assert r.status_code == 200, r.text
    assert ("starttls",) in sent and ("login", "mailer", "pw-123") in sent and sent[-1][0] == "send"
    assert admin.post("/api/config/smtp/test", json={"to": "not-an-address"}).status_code == 400


def test_payment_gateways_masked_and_used_as_payment_methods(admin):
    body = {
        "stripe_enabled": True,
        "stripe_mode": "live",
        "stripe_publishable_key": "pk_live_abc",
        "stripe_secret_key": "sk_live_SECRET",
        "bkash_enabled": True,
        "bkash_app_secret": "BK-SECRET",
    }
    assert admin.put("/api/config/payments", json=body).status_code == 200
    got = admin.get("/api/config/payments").json()
    assert got["stripe_enabled"] and got["stripe_mode"] == "live" and got["stripe_publishable_key"] == "pk_live_abc"
    assert got["stripe_secret_key"] == "" and got["stripe_secret_key_set"] and got["stripe_secret_key_mask"]
    assert "SECRET" not in json.dumps(got)
    methods = admin.get("/api/settings").json()["payment_methods"]
    assert "Stripe" in methods and "bKash" in methods
    assert admin.put("/api/config/payments", json={"stripe_mode": "sandbox"}).status_code == 400


def test_sms_settings(admin):
    r = admin.put(
        "/api/config/sms",
        json={
            "enabled": True,
            "provider": "custom",
            "api_url": "https://sms.example.org/send",
            "api_key": "KEY-1",
            "sender_id": "MADRASA",
        },
    )
    assert r.status_code == 200
    got = admin.get("/api/config/sms").json()
    assert got["api_key"] == "" and got["api_key_set"] and got["sender_id"] == "MADRASA"
    assert admin.put("/api/config/sms", json={"api_url": "http://plain.example.org"}).status_code == 400


def test_config_is_admin_only(teacher, anon):
    for section in ("smtp", "payments", "sms"):
        assert teacher.get(f"/api/config/{section}").status_code == 403
        assert teacher.put(f"/api/config/{section}", json={}).status_code == 403
        assert anon.get(f"/api/config/{section}").status_code == 401
    assert teacher.post("/api/config/smtp/test", json={"to": RCPT}).status_code == 403
    assert teacher.post("/api/currencies", json={"code": "EUR", "name": "Euro", "symbol": "E"}).status_code == 403
    assert teacher.post("/api/languages", json={"code": "ur", "name": "Urdu"}).status_code == 403


def test_unknown_config_section(admin):
    assert admin.get("/api/config/nothing").status_code in (400, 404)


def test_demo_mode_never_stores_secrets_and_sends_no_email(demo_on):
    a = _demo_client("admin")
    r = a.put("/api/config/smtp", json={"host": "smtp.example.org", "password": "real-secret"})
    assert r.status_code == 200 and r.json()["skipped_secrets"] == ["password"]
    got = a.get("/api/config/smtp").json()
    assert got["host"] == "smtp.example.org" and got["password_set"] is False and got["demo_mode"] is True
    r = a.put("/api/config/payments", json={"stripe_secret_key": "sk_live_x", "paypal_client_secret": "y"})
    assert set(r.json()["skipped_secrets"]) == {"stripe_secret_key", "paypal_client_secret"}
    with SessionLocal() as db:
        assert not db.scalars(select(AppSetting).where(AppSetting.is_secret.is_(True))).all()
    assert a.post("/api/config/smtp/test", json={"to": RCPT}).status_code == 403


# ------------------------------------------------------------------ branding
def test_branding_colours_apply_site_wide(admin, anon):
    r = admin.post("/api/settings", json={"primary_color": "#4F46E5", "secondary_color": "#F59E0B"})
    assert r.status_code == 200, r.text
    s = admin.get("/api/settings").json()
    assert s["primary_color"].upper() == "#4F46E5" and s["secondary_color"].upper() == "#F59E0B"
    for page in (anon.get("/").text, anon.get("/login").text, admin.get("/dashboard").text):
        assert "--brand-500:79 70 229" in page
    for bad in ("red", "#12345", "#GGGGGG", "url(x)"):
        assert admin.post("/api/settings", json={"primary_color": bad}).status_code == 422, bad


# ------------------------------------------------------------------ currencies
def test_currencies_crud_default_and_rebase(admin):
    rows = admin.get("/api/currencies").json()
    codes = {c["code"]: c for c in rows}
    assert {"BDT", "USD"} <= set(codes) and codes["BDT"]["is_default"]
    r = admin.post("/api/currencies", json={"code": "eur", "name": "Euro", "symbol": "€", "rate": 0.0078})
    assert r.status_code == 200 and r.json()["code"] == "EUR"
    eur = r.json()["id"]
    assert admin.post("/api/currencies", json={"code": "EUR", "name": "x", "symbol": "x"}).status_code == 400
    assert admin.post("/api/currencies", json={"code": "EU", "name": "x", "symbol": "x"}).status_code == 422
    assert (
        admin.put(
            f"/api/currencies/{eur}", json={"code": "EUR", "name": "Euro", "symbol": "€", "rate": 0.008}
        ).status_code
        == 200
    )
    # switch default -> school currency symbol follows, other rates re-based
    usd = codes["USD"]["id"]
    assert admin.post(f"/api/currencies/{usd}/default").status_code == 200
    after = {c["code"]: c for c in admin.get("/api/currencies").json()}
    assert after["USD"]["is_default"] and after["USD"]["rate"] == 1.0 and after["BDT"]["rate"] > 1
    assert admin.get("/api/settings").json()["currency"] == after["USD"]["symbol"]
    assert admin.delete(f"/api/currencies/{usd}").status_code == 400  # default cannot be deleted
    assert admin.delete(f"/api/currencies/{eur}").status_code == 200
    page = admin.get("/dashboard").text
    assert "data-currency-switch" in page and "data-currencies=" in page


# ------------------------------------------------------------------ languages, translations, RTL
def _set_lang(client, code, next_url="/dashboard"):
    tok = csrf_from(client.get("/login").text)
    return client.post(
        "/set-language", data={"lang": code, "next": next_url, "csrf_token": tok}, follow_redirects=False
    )


def test_builtin_languages_and_rtl(admin):
    langs = {x["code"]: x for x in admin.get("/api/languages").json()}
    assert set(langs) >= {"en", "bn", "ar"} and langs["ar"]["is_rtl"] and langs["en"]["is_default"]
    r = _set_lang(admin, "ar")
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    html = admin.get("/dashboard").text
    assert 'dir="rtl"' in html and 'lang="ar"' in html and "لوحة التحكم" in html
    _set_lang(admin, "bn")
    html = admin.get("/dashboard").text
    assert 'dir="ltr"' in html and "ড্যাশবোর্ড" in html
    _set_lang(admin, "en")
    assert "Dashboard" in admin.get("/dashboard").text


def test_set_language_rules(anon):
    tok = csrf_from(anon.get("/login").text)
    assert anon.post("/set-language", data={"lang": "ar", "next": "/"}, follow_redirects=False).status_code == 403
    assert anon.post("/set-language", data={"lang": "xx", "csrf_token": tok}, follow_redirects=False).status_code == 400
    for evil in ("//evil.example.org", "https://evil.example.org", "/\\evil"):
        r = anon.post("/set-language", data={"lang": "bn", "next": evil, "csrf_token": tok}, follow_redirects=False)
        assert r.headers["location"] == "/", evil
    html = anon.get("/").text  # the visitor's choice is used on the landing page too
    assert 'lang="bn"' in html


def test_add_language_translate_and_delete(admin):
    r = admin.post("/api/languages", json={"code": "ur", "name": "Urdu", "native_name": "اردو", "is_rtl": True})
    assert r.status_code == 200, r.text
    lid = r.json()["id"]
    assert admin.post("/api/languages", json={"code": "ur", "name": "Urdu"}).status_code == 400
    items = admin.get(f"/api/languages/{lid}/translations").json()["items"]
    assert any(i["key"] == "nav.dashboard" and i["english"] == "Dashboard" for i in items)
    r = admin.put(f"/api/languages/{lid}/translations", json={"items": {"nav.dashboard": "ڈیش بورڈ <b>"}})
    assert r.status_code == 200 and r.json()["changed"] == 1
    assert admin.put(f"/api/languages/{lid}/translations", json={"items": {"no.such.key": "x"}}).status_code == 400
    _set_lang(admin, "ur")
    html = admin.get("/dashboard").text
    assert "ڈیش بورڈ &lt;b&gt;" in html and 'dir="rtl"' in html  # escaped, never raw HTML
    _set_lang(admin, "en")
    en = next(x for x in admin.get("/api/languages").json() if x["code"] == "en")
    assert admin.delete(f"/api/languages/{en['id']}").status_code == 400
    assert admin.post(f"/api/languages/{lid}/default").status_code == 200
    assert admin.delete(f"/api/languages/{lid}").status_code == 400  # default
    assert admin.post(f"/api/languages/{en['id']}/default").status_code == 200
    assert admin.delete(f"/api/languages/{lid}").status_code == 200


def test_locale_files_are_complete():
    en = json.loads((PROJECT / "app/locales/en.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(PROJECT / "tools"))
    import extract_i18n

    assert extract_i18n.extract() == en, "run: python tools/extract_i18n.py"
    assert sorted(extract_i18n.js_keys()) == json.loads((PROJECT / "app/locales/_js_keys.json").read_text("utf-8"))
    for code in ("bn", "ar"):
        cat = {
            k: v
            for k, v in json.loads((PROJECT / f"app/locales/{code}.json").read_text("utf-8")).items()
            if not k.startswith("_")
        }
        assert set(cat) == set(en), code
        assert all(v.strip() for v in cat.values()), code
    i18n.builtin.cache_clear()


# ------------------------------------------------------------------ dashboard + UI
def test_dashboard_chart_data(admin, teacher):
    d = admin.get("/api/dashboard").json()
    assert isinstance(d["attendance_trend"], list) and isinstance(d["class_breakdown"], list)
    assert len(d["fee_trend"]) == 6 and all("month" in m and "total" in m for m in d["fee_trend"])
    assert "fee_trend" not in teacher.get("/api/dashboard").json()


def test_app_shell_has_topbar_settings_tabs_and_no_inline_handlers(admin):
    html = admin.get("/dashboard").text
    for marker in (
        "data-sidebar",
        "data-currency-switch",
        'data-set-tab="branding"',
        'data-set-tab="payments"',
        'data-set-tab="email"',
        'data-set-tab="currencies"',
        'data-set-tab="languages"',
        'data-set-tab="sms"',
    ):
        assert marker in html, marker
    for page in (html, admin.get("/login").text, admin.get("/").text):
        assert not re.search(r"\son(click|change|submit|load|error|input)=", page)
