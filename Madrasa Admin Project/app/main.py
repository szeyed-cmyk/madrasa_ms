"""FastAPI application: pages, print views, middleware and error handling."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, demo, grading, i18n, services, theme
from .api import MAX_LOGO_BYTES, logo_from_upload
from .api import router as api_router
from .config import BASE_DIR, settings, validate_settings
from .database import SessionLocal, get_db, migrate
from .models import (
    DEFAULT_APP_NAME,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLOR,
    DEFAULT_TAGLINE,
    Attendance,
    Class,
    Currency,
    Exam,
    Payment,
    SchoolSettings,
    Section,
    Student,
    User,
    utcnow,
)
from .security import (
    check_csrf,
    csrf_token,
    ensure_student_access,
    hash_password,
    login_session,
    login_throttle,
    needs_rehash,
    password_problem,
    session_user,
    verify_password,
)
from .seed import admin_exists, seed


def brand_context(request: Request) -> dict:
    """Branding + language for every template: app name, tagline, logo, colours (CSS variables),
    the interface language (t() translator, dir=rtl for Arabic) and the language list (1.0.5)."""
    name, tagline, logo = DEFAULT_APP_NAME, DEFAULT_TAGLINE, None
    primary, secondary = DEFAULT_PRIMARY_COLOR, DEFAULT_SECONDARY_COLOR
    lang_code, lang_dir, langs, cat, currencies = "en", "ltr", [], i18n.builtin("en"), []
    try:
        with SessionLocal() as db:
            s = db.scalars(select(SchoolSettings).order_by(SchoolSettings.id)).first()
            if s:
                name, tagline, logo = s.name or DEFAULT_APP_NAME, s.tagline or "", s.logo_path
                primary = s.primary_color if theme.valid_hex(s.primary_color) else primary
                secondary = s.secondary_color if theme.valid_hex(s.secondary_color) else secondary
            lang = i18n.current(db, request.session if "session" in request.scope else {}, s)
            if lang is not None:
                lang_code, lang_dir = lang.code, "rtl" if lang.is_rtl else "ltr"
            langs = [{"code": x.code, "name": x.native_name or x.name} for x in i18n.languages(db)]
            cat = i18n.catalog(db, lang_code)
            currencies = [
                {
                    "code": c.code,
                    "symbol": c.symbol,
                    "rate": c.rate,
                    "decimals": c.decimals,
                    "is_default": bool(c.is_default),
                }
                for c in db.scalars(select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.id)).all()
            ]
    except Exception:  # pragma: no cover - database not ready yet: fall back to the defaults
        pass
    return {
        "brand_name": name,
        "brand_tagline": tagline,
        "brand_logo": logo,
        "theme_css": theme.css_vars(primary, secondary),
        "brand_primary": primary,
        "lang_code": lang_code,
        "lang_dir": lang_dir,
        "languages": langs,
        "t": i18n.Translator(cat),
        "i18n_json": json.dumps(i18n.for_js(cat), ensure_ascii=False),
        "currencies": currencies,
        "currencies_json": json.dumps(currencies, ensure_ascii=False),
    }


templates = Jinja2Templates(directory=str(BASE_DIR / "templates"), context_processors=[brand_context])
templates.env.globals["app_version"] = __version__
templates.env.globals["demo_mode"] = settings.demo_auto_login


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from sqlalchemy import inspect

    from .database import engine

    validate_settings(settings)  # 1.0.2: e.g. refuses DEMO_AUTO_LOGIN together with COOKIE_SECURE
    if settings.demo_auto_login:
        # Public demo: start from a fresh sample database on every start (see app/demo.py).
        engine.dispose()
        demo.reset_database_files(settings.database_path)
    # An older (1.1.x) database gets the routine tables now: give it the standard school day once.
    insp = inspect(engine)
    upgrade_routine = insp.has_table("classes") and not insp.has_table("periods")
    migrate()
    db = SessionLocal()
    try:
        seed(db, demo=True if settings.demo_auto_login else None, default_periods=True if upgrade_routine else None)
        if settings.demo_auto_login:
            demo.seed_showcase(db)  # 1.0.5: more students, 6 months of fees, 4 weeks of attendance
            s = services.school(db)
            s.name = demo.DEMO_APP_NAME
            db.commit()
        # 1.0.8: Demo sign-in boxes (default on). Does not wipe; DEMO_MODE already reset the DB above.
        demo.sync_demo_logins(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Madrasa & School Admin System",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="madrasa_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.cookie_secure,
)

CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'; object-src 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/") or request.url.path.startswith("/print/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api_router)


# ------------------------------------------------------------------ errors
def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api/")


# Registered for Starlette's base class so unknown URLs and missing static files (raised by the router
# itself, not by our code) also get the friendly error page instead of raw JSON.
@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if _is_api(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    if exc.status_code == 403 and "Password change required" in str(exc.detail):
        return RedirectResponse("/change-password", status_code=303)
    return templates.TemplateResponse(
        request, "error.html", {"code": exc.status_code, "message": exc.detail}, status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        msg = str(err.get("msg", "Invalid value")).replace("Value error, ", "")
        problems.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    detail = "; ".join(problems) or "Invalid input"
    if _is_api(request):
        return JSONResponse({"detail": detail, "errors": problems}, status_code=422)
    return templates.TemplateResponse(request, "error.html", {"code": 422, "message": detail}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):  # pragma: no cover - safety net
    if _is_api(request):
        return JSONResponse({"detail": "Unexpected server error. Please try again."}, status_code=500)
    return templates.TemplateResponse(
        request, "error.html", {"code": 500, "message": "Unexpected server error."}, status_code=500
    )


# ------------------------------------------------------------------ helpers
def page_user(request: Request, db: Session, roles: tuple[str, ...] | None = None) -> User:
    user = session_user(request, db)
    if not user:
        raise HTTPException(401)
    if user.must_change_password:
        raise HTTPException(403, "Password change required")
    if roles and user.role not in roles:
        raise HTTPException(403, "You do not have permission to open this page.")
    return user


def _scoped(query, db: Session, user: User):
    """1.3.0: limit a Student query to the classes a teacher teaches (admins: unchanged)."""
    cond = services.student_condition(db, user)
    return query if cond is None else query.where(cond)


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    db_ctx = {"csrf_token": csrf_token(request)}
    db_ctx.update(ctx or {})
    return templates.TemplateResponse(request, name, db_ctx, status_code=status_code)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------ pages
@app.get("/healthz")
def healthz():
    return {"ok": True, "version": __version__}


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    """Public landing page. Always shown at "/", including on a fresh install before /setup.
    Settings > Branding can switch it off; "/" then opens the app (or /setup if no administrator yet)."""
    school = services.school(db)
    has_admin = admin_exists(db)
    if school.landing_enabled is False:
        if not has_admin and not session_user(request, db):
            return RedirectResponse("/setup", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)
    user = session_user(request, db)
    return render(
        request,
        "landing.html",
        {"school": school, "user": user, "demo": settings.demo_auto_login, "needs_setup": not has_admin},
    )


@app.get("/tour", response_class=HTMLResponse)
def product_tour(request: Request, db: Session = Depends(get_db)):
    """Product tour (screenshot walkthrough of the real app). ?autostart=1 starts playing.
    Public: no login and no administrator required."""
    return render(
        request,
        "tour.html",
        {
            "school": services.school(db),
            "user": session_user(request, db),
            "demo": settings.demo_auto_login,
            "autostart": request.query_params.get("autostart") == "1",
        },
    )


@app.get("/dashboard", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """The app: admin / teacher single-page UI (students go to their profile hub)."""
    if not admin_exists(db) and not session_user(request, db):
        return RedirectResponse("/setup", status_code=303)
    user = page_user(request, db)
    if user.role == "student":
        if not user.student_id:
            raise HTTPException(403, "This student account is not linked to a student record.")
        return RedirectResponse(f"/student/{user.student_id}", status_code=303)
    return render(request, "index.html", {"user": user, "school": services.school(db)})


@app.post("/set-language")
def set_language(
    request: Request,
    lang: str = Form(..., max_length=10),
    next_url: str = Form("/", alias="next", max_length=300),
    csrf_token_field: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    """1.0.5: switch the interface language for this browser session (any visitor, CSRF-checked)."""
    check_csrf(request, csrf_token_field)
    if lang not in {x.code for x in i18n.languages(db)}:
        raise HTTPException(400, "Unknown language")
    request.session["lang"] = lang
    safe = next_url if next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url else "/"
    return RedirectResponse(safe, status_code=303)


# ------------------------------------------------------------------ first-run setup
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")


def _read_logo(upload: UploadFile) -> bytes:
    """Read at most MAX_LOGO_BYTES + 1 bytes of an upload (sync route: use the underlying file)."""
    return upload.file.read(MAX_LOGO_BYTES + 1)


def _setup_ctx(**values) -> dict:
    form = {"app_name": DEFAULT_APP_NAME, "tagline": DEFAULT_TAGLINE, "username": "", "full_name": ""}
    form.update(values)
    return {"form": form}


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    if admin_exists(db):
        # Already set up — go to the admin dashboard
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "setup.html", _setup_ctx())


@app.post("/setup")
def setup_submit(
    request: Request,
    # Every field is optional here so that a finished setup answers 404 before any form validation (422).
    app_name: str = Form(""),
    tagline: str = Form(""),
    username: str = Form(""),
    full_name: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    csrf_token_field: str = Form("", alias="csrf_token"),
    logo: UploadFile | None = File(None),  # 1.3.0: optional school logo (PNG/JPG/GIF/WebP, max 300 KB)
    db: Session = Depends(get_db),
):
    if admin_exists(db):
        raise HTTPException(404, "Setup is already complete.")
    check_csrf(request, csrf_token_field)
    logo_url, logo_error = None, None
    if logo is not None and (logo.filename or ""):
        raw = _read_logo(logo)
        if raw:
            try:
                logo_url = logo_from_upload(raw)
            except HTTPException as exc:
                logo_error = f"Logo: {exc.detail}"
    app_name, tagline, username, full_name = app_name.strip(), tagline.strip(), username.strip(), full_name.strip()
    ctx = _setup_ctx(app_name=app_name, tagline=tagline, username=username, full_name=full_name)
    if not app_name:
        error = "Enter the name to show across the app."
    elif len(app_name) > 120 or len(tagline) > 160 or len(full_name) > 120:
        error = "Name: max. 120 characters, tagline: max. 160 characters."
    elif len(password) > 128:
        error = "The password can be at most 128 characters."
    elif db.scalars(select(User).where(func.lower(User.username) == username.lower())).first():
        error = "That username is already used (for example by one of the sample teachers). Choose another one."
    elif not USERNAME_RE.match(username):
        error = "Username: 3-64 characters, letters, digits, dot, dash or underscore only."
    elif password != confirm_password:
        error = "The passwords do not match."
    elif password.lower() == username.lower():
        error = "The password must be different from the username."
    else:
        error = password_problem(password) or logo_error
    if error:
        return render(request, "setup.html", {**ctx, "error": error}, 400)
    s = services.school(db)
    s.name, s.tagline = app_name, tagline or None
    if logo_url:
        s.logo_path = logo_url
    user = User(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        full_name=full_name or "Administrator",
        must_change_password=False,
        is_active=True,
        last_login=utcnow(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # pragma: no cover - two setups at the same moment
        db.rollback()
        raise HTTPException(404, "Setup is already complete.") from exc
    login_session(request, user)
    return RedirectResponse("/dashboard", status_code=303)


def _login_ctx(db: Session, **extra) -> dict:
    """Shared login template context. Demo sign-in cards stay visible after errors when enabled."""
    ctx = {"school": services.school(db), **extra}
    if demo.demo_logins_enabled():
        ctx["demo"] = True
        ctx["demo_roles"] = demo.ROLE_CARDS
    return ctx


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if demo.demo_logins_enabled():
        demo.sync_demo_logins(db)
        if session_user(request, db):
            return RedirectResponse("/dashboard", status_code=303)
        return render(request, "login.html", _login_ctx(db))
    if not admin_exists(db):
        return RedirectResponse("/setup", status_code=303)
    if session_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html", _login_ctx(db))


@app.post("/login")
def login(
    request: Request,
    username: str = Form(..., max_length=64),
    password: str = Form(..., max_length=128),
    csrf_token_field: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    check_csrf(request, csrf_token_field)
    if demo.demo_logins_enabled():
        demo.sync_demo_logins(db)
    elif not admin_exists(db):
        return RedirectResponse("/setup", status_code=303)
    ip = _client_ip(request)
    ctx = _login_ctx(db, username=username)
    if login_throttle.blocked(ip, username):
        error = f"Too many failed attempts. Wait {settings.login_lock_minutes} minutes."
        return render(request, "login.html", {**ctx, "error": error}, 429)
    user = db.scalars(select(User).where(func.lower(User.username) == username.strip().lower())).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        login_throttle.fail(ip, username)
        return render(request, "login.html", {**ctx, "error": "Invalid username or password."}, 400)
    login_throttle.reset(ip, username)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login = utcnow()
    db.commit()
    login_session(request, user)
    if user.must_change_password:
        return RedirectResponse("/change-password", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/demo/login")
def demo_login(
    request: Request,
    role: str = Form("admin", max_length=16),
    csrf_token_field: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    """Demo sign-in only (404 otherwise): switch to the demo administrator, teacher or student."""
    if not demo.demo_logins_enabled():
        raise HTTPException(404, "Not found")
    check_csrf(request, csrf_token_field)
    user = demo.demo_user(db, role) if role in demo.DEMO_ROLES else None
    if user is None:
        raise HTTPException(400, "Unknown demo role.")
    login_session(request, user)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf_token_field: str = Form("", alias="csrf_token")):
    check_csrf(request, csrf_token_field)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/logout")
def logout_get():
    # Logging out needs a POST with a CSRF token; a plain link just goes back home.
    return RedirectResponse("/", status_code=303)


@app.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request, db: Session = Depends(get_db)):
    user = session_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return render(request, "change_password.html", {"user": user, "forced": user.must_change_password})


@app.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(..., max_length=128),
    new_password: str = Form(..., max_length=128),
    confirm_password: str = Form(..., max_length=128),
    csrf_token_field: str = Form("", alias="csrf_token"),
    db: Session = Depends(get_db),
):
    check_csrf(request, csrf_token_field)
    user = session_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    ctx = {"user": user, "forced": user.must_change_password}
    error = None
    if not verify_password(current_password, user.password_hash):
        error = "Current password is wrong."
    elif new_password != confirm_password:
        error = "The new passwords do not match."
    elif new_password == current_password:
        error = "Choose a password different from the current one."
    else:
        error = password_problem(new_password)
    if error:
        return render(request, "change_password.html", {**ctx, "error": error}, 400)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    login_session(request, user)  # new session for the new password; other sessions are logged out
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/student/{student_pk}", response_class=HTMLResponse)
def student_page(student_pk: int, request: Request, db: Session = Depends(get_db)):
    user = page_user(request, db)
    ensure_student_access(user, student_pk, db)
    student = db.get(Student, student_pk)
    if not student:
        raise HTTPException(404, "Student not found")
    return render(
        request,
        "student.html",
        {"user": user, "student_pk": student_pk, "student": student, "school": services.school(db)},
    )


# ------------------------------------------------------------------ print views (server-rendered, auto-escaped)
def _opt_id(raw: str | None) -> int | None:
    """Optional numeric id from a query string; a blank value (e.g. "?exam_id=") means "not chosen"."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(400, "Invalid id") from exc
    if value < 1:
        raise HTTPException(400, "Invalid id")
    return value


