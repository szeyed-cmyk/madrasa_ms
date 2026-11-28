"""Package checks for the Vibe96 archive layout.

Run from the package root with the project's dev requirements installed:
    py -m pip install -r "Madrasa Admin Project/requirements-dev.txt"
    py -m pytest tests
"""

from __future__ import annotations

import inspect
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "Madrasa Admin Project"
VERSION = "1.0.8"
CREDIT = "Developer: Syed Abue Tayeb Al-Zeyed"

# Import the app against a throw-away database (never the buyer's data/madrasa.db).
_TMP = Path(tempfile.mkdtemp(prefix="madrasa-pkg-test-"))
os.environ["DATABASE_PATH"] = str(_TMP / "app.db")
os.environ["SECRET_KEY"] = "package-test-secret-key-0123456789abcdefghij"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""
sys.path.insert(0, str(PROJECT))

from sqlalchemy import create_engine  # noqa: E402

import app.models  # noqa: E402,F401
from app import __version__  # noqa: E402
from app.database import Base, migrate  # noqa: E402

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".html",
    ".js",
    ".css",
    ".sql",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".csv",
    ".bat",
    ".ps1",
    ".sh",
    ".example",
    ".lock",
    ".svg",
    ".json",
    "",
}
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".git", "node_modules", "data"}


def text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith("."):
            yield path


# --------------------------------------------------------------------------- layout
ROOT_FILES = [
    "README.md",
    "HowToSetup.md",
    "CLAUDE.md",
    "CHANGELOG.md",
    "LICENSE-NOTE.md",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    "render.yaml",
    "GITHUB-RENDER.md",
    "database/schema.sql",
    "database/seed.sql",
    "docs/ROUTES.md",
]
PROJECT_FILES = [
    "main.py",
    ".env.example",
    "requirements.txt",
    "requirements.lock",
    "requirements-dev.txt",
    "runtime.txt",
    "start.bat",
    "start.ps1",
    "start.sh",
    "start-demo.bat",
    "start-demo.ps1",
    "start-demo.sh",
    "pytest.ini",
    "ruff.toml",
    "app/__init__.py",
    "app/main.py",
    "app/models.py",
    "app/api/__init__.py",
    "app/api/accounts.py",
    "app/api/exams.py",
    "app/api/fees.py",
    "data/README.txt",
    "tools/gen_schema_sql.py",
    "app/config.py",
    "templates/index.html",
    "templates/login.html",
    "templates/setup.html",
    "static/app.css",
    "static/js/app.js",
    "static/vendor/alpine.min.js",
    "sample/students-import-sample.csv",
    "data/.gitkeep",
    "tests/conftest.py",
    # 1.0.5
    "templates/landing.html",
    "templates/_topbar.html",
    "app/integrations.py",
    "app/secret_store.py",
    "app/i18n.py",
    "app/theme.py",
    "app/api/integrations.py",
    "app/locales/en.json",
    "app/locales/bn.json",
    "app/locales/ar.json",
    "app/locales/_js_keys.json",
    "tools/extract_i18n.py",
    "static/img/landing/dashboard.webp",
    "static/fonts/inter-latin-var.woff2",
    "static/fonts/plus-jakarta-sans-latin-var.woff2",
    "tests/test_v105.py",
    # 1.0.6
    "templates/tour.html",
    "static/js/tour.js",
    "static/js/tour-data.js",
    "static/css/tour.css",
    "static/css/landing.css",
    "static/js/landing.js",
    "static/js/login-demo.js",
    "static/css/login-demo.css",
    "static/tour/shots/dashboard.jpg",
    "tests/test_v106.py",
]


@pytest.mark.parametrize("name", ROOT_FILES)
def test_root_file_exists(name):
    assert (ROOT / name).is_file(), name


@pytest.mark.parametrize("name", PROJECT_FILES)
def test_project_file_exists(name):
    assert (PROJECT / name).is_file(), name


def test_all_application_code_is_inside_the_project_folder():
    for name in ("main.py", "app", "templates", "static", "requirements.txt"):
        assert not (ROOT / name).exists(), f"{name} must live in 'Madrasa Admin Project/', not at the root"
    py_outside = [p for p in ROOT.rglob("*.py") if PROJECT not in p.parents and p.parent != ROOT / "tests"]
    assert not py_outside, py_outside


