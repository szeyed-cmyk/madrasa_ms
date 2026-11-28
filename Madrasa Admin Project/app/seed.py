"""First-run data: settings, classes, subjects and (optional) demo records.

No user account is created here with a known password. The first administrator is created on the
/setup page (or, for headless Docker/Render installs, from ADMIN_USERNAME + ADMIN_PASSWORD).
The demo data has four teacher records for the demo routine; they are disabled and have NO password
until the administrator gives them one in Settings > Staff accounts.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    DEFAULT_APP_NAME,
    DEFAULT_TAGLINE,
    AcademicYear,
    Attendance,
    Class,
    ClassSubject,
    Currency,
    Exam,
    FeePlan,
    Language,
    Mark,
    Payment,
    Period,
    RoutineSlot,
    SchoolSettings,
    Section,
    Student,
    StudentSubject,
    Subject,
    TeacherSubject,
    User,
)
from .security import hash_password, password_problem
from .services import apply_class_defaults

log = logging.getLogger("madrasa.setup")
NO_PASSWORD = "!no-password-set"  # not a valid hash: nobody can log in until the admin sets a password
DEFAULT_PERIODS = [
    ("1st period", "08:00", "08:45", False),
    ("2nd period", "08:45", "09:30", False),
    ("3rd period", "09:30", "10:15", False),
    ("Tiffin break", "10:15", "10:45", True),
    ("4th period", "10:45", "11:30", False),
    ("5th period", "11:30", "12:15", False),
    ("6th period", "12:15", "13:00", False),
]
# username, full name, (class prefix, subjects) the sample teacher is assigned to
DEMO_TEACHERS = [
    ("demo.rahima", "Rahima Khatun", [("Grade", ["Bangla", "English"])]),
    ("demo.karim", "Abdul Karim", [("Grade", ["Math", "Science"])]),
    ("demo.yusuf", "Maulana Yusuf Ali", [("Hifz", ["Quran (Hifz)", "Tajweed"])]),
    ("demo.abdullah", "Hafiz Abdullah", [("Hifz", ["Arabic", "Islamic Studies"]), ("Grade", ["Islamic Studies"])]),
]
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")

GRADE_SUBJECTS = ["Bangla", "English", "Math", "Science", "Islamic Studies"]
HIFZ_SUBJECTS = ["Quran (Hifz)", "Tajweed", "Arabic", "Islamic Studies"]
ALL_SUBJECTS = [
    ("Bangla", "BAN"),
    ("English", "ENG"),
    ("Math", "MATH"),
    ("Science", "SCI"),
    ("Islamic Studies", "ISL"),
    ("Quran (Hifz)", "QUR"),
    ("Tajweed", "TAJ"),
    ("Arabic", "ARB"),
]


def _backfill_student_subjects(db: Session) -> None:
    """v1.0 stored marks without subject assignments, so results looked empty. Repair that."""
    assigned = {(r.student_id, r.subject_id) for r in db.scalars(select(StudentSubject)).all()}
    for m in db.scalars(select(Mark)).all():
        key = (m.student_id, m.subject_id)
        if key not in assigned and m.student_id and m.subject_id:
            db.add(StudentSubject(student_id=m.student_id, subject_id=m.subject_id, is_active=True))
            assigned.add(key)
    db.commit()


def _fill_nulls(db: Session) -> None:
    for s in db.scalars(select(SchoolSettings)).all():
        s.name = s.name or DEFAULT_APP_NAME
        s.grading_scale = s.grading_scale or "standard"
        s.currency = s.currency or "৳"
    for subj in db.scalars(select(Subject)).all():
        if subj.max_marks is None:
            subj.max_marks = 100
        if subj.credits is None:
            subj.credits = 3.0
        if subj.is_active is None:
            subj.is_active = True
    for p in db.scalars(select(Payment).where(Payment.fee_month.is_(None))).all():
        p.fee_month = (p.date or "")[:7] or None
        p.is_void = bool(p.is_void)
    for e in db.scalars(select(Exam).where(Exam.is_published.is_(None))).all():
        e.is_published = True
    db.commit()


def seed(db: Session, demo: bool | None = None, default_periods: bool | None = None) -> None:
    """Fill a new database. ``default_periods``: add the standard school day (default: only for a new
    database; the app also passes True when an older database gets the routine tables for the first time)."""
    demo = settings.seed_demo_data if demo is None else demo

    if not db.scalars(select(SchoolSettings)).first():
        db.add(
            SchoolSettings(
                name=DEFAULT_APP_NAME,
                tagline=DEFAULT_TAGLINE,
                address="Dhaka, Bangladesh",
                grading_scale="standard",
                currency="৳",
            )
        )
        db.commit()

    bootstrap_admin(db)
    seed_currencies_and_languages(db)

    if not db.scalars(select(AcademicYear)).first():
        db.add(AcademicYear(name=str(date.today().year), is_current=True))
        db.commit()

    first_run = not db.scalars(select(Class)).first()
    if first_run:
        db.add_all([Class(name=f"Grade {i}", order=i) for i in range(1, 11)])
        db.add_all([Class(name=f"Hifz Level {i}", order=100 + i) for i in range(1, 11)])
        db.commit()
        for c in db.scalars(select(Class)).all():
            db.add(Section(name="A", class_id=c.id))
            if c.name.startswith("Grade"):
                db.add(Section(name="B", class_id=c.id))
            db.add(
                FeePlan(class_id=c.id, fee_head="Monthly Tuition", amount=1500 if c.name.startswith("Grade") else 1200)
            )
        db.commit()

    if not db.scalars(select(Subject)).first():
        for name, code in ALL_SUBJECTS:
            db.add(Subject(name=name, code=code, max_marks=100, pass_marks=33, credits=3.0, is_active=True))
        db.commit()

    if not db.scalars(select(ClassSubject)).first():
        by_name = {s.name: s.id for s in db.scalars(select(Subject)).all()}
        for c in db.scalars(select(Class)).all():
            names = HIFZ_SUBJECTS if c.name.startswith("Hifz") else GRADE_SUBJECTS if c.name.startswith("Grade") else []
            for n in names:
                if n in by_name:
                    db.add(ClassSubject(class_id=c.id, subject_id=by_name[n]))
        db.commit()

    if (first_run if default_periods is None else default_periods) and not db.scalars(select(Period)).first():
        for i, (name, start, end, is_break) in enumerate(DEFAULT_PERIODS, start=1):
            db.add(Period(name=name, start_time=start, end_time=end, is_break=is_break, order=i))
        db.commit()

    if first_run and demo:
        _seed_demo(db)

    _fill_nulls(db)
    _backfill_student_subjects(db)


# 1.0.5: starting currencies (rate = value of 1 unit of the default currency; example rates, edit them in
# Settings > Currencies) and the built-in interface languages.
DEFAULT_CURRENCIES = [
    ("BDT", "Bangladeshi Taka", "৳", 1.0, 2),
    ("USD", "US Dollar", "$", 0.0082, 2),
    ("SAR", "Saudi Riyal", "SAR", 0.031, 2),
    ("AED", "UAE Dirham", "AED", 0.030, 2),
]


def seed_currencies_and_languages(db: Session) -> None:
    """Idempotent: add the default currencies (the school's current symbol stays the default) and the
    built-in languages English, Bangla and Arabic (RTL) when the tables are empty (new or upgraded DB)."""
    from .i18n import BUILTIN_LANGUAGES

    school = db.scalars(select(SchoolSettings).order_by(SchoolSettings.id)).first()
    if not db.scalars(select(Currency)).first():
        symbol = (school.currency if school else None) or "৳"
        default_code = "BDT" if symbol == "৳" else None
        for code, name, sym, rate, decimals in DEFAULT_CURRENCIES:
            db.add(
                Currency(
                    code=code,
                    name=name,
                    symbol=sym,
                    rate=rate,
                    decimals=decimals,
                    is_active=True,
                    is_default=(code == default_code),
                )
            )
        if default_code is None:  # an older install with another symbol: keep it as the default currency
            db.add(
                Currency(
                    code="CUR",
                    name="School currency",
                    symbol=symbol[:8],
                    rate=1.0,
                    decimals=2,
                    is_active=True,
                    is_default=True,
                )
            )
        db.commit()
    if not db.scalars(select(Language)).first():
        for code, name, native, rtl in BUILTIN_LANGUAGES:
            db.add(
                Language(
                    code=code, name=name, native_name=native, is_rtl=rtl, is_active=True, is_default=(code == "en")
                )
            )
        db.commit()


def admin_exists(db: Session) -> bool:
    q = select(User.id).where(User.role == "admin", User.is_active.is_(True)).limit(1)
    return db.scalars(q).first() is not None


def bootstrap_admin(db: Session) -> User | None:
    """Create the first admin from ADMIN_USERNAME + ADMIN_PASSWORD (headless installs only).

    Does nothing when an admin already exists or when either variable is empty, so normal
    installs show the /setup page instead. An invalid value is logged and skipped.
    """
    username, password = settings.bootstrap_admin_username, settings.bootstrap_admin_password
    if not username or not password or admin_exists(db):
        return None
    problem = None if USERNAME_RE.match(username) else "ADMIN_USERNAME must be 3-64 letters, digits, . _ or -"
    problem = problem or password_problem(password)
    if problem:
        log.warning("Admin bootstrap skipped (%s). Open /setup to create the administrator.", problem)
        return None
    user = User(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        full_name="Administrator",
        must_change_password=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    log.warning("Administrator '%s' created from ADMIN_USERNAME/ADMIN_PASSWORD.", username)
    return user


def _seed_demo(db: Session) -> None:
    year = db.scalars(select(AcademicYear)).first()
    g1 = db.scalars(select(Class).where(Class.name == "Grade 1")).first()
    g5 = db.scalars(select(Class).where(Class.name == "Grade 5")).first()
    h1 = db.scalars(select(Class).where(Class.name == "Hifz Level 1")).first()
    sec = {(s.class_id, s.name): s.id for s in db.scalars(select(Section)).all()}
    this_year = date.today().year
    rows = [
        ("000001", "Ahmed Rahman", "2016-03-15", "Male", g1, "A", 1, "Karim Rahman", "01711111111"),
        ("000002", "Fatima Begum", "2015-07-22", "Female", g1, "A", 2, "Ayesha Begum", "01722222222"),
        ("000003", "Omar Farooq", "2013-09-30", "Male", h1, "A", 1, "Farooq Ahmed", "01755555555"),
        ("000004", "Maryam Akter", "2016-01-05", "Female", g1, "A", 3, "Rahim Uddin", "01733333333"),
        ("000005", "Yusuf Hossain", "2012-11-11", "Male", g5, "A", 1, "Delwar Hossain", "01744444444"),
        ("000006", "Khadija Islam", "2013-04-18", "Female", h1, "A", 2, "Nurul Islam", "01766666666"),
    ]
    students = []
    for code, name, dob, gender, cls, sec_name, roll, guardian, phone in rows:
        s = Student(
            student_id=code,
            admission_no=f"ADM-{this_year}-{code[-3:]}",
            name=name,
            dob=dob,
            gender=gender,
            class_id=cls.id,
            section_id=sec[(cls.id, sec_name)],
            roll_no=roll,
            admission_date=f"{this_year}-01-10",
            status="Active",
            guardian_name=guardian,
            guardian_relation="Father" if gender == "Male" else "Mother",
            guardian_phone=phone,
            address="Dhaka",
        )
        db.add(s)
        students.append(s)
    db.commit()
    for s in students:
        apply_class_defaults(db, s)
    db.commit()

    exam = Exam(
        name="1st Term", academic_year_id=year.id if year else None, exam_date=f"{this_year}-04-15", is_published=True
    )
    db.add(exam)
    db.commit()
    subjects = {s.id: s for s in db.scalars(select(Subject)).all()}
    pattern = [92, 81, 76, 68, 88, 73, 59, 84]
    for i, s in enumerate(students):
        for j, sid in enumerate(
            sorted(
                r.subject_id for r in db.scalars(select(StudentSubject).where(StudentSubject.student_id == s.id)).all()
            )
        ):
            score = pattern[(i * 3 + j) % len(pattern)]
            if s.student_id == "000004" and j == 2:
                score = 28  # one failing subject so the demo shows a "Fail" result
            db.add(
                Mark(
                    student_id=s.id,
                    exam_id=exam.id,
                    subject_id=sid,
                    marks_obtained=score,
                    max_marks=subjects[sid].max_marks,
                    entered_by="admin",
                )
            )
    db.commit()

    today = date.today()
    for back in range(1, 6):
        d = today - timedelta(days=back)
        for i, s in enumerate(students):
            status = "Absent" if (i + back) % 7 == 0 else "Late" if (i + back) % 5 == 0 else "Present"
            db.add(Attendance(student_id=s.id, date=d.isoformat(), status=status, marked_by="teacher"))
    db.commit()

    month = f"{today.year:04d}-{today.month:02d}"
    for n, (s, amount) in enumerate([(students[0], 1500), (students[1], 1500), (students[2], 1200)], start=1):
        p = Payment(
            student_id=s.id,
            amount=amount,
            date=today.isoformat(),
            fee_month=month,
            fee_head="Monthly Tuition",
            method="Cash",
            collected_by="admin",
            is_void=False,
            receipt_no=f"TMP-{n}",
        )
        db.add(p)
        db.flush()
        p.receipt_no = f"RCP-{today.year}-{p.id:05d}"
    db.commit()

    _seed_demo_routine(db, [students[0], students[4], students[2]])


def _seed_demo_routine(db: Session, students: list[Student]) -> None:
    """Sample teachers (disabled, no password), their subject assignments and a full week for 3 sections."""
    subjects = {s.name: s.id for s in db.scalars(select(Subject)).all()}
    classes = list(db.scalars(select(Class)).all())
    teachers: dict[int, list[tuple[int, int]]] = {}
    for username, full_name, groups in DEMO_TEACHERS:
        if db.scalars(select(User).where(User.username == username)).first():
            return  # already there (seed is only run once for demo data)
        u = User(
            username=username,
            password_hash=NO_PASSWORD,
            role="teacher",
            full_name=full_name,
            is_active=False,
            must_change_password=True,
        )
        db.add(u)
        db.flush()
        for prefix, names in groups:
            for c in classes:
                if not c.name.startswith(prefix):
                    continue
                for n in names:
                    db.add(TeacherSubject(teacher_id=u.id, class_id=c.id, section_id=None, subject_id=subjects[n]))
                    teachers.setdefault(u.id, []).append((c.id, subjects[n]))
    db.commit()
    by_class_subject = {(cid, sid): tid for tid, pairs in teachers.items() for cid, sid in pairs}
    from .services import class_subject_ids, working_days

    periods = [p for p in db.scalars(select(Period).order_by(Period.order)).all() if not p.is_break]
    sections = [(st.class_id, st.section_id) for st in students]
    # Grade classes first, Hifz last: Hifz can always fall back to its own Quran / Tajweed teacher.
    sections.sort(key=lambda cs: db.get(Class, cs[0]).name.startswith("Hifz"))
    for d_idx, day in enumerate(working_days(db)):
        for p_idx, period in enumerate(periods):
            busy: set[int] = set()
            for offset, (cid, secid) in enumerate(sections):
                subj_ids = sorted(class_subject_ids(db, cid))
                if not subj_ids:
                    continue
                for k in range(len(subj_ids)):
                    sid = subj_ids[(d_idx + p_idx + offset * 2 + k) % len(subj_ids)]
                    tid = by_class_subject.get((cid, sid))
                    if tid and tid not in busy:
                        busy.add(tid)
                        db.add(
                            RoutineSlot(
                                class_id=cid,
                                section_id=secid,
                                day=day,
                                period_id=period.id,
                                subject_id=sid,
                                teacher_id=tid,
                                room=f"Room {101 + offset}",
                            )
                        )
                        break
    db.commit()