def _print_ctx(db: Session) -> dict:
    s = services.school(db)
    return {
        "school": s,
        "today": date.today().isoformat(),
        "scale_label": grading.scale(s.grading_scale)["label"],
        "currency": s.currency or "৳",
    }


@app.get("/print/result/{student_pk}", response_class=HTMLResponse)
def print_result(student_pk: int, request: Request, exam_id: str | None = None, db: Session = Depends(get_db)):
    user = page_user(request, db)
    exam_id = _opt_id(exam_id)
    ensure_student_access(user, student_pk, db)
    s = db.get(Student, student_pk)
    if not s:
        raise HTTPException(404, "Student not found")
    exam = db.get(Exam, exam_id) if exam_id else services.default_exam(db, s.id, user.role == "student")
    if exam_id and (not exam or (user.role == "student" and not exam.is_published)):
        raise HTTPException(404, "Exam not found")
    ctx = _print_ctx(db)
    classes, sections = services.class_maps(db)
    card = {
        **services.student_result(db, s, exam, ctx["school"].grading_scale),
        "student": services.student_dict(s, classes, sections),
    }
    att = services.attendance_summary(db, s.id)
    return render(
        request,
        "print_results.html",
        {**ctx, "exam": exam, "cards": [card], "attendance": {s.id: att}, "title": f"Result card - {s.name}"},
    )