def test_env_examples_are_identical_and_cover_every_setting():
    root_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert root_env == (PROJECT / ".env.example").read_text(encoding="utf-8")
    config = (PROJECT / "app/config.py").read_text(encoding="utf-8")
    names = set(re.findall(r'(?:environ\.get|_bool|_int)\(\s*"([A-Z_]+)"', config))
    assert names >= {
        "SECRET_KEY",
        "DATABASE_PATH",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "SEED_DEMO_DATA",
        "HOST",
        "PORT",
    }
    for name in names:
        assert re.search(rf"^{name}=", root_env, re.M), f"{name} missing from .env.example"
    # Placeholders must be safe: no real secret is shipped.
    assert re.search(r"^SECRET_KEY=$", root_env, re.M)
    assert re.search(r"^ADMIN_USERNAME=$", root_env, re.M)
    assert re.search(r"^ADMIN_PASSWORD=$", root_env, re.M)


def test_ignore_files_keep_runtime_data_and_secrets_out():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".env", "**/*.db", "**/data/.secret_key", "venv/", "__pycache__/", "node_modules/"):
        assert pattern in gitignore, pattern
    for pattern in ("**/.env", "**/*.db", "**/data/.secret_key", "**/venv/", "**/__pycache__/"):
        assert pattern in dockerignore, pattern
    assert "!**/.env.example" in gitignore and "!**/.env.example" in dockerignore


def test_version_is_consistent():
    assert __version__ == VERSION
    assert f"Version {VERSION}" in (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"^## (\S+)", changelog, re.M)
    assert first and first.group(1) == VERSION
    assert re.search(r"^## 1\.0\.0\b", changelog, re.M), "CHANGELOG must go back to 1.0.0"
    assert VERSION in (ROOT / "database/schema.sql").read_text(encoding="utf-8").splitlines()[0]


# --------------------------------------------------------------------------- credit / contact info
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
CONTACT_WORDS = re.compile(r"mailto:|wa\.me|t\.me/|whatsapp|telegram|\+880|skype:|fiverr|upwork", re.I)
BD_PHONE = re.compile(r"(?<!\d)(?:\+?88)?01[3-9]\d{8}(?!\d)")


def _is_demo_number(num: str) -> bool:
    tail = num[-8:]
    return len(set(tail)) == 1  # 01711111111, 01700000000: obviously made-up demo numbers


def test_no_email_or_contact_details_anywhere():
    problems = []
    for path in text_files():
        if path == Path(__file__).resolve():
            continue  # this file holds the patterns themselves
        # Lines that assert something is absent (e.g. `"mailto:" not in html`) are allowed.
        text = "\n".join(
            line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if " not in " not in line
        )
        rel = path.relative_to(ROOT)
        for m in EMAIL.finditer(text):
            if path.suffix == ".js" and "vendor" in path.parts:
                continue  # minified third-party library
            problems.append(f"{rel}: email-like text {m.group(0)!r}")
        for m in CONTACT_WORDS.finditer(text):
            problems.append(f"{rel}: contact reference {m.group(0)!r}")
        for m in BD_PHONE.finditer(text):
            if not _is_demo_number(m.group(0)):
                problems.append(f"{rel}: phone number {m.group(0)!r}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", ["README.md", "HowToSetup.md", "CLAUDE.md", "LICENSE-NOTE.md"])
