"""Password hashing, sessions, CSRF, role checks and login throttling.

Role guards used by every API route (declared per route as a FastAPI dependency):
  current_user  - any signed-in account (password already changed)
  require_staff - admin or teacher
  require_admin - admin only
Record isolation: ensure_student_access() / services.student_condition() limit teachers to the
classes they teach and students to their own record. tests/test_guards_v104.py and tests/test_auth.py list every
route and fail if a route has no role guard, or a write/DELETE route lacks require_admin/require_staff.

Login throttle (1.0.4): failed attempts are stored in the database table login_attempts, so the
lock survives restarts and is shared by every worker/process that uses the same database file.
Default: 5 failures within 10 minutes lock that username + IP for 10 minutes (LOGIN_MAX_ATTEMPTS,
LOGIN_LOCK_MINUTES). Successful login clears the counter.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

PBKDF2_ITERATIONS = settings.pbkdf2_iterations  # PBKDF2_ITERATIONS env var, default 600000
LEGACY_ITERATIONS = 100_000  # hashes written by version 1.0
MIN_PASSWORD_LENGTH = 8
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ---------------------------------------------------------------- passwords
def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or password is None:
        return False
    try:
        parts = stored.split("$")
        if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
            iterations, salt, expected = int(parts[1]), parts[2], parts[3]
        elif len(parts) == 2:  # legacy "salt$hex"
            iterations, salt, expected = LEGACY_ITERATIONS, parts[0], parts[1]
        else:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), iterations)
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, TypeError):
        return False


def needs_rehash(stored: str) -> bool:
    return not stored.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")


def password_problem(password: str) -> str | None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 128:
        return "Password is too long (max 128)."
    if password.lower() in {"admin123", "teacher123", "student123", "password", "12345678"}:
        return "That password is too common. Choose another one."
    return None


def password_fingerprint(user: User) -> str:
    """Changes whenever the password changes, so old sessions stop working."""
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


# ---------------------------------------------------------------- sessions
def login_session(request: Request, user: User) -> None:
    request.session.clear()  # prevent session fixation
    request.session["uid"] = user.id
    request.session["pv"] = password_fingerprint(user)
    request.session["csrf"] = secrets.token_urlsafe(32)


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, supplied: str | None) -> None:
    expected = request.session.get("csrf")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        raise HTTPException(403, "Invalid or missing CSRF token. Reload the page and try again.")


def csrf_protect(request: Request) -> None:
    """Router dependency: every state-changing API call must send X-CSRF-Token."""
    if request.method in SAFE_METHODS:
        return
    check_csrf(request, request.headers.get("x-csrf-token"))


def session_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        request.session.clear()
        return None
    if not hmac.compare_digest(str(request.session.get("pv", "")), password_fingerprint(user)):
        request.session.clear()
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user(request, db)
    if not user:
        raise HTTPException(401, "Not logged in")
    if user.must_change_password:
        raise HTTPException(403, "Password change required. Open /change-password.")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission for this action.")
        return user

    return checker


require_admin = require_roles("admin")
require_staff = require_roles("admin", "teacher")


def ensure_student_access(user: User, student_pk: int, db: Session) -> None:
    """1.3.0 role scope: admin sees every student, a teacher only students of the classes/sections
    they teach (subject assignments or routine periods), a student account only its own record."""
    from . import services  # local import: services imports models only, keeps this module light
    from .models import Student

    if user.role == "admin":
        return
    if user.role == "student" and user.student_id == student_pk:
        return
    if user.role == "teacher" and services.can_view_student(db, user, db.get(Student, student_pk)):
        return
    if user.role == "teacher":
        raise HTTPException(403, "This student is not in a class you teach.")
    raise HTTPException(403, "You can only view your own record.")


# ---------------------------------------------------------------- throttling
class LoginThrottle:
    """Persistent failed-login limiter (table login_attempts). Defaults: 5 failures in 10 minutes lock the
    username + IP pair for 10 minutes (LOGIN_MAX_ATTEMPTS / LOGIN_LOCK_MINUTES)."""

    def __init__(self, limit: int = 5, window: int = 600):
        self.limit = limit
        self.window = window

    @staticmethod
    def _key(ip: str, username: str) -> str:
        return f"{ip}|{username.strip().lower()}"[:200]

    @staticmethod
    def _session() -> Session:
        from .database import SessionLocal  # local import: database imports config only

        return SessionLocal()

    def _since(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=self.window)

    def blocked(self, ip: str, username: str) -> bool:
        from .models import LoginAttempt

        with self._session() as db:
            n = db.scalar(
                select(func.count())
                .select_from(LoginAttempt)
                .where(LoginAttempt.key == self._key(ip, username), LoginAttempt.attempted_at >= self._since())
            )
            return (n or 0) >= self.limit

    def fail(self, ip: str, username: str) -> None:
        from .models import LoginAttempt

        with self._session() as db:
            db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < self._since()))  # housekeeping
            db.add(LoginAttempt(key=self._key(ip, username), attempted_at=datetime.now(UTC).replace(tzinfo=None)))
            db.commit()

    def reset(self, ip: str | None = None, username: str | None = None) -> None:
        from .models import LoginAttempt

        with self._session() as db:
            if ip is None:
                cond = LoginAttempt.id.is_not(None)  # every row, with an explicit WHERE
            else:
                cond = LoginAttempt.key == self._key(ip, username or "")
            db.execute(delete(LoginAttempt).where(cond))
            db.commit()


login_throttle = LoginThrottle(limit=settings.login_max_attempts, window=settings.login_lock_minutes * 60)