@app.get("/print/results", response_class=HTMLResponse)
def print_results(
    request: Request, exam_id: str | None = None, class_id: int = 0, section_id: int = 0, db: Session = Depends(get_db)
):
    user = page_user(request, db, ("admin", "teacher"))
    chosen = _opt_id(exam_id)
    # No exam chosen yet (blank link): fall back to the latest exam instead of a validation error.
    exam = db.get(Exam, chosen) if chosen else services.default_exam(db, None)
    if not exam:
        raise HTTPException(404, "Exam not found")
    ctx = _print_ctx(db)
    rows = services.class_results(db, exam, class_id or None, section_id or None, ctx["school"].grading_scale)
    cond = services.student_condition(db, user)
    if cond is not None:  # 1.3.0: teachers print only the classes they teach
        visible = set(db.scalars(select(Student.id).where(cond)).all())
        rows = [r for r in rows if r["student_pk"] in visible]
    att = {r["student_pk"]: services.attendance_summary(db, r["student_pk"]) for r in rows}
    return render(
        request,
        "print_results.html",
        {**ctx, "exam": exam, "cards": rows, "attendance": att, "title": f"Result cards - {exam.name}"},
    )


@app.get("/print/receipt/{payment_id}", response_class=HTMLResponse)
def print_receipt(payment_id: int, request: Request, db: Session = Depends(get_db)):
    page_user(request, db, ("admin",))
    p = db.get(Payment, payment_id)
    if not p:
        raise HTTPException(404, "Receipt not found")
    st = db.get(Student, p.student_id)
    cls = db.get(Class, st.class_id) if st else None
    sec = db.get(Section, st.section_id) if st else None
    return render(
        request,
        "print_receipt.html",
        {
            **_print_ctx(db),
            "p": services.payment_dict(p, st),
            "student": st,
            "class_name": cls.name if cls else "",
            "section_name": sec.name if sec else "",
        },
    )