def test_developer_credit(name):
    assert CREDIT in (ROOT / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- database
def _schema(conn: sqlite3.Connection) -> dict:
    tables = [
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    ]
    out = {}
    for t in sorted(tables):
        cols = [(r[1], r[2].upper(), r[3], r[5]) for r in conn.execute(f'PRAGMA table_info("{t}")')]
        fks = sorted((r[2], r[3], r[4]) for r in conn.execute(f'PRAGMA foreign_key_list("{t}")'))
        uniques = set()
        for idx in conn.execute(f'PRAGMA index_list("{t}")'):
            if idx[2]:  # unique
                uniques.add(tuple(sorted(r[2] for r in conn.execute(f'PRAGMA index_info("{idx[1]}")'))))
        out[t] = {"columns": cols, "fks": fks, "uniques": sorted(uniques)}
    return out


def _db_from_sql(path: Path, *sql_files: str) -> None:
    conn = sqlite3.connect(path)
    for f in sql_files:
        conn.executescript((ROOT / "database" / f).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def test_schema_sql_creates_exactly_the_models_tables(tmp_path):
    from_sql = tmp_path / "from_sql.db"
    _db_from_sql(from_sql, "schema.sql")
    from_models = tmp_path / "from_models.db"
    Base.metadata.create_all(create_engine(f"sqlite:///{from_models}"))
    a, b = sqlite3.connect(from_sql), sqlite3.connect(from_models)
    try:
        sa, sb = _schema(a), _schema(b)
        assert sorted(sa) == sorted(sb) == sorted(t.name for t in Base.metadata.sorted_tables)
        for table in sb:
            assert sa[table] == sb[table], table
    finally:
        a.close()
        b.close()
    # The app's own migrator finds nothing to add to a schema.sql database.
    assert migrate(create_engine(f"sqlite:///{from_sql}")) == []


def test_seed_sql_loads_and_the_app_accepts_it(tmp_path):
    db = tmp_path / "seeded.db"
    _db_from_sql(db, "schema.sql", "seed.sql")
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
        assert count("students") == 6 and count("classes") == 20 and count("subjects") == 8
        assert count("marks") > 0 and count("attendance") > 0 and count("payments") == 3
        # No usable account ships with the package: the first start shows the setup page.
        # 1.2.0: four sample teachers for the routine, disabled and without a password hash.
        users = conn.execute("SELECT role, is_active, password_hash FROM users").fetchall()
        assert len(users) == 4 and all(r == "teacher" and not a and "$" not in h for r, a, h in users)
        assert count("periods") == 7 and count("teacher_subjects") > 0 and count("routine_slots") > 0
        assert conn.execute("SELECT working_days FROM school_settings").fetchone()[0] == "Sat,Sun,Mon,Tue,Wed,Thu"
        name, tagline = conn.execute("SELECT name, tagline FROM school_settings").fetchone()
        assert name == "Madrasa Admin" and tagline
    finally:
        conn.close()


DEFAULT_CREDENTIAL_TEXT = ("admin123", "teacher123", "admin / admin", "First run:", "demo teacher")


def test_no_default_credentials_in_docs_templates_or_sql():
    problems = []
    for path in text_files():
        rel = path.relative_to(ROOT)
        if "tests" in rel.parts:
            continue  # tests mention the old passwords only to prove they no longer work
        if path.name == "security.py":
            continue  # lists them as blocked, too-common passwords
        if path.name == "CHANGELOG.md":
            continue  # history: says the defaults were removed
        text = path.read_text(encoding="utf-8", errors="ignore")
        for bad in DEFAULT_CREDENTIAL_TEXT:
            if bad in text:
                problems.append(f"{rel}: {bad!r}")
    assert not problems, "\n".join(problems)


def test_first_start_on_seed_sql_database_opens_setup(tmp_path):
    """A database built from schema.sql + seed.sql has no admin: / is the landing page, /setup still works."""
    import subprocess

    db = tmp_path / "from_sql.db"
    _db_from_sql(db, "schema.sql", "seed.sql")
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "with TestClient(app) as c:\n"
        "    r = c.get('/', follow_redirects=False)\n"
        "    assert r.status_code == 200 and 'data-landing' in r.text, r.text[:200]\n"
        "    s = c.get('/setup', follow_redirects=False)\n"
        "    assert s.status_code == 200 and 'Create your administrator account' in s.text\n"
        "print('ok')\n"
    )
    env = {**os.environ, "DATABASE_PATH": str(db), "SEED_DEMO_DATA": "true", "ADMIN_USERNAME": "", "ADMIN_PASSWORD": "", "DEMO_MODE": "false", "DEMO_AUTO_LOGIN": "false", "DEMO_LOGINS": "false"}
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, env=env, capture_output=True, text=True)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr


# --------------------------------------------------------------------------- dependencies
def _pins(text: str) -> dict:
    return {
        m.group(1).lower().replace("_", "-"): m.group(2)
        for m in re.finditer(r"^([A-Za-z0-9_.-]+)==([^\s\\;]+)", text, re.M)
    }


def test_lockfile_is_pinned_hashed_and_matches_requirements():
    req = _pins((PROJECT / "requirements.txt").read_text(encoding="utf-8"))
    lock_text = (PROJECT / "requirements.lock").read_text(encoding="utf-8")
    lock = _pins(lock_text)
    assert req, "requirements.txt has no pins"
    for name, version in req.items():
        assert lock.get(name) == version, f"{name}: requirements.txt {version} != lock {lock.get(name)}"
    entries = re.split(r"\n(?=[A-Za-z0-9])", lock_text.split("\n", 1)[1])
    for entry in entries:
        if re.match(r"[A-Za-z0-9]", entry):
            assert "--hash=sha256:" in entry, entry.splitlines()[0]


# --------------------------------------------------------------------------- docker / start scripts
def test_dockerfile_and_compose_reference_real_paths():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"Madrasa Admin Project/requirements.lock"' in docker and '"Madrasa Admin Project/"' in docker
    assert "--require-hashes" in docker and 'CMD ["python", "main.py"]' in docker and "/healthz" in docker
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile" in compose and "/app/data" in compose and "env_file" in compose
    assert (PROJECT / "main.py").is_file() and (PROJECT / "requirements.lock").is_file()


def test_windows_scripts_use_py_launcher():
    for name in ("start.bat", "start.ps1"):
        text = (PROJECT / name).read_text(encoding="utf-8")
        assert re.search(r"^\s*py -3 -m venv venv", text, re.M), name
        assert not re.search(r"^\s*python(\.exe)?\s", text, re.M), f"{name} must not rely on a 'python' command"
        assert "requirements.lock" in text and "main.py" in text
    assert b"\r\n" in (PROJECT / "start.bat").read_bytes(), "start.bat needs Windows line endings"
    sh = (PROJECT / "start.sh").read_text(encoding="utf-8")
    assert sh.startswith("#!/usr/bin/env bash") and b"\r\n" not in (PROJECT / "start.sh").read_bytes()
    howto = (ROOT / "HowToSetup.md").read_text(encoding="utf-8")
    assert "py main.py" in howto and "py -m pip install" in howto


# --------------------------------------------------------------------------- route guards
def _route_guards(route) -> set[str]:
    from app.security import current_user

    found = set()

    def walk(dep):
        call = dep.call
        if call is current_user:
            found.add("signed-in")
        if call is not None and getattr(call, "__name__", "") == "checker" and call.__closure__:
            for cell in call.__closure__:
                if isinstance(cell.cell_contents, tuple):
                    found.add("+".join(cell.cell_contents))
        for sub in dep.dependencies:
            walk(sub)

    walk(route.dependant)
    return found


def test_every_mutating_api_route_requires_a_staff_role_and_csrf():
    from app.api import router
    from app.security import csrf_protect

    assert any(d.dependency is csrf_protect for d in router.dependencies)
    for route in router.routes:
        if route.methods - {"GET", "HEAD", "OPTIONS"}:
            guards = _route_guards(route)
            assert guards & {"admin", "admin+teacher"}, f"{route.methods} {route.path} has no role guard"
        else:
            assert "signed-in" in _route_guards(route), f"{route.path} is readable without login"


def test_page_forms_check_csrf_and_routes_are_documented():
    from fastapi.routing import APIRoute

    from app.api import router
    from app.main import app as fastapi_app

    doc = (ROOT / "docs/ROUTES.md").read_text(encoding="utf-8")
    routes = [r for r in fastapi_app.routes if isinstance(r, APIRoute)] + list(router.routes)
    for route in routes:
        for method in route.methods - {"HEAD", "OPTIONS"}:
            assert f"| {method} | `{route.path}` |" in doc, f"{method} {route.path} missing from docs/ROUTES.md"
            if method == "POST" and not route.path.startswith("/api"):
                assert "check_csrf" in inspect.getsource(route.endpoint), route.path
