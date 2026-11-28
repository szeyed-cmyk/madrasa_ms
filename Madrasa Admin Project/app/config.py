"""Application settings, read from environment variables (and an optional .env file).

Every tunable lives in the ``Settings`` object below (1.0.2): database path, secret key, demo
switches, cookie/session settings, password-hash iterations and the login throttle. Other modules
read ``settings.<name>`` instead of keeping their own literals.

1.0.5: the public demo switch is DEMO_MODE=true (DEMO_AUTO_LOGIN=true is still accepted as the old name and means
the same). Demo mode no longer logs visitors in automatically: the landing page's "Live Demo" button opens the login
page, which shows one-click demo login buttons for every role.

Demo safety rules (``validate_settings``, enforced at start-up; tested in tests/test_demo_v104.py).
DEMO_MODE=true is REFUSED (the app will not start) when:
  1. COOKIE_SECURE=true                 - that marks a real HTTPS production install;
  2. SEED_DEMO_DATA is not true         - a demo must run on sample data only;
  3. ADMIN_USERNAME / ADMIN_PASSWORD set - a real bootstrap administrator means real use.
  4. (app/demo.py) the database file exists but was not created by demo mode - real data is never
     wiped; the start is refused instead.
When demo mode does start, a loud WARNING is logged.

The data directory (data/ next to main.py, or the folder of DATABASE_PATH) is created on start
with mkdir(parents=True, exist_ok=True); bare-metal and Docker installs need no manual step.
data/.secret_key is generated at runtime, is git/docker-ignored and is never shipped.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines). Real environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    database_path: Path
    secret_key: str
    seed_demo_data: bool
    demo_auto_login: bool  # = demo mode (DEMO_MODE, or the 1.0.4 name DEMO_AUTO_LOGIN)
    demo_logins: bool  # DEMO_LOGINS (default True): show Demo sign-in boxes on /login
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    cookie_secure: bool
    session_max_age: int
    host: str
    port: int
    # 1.0.2: security tunables, previously literals in security.py
    pbkdf2_iterations: int = 600_000
    login_max_attempts: int = 5
    login_lock_minutes: int = 10


def _resolve_secret(data_dir: Path) -> str:
    key = os.environ.get("SECRET_KEY", "").strip()
    if key and key != "change-me":
        return key
    # No key configured: create one once and keep it in data/.secret_key
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = data_dir / ".secret_key"
    if key_file.is_file():
        stored = key_file.read_text(encoding="utf-8").strip()
        if len(stored) >= 32:
            return stored
    key = secrets.token_urlsafe(48)
    key_file.write_text(key, encoding="utf-8")
    try:
        os.chmod(key_file, 0o600)
    except OSError:  # pragma: no cover - Windows
        pass
    return key


def load_settings() -> Settings:
    _load_dotenv(BASE_DIR / ".env")
    db_raw = os.environ.get("DATABASE_PATH", "").strip()
    db_path = Path(db_raw) if db_raw else BASE_DIR / "data" / "madrasa.db"
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        database_path=db_path,
        secret_key=_resolve_secret(db_path.parent),
        # 1.0.2: sample data is OFF by default (true only for demos and trying the app out).
        seed_demo_data=_bool("SEED_DEMO_DATA", False),
        # Public demo only: one-click demo logins (no password) on the login page and the database is
        # recreated from sample data on every start. OFF by default. See README "Demo mode".
        # DEMO_MODE is the 1.0.5 name; DEMO_AUTO_LOGIN (1.0.4) is still read and means the same.
        demo_auto_login=_bool("DEMO_MODE", False) or _bool("DEMO_AUTO_LOGIN", False),
        # Login-page Demo sign-in boxes. Default ON, even with no env vars. Set DEMO_LOGINS=false
        # for a real school: the boxes are hidden and the three demo accounts are disabled.
        # This does not wipe the database (that is only DEMO_MODE).
        demo_logins=_bool("DEMO_LOGINS", True),
        # Optional headless bootstrap (Docker/Render): both set => the first admin is created from them
        # instead of the /setup page. Empty (default) => first-run setup page.
        bootstrap_admin_username=os.environ.get("ADMIN_USERNAME", "").strip(),
        bootstrap_admin_password=os.environ.get("ADMIN_PASSWORD", "").strip(),
        cookie_secure=_bool("COOKIE_SECURE", False),
        session_max_age=max(1, _int("SESSION_HOURS", 12)) * 3600,
        host=os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int("PORT", 8000),
        pbkdf2_iterations=max(100_000, _int("PBKDF2_ITERATIONS", 600_000)),
        login_max_attempts=max(1, _int("LOGIN_MAX_ATTEMPTS", 5)),
        login_lock_minutes=max(1, _int("LOGIN_LOCK_MINUTES", 10)),
    )


def validate_settings(s: Settings) -> None:
    """Refuse unsafe combinations before the app starts serving (called from the app lifespan)."""
    if not s.demo_auto_login:
        return
    problems = []
    if s.cookie_secure:
        problems.append("COOKIE_SECURE=true (a production HTTPS install)")
    if not s.seed_demo_data:
        problems.append("SEED_DEMO_DATA is not true (demo mode must run on sample data only)")
    if s.bootstrap_admin_username or s.bootstrap_admin_password:
        problems.append("ADMIN_USERNAME/ADMIN_PASSWORD are set (a real administrator means real use)")
    if problems:
        raise RuntimeError(
            "Refusing to start: DEMO_MODE=true cannot be combined with "
            + "; ".join(problems)
            + ". Demo mode offers password-less demo logins and wipes the database on every start. "
            "Set DEMO_MODE=false (and DEMO_AUTO_LOGIN=false) for real use."
        )


settings = load_settings()