@app.get("/print/attendance", response_class=HTMLResponse)
def print_attendance(request: Request, class_id: int = 0, section_id: int = 0, db: Session = Depends(get_db)):
    user = page_user(request, db, ("admin", "teacher"))
    day_raw = request.query_params.get("date") or date.today().isoformat()
    try:
        day = date.fromisoformat(day_raw).isoformat()
    except ValueError as exc:
        raise HTTPException(400, "Invalid date") from exc
    q = _scoped(select(Student).where(func.lower(Student.status) == "active"), db, user)
    if class_id:
        q = q.where(Student.class_id == class_id)
    if section_id:
        q = q.where(Student.section_id == section_id)
    students = db.scalars(q.order_by(Student.roll_no, Student.name)).all()
    saved = {a.student_id: a.status for a in db.scalars(select(Attendance).where(Attendance.date == day)).all()}
    classes, sections = services.class_maps(db)
    rows = [
        {"s": services.student_dict(s, classes, sections), "status": saved.get(s.id, "Not marked")} for s in students
    ]
    cls = classes.get(class_id)
    return render(
        request,
        "print_attendance.html",
        {**_print_ctx(db), "day": day, "rows": rows, "class_name": cls.name if cls else "All classes"},
    )


@app.get("/print/students", response_class=HTMLResponse)
def print_students(request: Request, class_id: int = 0, db: Session = Depends(get_db)):
    user = page_user(request, db, ("admin", "teacher"))
    q = _scoped(select(Student).where(func.lower(Student.status) != "archived"), db, user)
    if class_id:
        q = q.where(Student.class_id == class_id)
    classes, sections = services.class_maps(db)
    rows = [
        services.student_dict(s, classes, sections)
        for s in db.scalars(q.order_by(Student.class_id, Student.roll_no, Student.name)).all()
    ]
    cls = classes.get(class_id)
    return render(
        request,
        "print_students.html",
        {**_print_ctx(db), "rows": rows, "class_name": cls.name if cls else "All classes"},
    )


