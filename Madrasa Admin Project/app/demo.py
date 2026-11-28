"""Public demo mode (DEMO_MODE=true; the 1.0.4 name DEMO_AUTO_LOGIN=true still works).

OFF by default - never use it with real data.

What demo mode does:
  * On every start the SQLite database (and its -wal/-shm files) is DELETED and recreated with the
    sample data, so visitors always see a clean demo and nothing they type survives a restart.
  * Three demo accounts exist, each with a real hashed password that is set only in demo mode:
    match), so they cannot be used on the normal login form:
        demo.admin    administrator     password Admin@2026
        demo.karim    sample teacher    password Teacher@2026
        demo.student  first sample student  password Student@2026
    1.0.8: the same three accounts (with hashed passwords) are also created when DEMO_LOGINS is true
    (the default). That does not wipe the database. Set DEMO_LOGINS=false for a real school, which
    hides the boxes and disables these accounts. DEMO_MODE still wipes and re-seeds as above.
  * 1.0.5: no automatic login any more. "/" is the public landing page; its "Live Demo" button opens /login.
  * 1.0.6: /login shows a Demo sign-in box under the form (username, password, "Sign in with this account").
    Clicking a card fills the form; the link submits it. POST /demo/login (CSRF-protected, demo mode only,
    404 otherwise) remains as a one-click option. /tour?autostart=1 is the product tour.
  * 1.0.5: secrets (SMTP password, payment and SMS keys) are never stored in demo mode and the test
    email is disabled (app/integrations.py), so demo visitors can neither read nor plant credentials.
  * The app refuses to start in demo mode with COOKIE_SECURE=true, SEED_DEMO_DATA=false or an
    ADMIN_USERNAME/ADMIN_PASSWORD bootstrap (config.validate_settings), and it refuses to wipe a
    database that holds a non-demo administrator and has no "<db>.demo" marker (written by demo mode).
  * Seeded on every start (app/seed.py _seed_demo and _seed_demo_routine): 20 classes with sections,
    subjects, the school day (periods), a full weekly timetable for 3 sections with four sample
    teachers, 6 students, attendance for the last 5 days, a published "1st Term" exam with marks
    (results incl. one failing subject), fee plans for every class and 3 fee payments with receipts.
    1.0.5 (seed_showcase): 30 more students in the routine sections, 4 weeks of attendance and six months
    of fee payments, so the dashboard charts have something to show.

Risk: anyone who can reach the URL can open the demo administrator. Only for a public sales demo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .models import Attendance, Exam, Mark, Payment, Student, StudentSubject, Subject, User

log = logging.getLogger("madrasa.demo")

DEMO_ADMIN = "demo.admin"
DEMO_TEACHER = "demo.karim"  # one of the sample teachers created by seed._seed_demo_routine
DEMO_STUDENT = "demo.student"
DEMO_STUDENT_ADMISSION = "DEMO-STU"  # dedicated demo student; never reused for a real pupil
DEMO_TEACHER_NAME = "Abdul Karim"
DEMO_ROLES = ("admin", "teacher", "student")
DEMO_APP_NAME = "Madrasa Pro"
# Public demo passwords (hashed and stored only when demo mode starts).
DEMO_PASSWORDS = {
    DEMO_ADMIN: "Admin@2026",
    DEMO_TEACHER: "Teacher@2026",
    DEMO_STUDENT: "Student@2026",
}
# Login page cards: role, label, what the role can do, username, password
ROLE_CARDS = [
    (
        "admin",
        "Administrator",
        "Full access: students, fees, exams, routine and all settings",
        DEMO_ADMIN,
        DEMO_PASSWORDS[DEMO_ADMIN],
    ),
    (
        "teacher",
        "Teacher",
        "Own classes: attendance, marks entry and teaching routine",
        DEMO_TEACHER,
        DEMO_PASSWORDS[DEMO_TEACHER],
    ),
    (
        "student",
        "Student",
        "Own profile: results, attendance, fees and class routine",
        DEMO_STUDENT,
        DEMO_PASSWORDS[DEMO_STUDENT],
    ),
]
SHOWCASE_NAMES = [
    ("Abdullah Al Mamun", "Male"),
    ("Ayesha Siddiqua", "Female"),
    ("Ibrahim Khalil", "Male"),
    ("Zainab Akter", "Female"),
    ("Hasan Mahmud", "Male"),
    ("Nusrat Jahan", "Female"),
    ("Tanvir Ahmed", "Male"),
    ("Sumaiya Rahman", "Female"),
    ("Imran Hossain", "Male"),
    ("Rukaiya Islam", "Female"),
    ("Mahmudul Hasan", "Male"),
    ("Tasnim Ferdous", "Female"),
    ("Arif Billah", "Male"),
    ("Halima Khatun", "Female"),
    ("Sakib Al Hasan", "Male"),
    ("Jannatul Ferdous", "Female"),
    ("Rakibul Islam", "Male"),
    ("Mariam Sultana", "Female"),
    ("Nazmul Huda", "Male"),
    ("Sadia Afrin", "Female"),
    ("Fahim Faisal", "Male"),
    ("Lamia Chowdhury", "Female"),
    ("Ridwan Kabir", "Male"),
    ("Umme Habiba", "Female"),
    ("Shahriar Kabir", "Male"),
    ("Afsana Mimi", "Female"),
    ("Junaid Hasan", "Male"),
    ("Samiha Noor", "Female"),
    ("Mehedi Hasan", "Male"),
    ("Raisa Tabassum", "Female"),
]


def marker_path(db_path: Path) -> Path:
    return Path(str(db_path) + ".demo")


def _non_demo_admins(db_path: Path) -> list[str]:
    """Admin usernames other than demo.admin in an existing database (read-only SQLAlchemy query)."""
    from sqlalchemy import create_engine, inspect

    eng = create_engine(f"sqlite:///file:{db_path}?mode=ro&uri=true")
    try:
        if not inspect(eng).has_table("users"):
            return []
        with Session(eng) as db:
            return list(db.scalars(select(User.username).where(User.role == "admin", User.username != DEMO_ADMIN)))
    except DBAPIError:
        return ["<unreadable database>"]
    finally:
        eng.dispose()


def reset_database_files(db_path: Path) -> None:
    """Delete the demo database so it is recreated from the sample data (demo mode only).

    Refuses (RuntimeError) when a database exists that demo mode did not create: real data is never wiped.
    """
    marker = marker_path(db_path)
    if db_path.is_file() and not marker.is_file() and _non_demo_admins(db_path):
        raise RuntimeError(
            f"Refusing to start in demo mode: {db_path} exists and was not created by demo mode "
            "(it may hold real school data). Use another DATABASE_PATH for the demo or set DEMO_MODE=false."
        )
    for suffix in ("", "-wal", "-shm", "-journal"):
        f = Path(str(db_path) + suffix)
        if f.is_file():
            f.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Created by DEMO_MODE=true. This database is wiped on every start.\n", encoding="utf-8")
    log.warning(
        "DEMO MODE ACTIVE (DEMO_MODE=true): demo sign-in cards (with passwords) on the login page; "
        "database %s recreated with sample data. Never use demo mode with real data.",
        db_path,
    )


def demo_logins_enabled() -> bool:
    """True when the login page should show the Demo sign-in box."""
    from .config import settings as cfg

    return bool(cfg.demo_logins or cfg.demo_auto_login)


def _unused_student_id(db: Session) -> str:
    used = {c for c in db.scalars(select(Student.student_id)).all() if c}
    if "999999" not in used:
        return "999999"
    for n in range(999998, 900000, -1):
        code = f"{n:06d}"
        if code not in used:
            return code
    raise RuntimeError("no free student id for the demo student")


def _first_class_section(db: Session) -> tuple[int, int]:
    """Reuse an existing class/section; create Grade 1 / A only if the database has none."""
    from .models import Class, Section

    sec = db.scalars(select(Section).order_by(Section.id)).first()
    if sec is not None:
        return sec.class_id, sec.id
    klass = db.scalars(select(Class).order_by(Class.id)).first()
    if klass is None:
        klass = Class(name="Grade 1", order=1)
        db.add(klass)
        db.flush()
    sec = Section(name="A", class_id=klass.id)
    db.add(sec)
    db.flush()
    return klass.id, sec.id


def _ensure_demo_student_row(db: Session) -> int:
    """Return a student pk for demo.student. Creates a dedicated row if needed; never edits another pupil."""
    from datetime import date

    from .services import apply_class_defaults

    u = db.scalars(select(User).where(User.username == DEMO_STUDENT)).first()
    if u is not None and u.student_id:
        st = db.get(Student, u.student_id)
        if st is not None:
            return st.id
    st = db.scalars(select(Student).where(Student.admission_no == DEMO_STUDENT_ADMISSION)).first()
    if st is not None:
        return st.id
    cid, sid = _first_class_section(db)
    st = Student(
        student_id=_unused_student_id(db),
        admission_no=DEMO_STUDENT_ADMISSION,
        name="Demo Student",
        gender="Male",
        class_id=cid,
        section_id=sid,
        roll_no=99,
        admission_date=date.today().isoformat(),
        status="Active",
        guardian_name="Demo Guardian",
        guardian_relation="Father",
    )
    db.add(st)
    db.flush()
    apply_class_defaults(db, st)
    return st.id


def ensure_demo_accounts(db: Session, *, with_passwords: bool | None = None) -> None:
    """Create / enable the three demo accounts (idempotent).

    Real hashed passwords (Admin@2026 / Teacher@2026 / Student@2026) are set when
    ``with_passwords`` is true. That is the default in demo mode and when DEMO_LOGINS is on.
    Existing non-demo users are never modified. A missing teacher or student login is created
    without wiping or re-seeding the rest of the database. Passwords are not re-hashed when
    they already match, so calling this on every start is cheap.
    """
    from .config import settings as cfg
    from .security import hash_password, verify_password
    from .seed import NO_PASSWORD

    if with_passwords is None:
        with_passwords = bool(cfg.demo_auto_login or cfg.demo_logins)

    changed = False

    def password_hash_for(username: str, current: str | None) -> str:
        if not with_passwords:
            return NO_PASSWORD
        if current and current != NO_PASSWORD and verify_password(DEMO_PASSWORDS[username], current):
            return current
        return hash_password(DEMO_PASSWORDS[username])

    def upsert(username: str, role: str, full_name: str, student_id: int | None = None) -> None:
        nonlocal changed
        u = db.scalars(select(User).where(User.username == username)).first()
        if u is None:
            db.add(
                User(
                    username=username,
                    role=role,
                    full_name=full_name,
                    student_id=student_id,
                    password_hash=password_hash_for(username, None),
                    is_active=True,
                    must_change_password=False,
                )
            )
            changed = True
            return
        new_hash = password_hash_for(username, u.password_hash)
        if u.password_hash != new_hash:
            u.password_hash = new_hash
            changed = True
        if not u.is_active:
            u.is_active = True
            changed = True
        if u.must_change_password:
            u.must_change_password = False
            changed = True
        if student_id is not None and u.student_id is None:
            u.student_id = student_id
            changed = True
        if not u.full_name:
            u.full_name = full_name
            changed = True
        if u.role != role and username in DEMO_PASSWORDS:
            u.role = role
            changed = True

    upsert(DEMO_ADMIN, "admin", "Demo Administrator")
    upsert(DEMO_TEACHER, "teacher", DEMO_TEACHER_NAME)
    upsert(DEMO_STUDENT, "student", "Demo Student", _ensure_demo_student_row(db))
    if changed:
        db.commit()


def _has_published_demo_password(username: str, password_hash: str | None) -> bool:
    from .security import verify_password
    from .seed import NO_PASSWORD

    if not password_hash or password_hash == NO_PASSWORD:
        return False
    return verify_password(DEMO_PASSWORDS[username], password_hash)


def disable_demo_logins(db: Session) -> None:
    """Disable the reserved demo accounts that still use the published demo passwords.

    Accounts a school has taken over (custom password on demo.karim, for example) are
    left unchanged. Other users are never touched.
    """
    from .seed import NO_PASSWORD

    changed = False
    for username in (DEMO_ADMIN, DEMO_TEACHER, DEMO_STUDENT):
        u = db.scalars(select(User).where(User.username == username)).first()
        if u is None:
            continue
        adopted = (
            u.password_hash
            and u.password_hash != NO_PASSWORD
            and not _has_published_demo_password(username, u.password_hash)
        )
        if adopted:
            continue
        if u.is_active:
            u.is_active = False
            changed = True
        if u.password_hash != NO_PASSWORD:
            u.password_hash = NO_PASSWORD
            changed = True
    if changed:
        db.commit()


def sync_demo_logins(db: Session) -> None:
    """Apply DEMO_LOGINS / DEMO_MODE to the three demo accounts (idempotent, no wipe)."""
    if demo_logins_enabled():
        ensure_demo_accounts(db, with_passwords=True)
    else:
        disable_demo_logins(db)


def demo_user(db: Session, role: str) -> User | None:
    username = {"admin": DEMO_ADMIN, "teacher": DEMO_TEACHER, "student": DEMO_STUDENT}.get(role)
    if not username:
        return None
    u = db.scalars(select(User).where(User.username == username)).first()
    return u if u is not None and u.is_active else None


def seed_showcase(db: Session) -> None:
    """Demo mode only: a fuller sample school for the public demo (idempotent).

    Adds 30 students to the three sections that have a routine, attendance for the last 28 days
    (working days only), marks for the published exam and monthly tuition payments for the last six
    months, so the dashboard charts, lists and reports look like a school in use. Never called outside
    demo mode.
    """
    from datetime import date, datetime, timedelta

    from .services import apply_class_defaults, monthly_fee, working_days

    first = db.scalars(select(Student).order_by(Student.id)).all()
    if len(first) != 6 or not first:
        return  # not the fresh demo database (or already done)
    sections = [
        (first[0].class_id, first[0].section_id),
        (first[4].class_id, first[4].section_id),
        (first[2].class_id, first[2].section_id),
    ]
    year = date.today().year
    new: list[Student] = []
    for i, (name, gender) in enumerate(SHOWCASE_NAMES):
        cid, sid = sections[i % 3]
        code = f"{7 + i:06d}"
        s = Student(
            student_id=code,
            admission_no=f"ADM-{year}-{code[-3:]}",
            name=name,
            gender=gender,
            dob=f"{2011 + i % 6}-{1 + i % 12:02d}-{1 + (i * 3) % 27:02d}",
            class_id=cid,
            section_id=sid,
            roll_no=10 + i // 3,
            admission_date=f"{year}-01-{10 + i % 15:02d}",
            status="Active",
            guardian_name=("Md. " if i % 2 == 0 else "Mrs. ") + name.split()[-1],
            guardian_relation="Father" if i % 2 == 0 else "Mother",
            address="Dhaka",
        )
        db.add(s)
        new.append(s)
    db.commit()
    for s in new:
        apply_class_defaults(db, s)
    db.commit()
    for s in first:
        s.guardian_phone = None  # public demo: no phone numbers on screen (not even made-up ones)
    db.commit()
    everyone = first + new
    days = set(working_days(db))
    codes = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
    today = date.today()
    have = {(a.student_id, a.date) for a in db.scalars(select(Attendance)).all()}
    for back in range(0, 28):
        d = today - timedelta(days=back)
        if codes[d.weekday()] not in days:
            continue
        for i, s in enumerate(everyone):
            if (s.id, d.isoformat()) in have:
                continue
            k = (i * 7 + back * 3) % 23
            status = "Absent" if k == 0 or k == 11 else "Late" if k == 5 else "Present"
            stamp = datetime(d.year, d.month, d.day, 3, 30) + timedelta(seconds=i)  # morning roll call (UTC)
            db.add(
                Attendance(student_id=s.id, date=d.isoformat(), status=status, marked_by="demo.karim", updated_at=stamp)
            )
    db.commit()
    for back in range(5, -1, -1):
        y, m = today.year, today.month - back
        while m < 1:
            y, m = y - 1, m + 12
        month = f"{y:04d}-{m:02d}"
        day = min(today.day, 10) if back == 0 else 10
        for i, s in enumerate(everyone):
            if back == 0 and i < 3:
                continue  # the 3 receipts of the base demo data are this month's
            if (i + back) % 5 == 0 or (back == 0 and i % 3 == 0):
                continue  # some families pay late: gives the dues list something to show
            plan_due = monthly_fee(db, s.class_id) or 1500
            p = Payment(
                student_id=s.id,
                amount=plan_due,
                date=f"{month}-{day:02d}",
                fee_month=month,
                fee_head="Monthly Tuition",
                method=("Cash", "bKash", "Bank", "Nagad")[(i + back) % 4],
                collected_by="demo.admin",
                is_void=False,
                receipt_no=f"TMP-S{back}-{i}",
            )
            db.add(p)
            db.flush()
            p.receipt_no = f"RCP-{y}-{p.id:05d}"
    db.commit()
    # marks for the published exam(s) of the base demo data, so result lists and cards are full
    exams = db.scalars(select(Exam).where(Exam.is_published.is_(True)).order_by(Exam.id)).all()
    subjects = {x.id: x for x in db.scalars(select(Subject)).all()}
    for exam in exams:
        for i, st in enumerate(new):
            for j, link in enumerate(
                db.scalars(select(StudentSubject).where(StudentSubject.student_id == st.id)).all()
            ):
                sub = subjects.get(link.subject_id)
                if sub is None:
                    continue
                full = sub.max_marks or 100
                score = round(full * (0.42 + ((i * 13 + j * 7 + exam.id * 5) % 55) / 100))
                db.add(
                    Mark(
                        student_id=st.id,
                        exam_id=exam.id,
                        subject_id=sub.id,
                        marks_obtained=min(score, full),
                        max_marks=full,
                        entered_by="demo.karim",
                    )
                )
    db.commit()