@app.get("/print/dues", response_class=HTMLResponse)
def print_dues(request: Request, class_id: int = 0, db: Session = Depends(get_db)):
    """Printable fee-due list (replaces the SMS fee reminders of 1.1.x): call or hand a slip to guardians."""
    page_user(request, db, ("admin",))
    q = select(Student).where(func.lower(Student.status) == "active")
    if class_id:
        q = q.where(Student.class_id == class_id)
    classes, sections = services.class_maps(db)
    rows = []
    for s in db.scalars(q.order_by(Student.class_id, Student.roll_no, Student.name)).all():
        fs = services.fee_status(db, s)
        if fs["due"] > 0:
            rows.append({"s": services.student_dict(s, classes, sections), "fees": fs})
    cls = classes.get(class_id)
    return render(
        request,
        "print_dues.html",
        {
            **_print_ctx(db),
            "rows": rows,
            "total": round(sum(r["fees"]["due"] for r in rows), 2),
            "class_name": cls.name if cls else "All classes",
            "title": "Fee due list",
        },
    )


def _routine_grid(db: Session, slots: list[dict]) -> dict:
    days = services.working_days(db)
    cells = {(x["day"], x["period_id"]): x for x in slots}
    return {"days": days, "day_names": services.DAY_NAMES, "periods": services.periods(db), "cells": cells}


@app.get("/print/routine", response_class=HTMLResponse)
def print_class_routine(request: Request, section_id: int = 0, db: Session = Depends(get_db)):
    user = page_user(request, db)
    if user.role == "student":
        own = db.get(Student, user.student_id) if user.student_id else None
        if not own:
            raise HTTPException(403, "This student account is not linked to a student record.")
        section_id = own.section_id
    sec = db.get(Section, section_id) if section_id else None
    if not sec:
        raise HTTPException(404, "Section not found")
    if user.role == "teacher" and not services.in_scope(services.teacher_scope(db, user.id), sec.class_id, sec.id):
        raise HTTPException(403, "This class is not one you teach.")
    cls = db.get(Class, sec.class_id)
    heading = f"Class routine — {cls.name if cls else ''} - Section {sec.name}"
    return render(
        request,
        "print_routine.html",
        {
            **_print_ctx(db),
            **_routine_grid(db, services.routine_slots(db, section_id=sec.id)),
            "heading": heading,
            "mode": "class",
            "title": heading,
        },
    )


@app.get("/print/routine/teacher/{teacher_id}", response_class=HTMLResponse)
def print_teacher_routine(teacher_id: int, request: Request, db: Session = Depends(get_db)):
    user = page_user(request, db, ("admin", "teacher"))
    if user.role == "teacher" and user.id != teacher_id:
        raise HTTPException(403, "You can only print your own routine.")
    teacher = db.get(User, teacher_id)
    if not teacher or teacher.role not in ("admin", "teacher"):
        raise HTTPException(404, "Teacher not found")
    heading = f"Teacher routine — {services.teacher_name(teacher)}"
    return render(
        request,
        "print_routine.html",
        {
            **_print_ctx(db),
            **_routine_grid(db, services.routine_slots(db, teacher_id=teacher_id)),
            "heading": heading,
            "mode": "teacher",
            "title": heading,
        },
    )
