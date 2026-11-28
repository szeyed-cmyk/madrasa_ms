"""Business logic shared by the API, the print pages and the tests."""

from __future__ import annotations

import re
import secrets
from datetime import date

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from . import grading
from .models import (
    ALL_DAYS,
    DEFAULT_APP_NAME,
    DEFAULT_TAGLINE,
    DEFAULT_WORKING_DAYS,
    AcademicYear,
    Attendance,
    Class,
    ClassSubject,
    Exam,
    FeePlan,
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

STUDENT_STATUSES = ["Active", "Inactive", "Transferred", "Graduated", "Archived"]
ATTENDANCE_STATUSES = ["Present", "Absent", "Late", "Leave"]
PAYMENT_METHODS = ["Cash", "bKash", "Nagad", "Rocket", "Bank", "Card", "Other", "Stripe", "PayPal", "SSLCommerz"]
PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{5,18}$")


def school(db: Session) -> SchoolSettings:
    s = db.scalars(select(SchoolSettings).order_by(SchoolSettings.id)).first()
    if not s:
        s = SchoolSettings(name=DEFAULT_APP_NAME, tagline=DEFAULT_TAGLINE, grading_scale="standard", currency="৳")
        db.add(s)
        db.commit()
    return s


def current_year(db: Session) -> AcademicYear | None:
    year = db.scalars(
        select(AcademicYear).where(AcademicYear.is_current.is_(True)).order_by(AcademicYear.id.desc())
    ).first()
    return year or db.scalars(select(AcademicYear).order_by(AcademicYear.id.desc())).first()


def next_student_code(db: Session) -> str:
    codes = db.scalars(select(Student.student_id)).all()
    highest = max((int(c) for c in codes if c and c.isdigit()), default=0)
    candidate = highest + 1
    existing = set(codes)
    while str(candidate).zfill(6) in existing:
        candidate += 1
    if candidate > 999_999:
        raise ValueError("Student ID space exhausted")
    return str(candidate).zfill(6)


def class_maps(db: Session):
    classes = {c.id: c for c in db.scalars(select(Class)).all()}
    sections = {s.id: s for s in db.scalars(select(Section)).all()}
    return classes, sections


def student_dict(s: Student, classes: dict, sections: dict) -> dict:
    cls = classes.get(s.class_id)
    sec = sections.get(s.section_id)
    return {
        "id": s.id,
        "student_id": s.student_id or str(s.id).zfill(6),
        "admission_no": s.admission_no,
        "name": s.name,
        "dob": s.dob,
        "gender": s.gender,
        "class_id": s.class_id,
        "section_id": s.section_id,
        "class_name": cls.name if cls else "",
        "section_name": sec.name if sec else "",
        "roll_no": s.roll_no,
        "admission_date": s.admission_date,
        "status": s.status or "Active",
        "address": s.address,
        "guardian_name": s.guardian_name,
        "guardian_relation": s.guardian_relation,
        "guardian_phone": s.guardian_phone,
        "guardian_address": s.guardian_address,
        "notes": s.notes,
        "photo": s.photo,
    }


# ------------------------------------------------------------------ subjects
def class_subject_ids(db: Session, class_id: int) -> list[int]:
    return list(db.scalars(select(ClassSubject.subject_id).where(ClassSubject.class_id == class_id)).all())


def student_subject_ids(db: Session, student_pk: int) -> list[int]:
    return list(
        db.scalars(
            select(StudentSubject.subject_id).where(
                StudentSubject.student_id == student_pk, StudentSubject.is_active.is_not(False)
            )
        ).all()
    )


def assign_subject(db: Session, student_pk: int, subject_id: int) -> bool:
    row = db.scalars(
        select(StudentSubject).where(StudentSubject.student_id == student_pk, StudentSubject.subject_id == subject_id)
    ).first()
    if row:
        if row.is_active is False:
            row.is_active = True
            return True
        return False
    db.add(StudentSubject(student_id=student_pk, subject_id=subject_id, is_active=True))
    return True


def apply_class_defaults(db: Session, student: Student) -> int:
    added = 0
    for sid in class_subject_ids(db, student.class_id):
        if assign_subject(db, student.id, sid):
            added += 1
    return added


def student_subjects(db: Session, student_pk: int) -> list[Subject]:
    ids = student_subject_ids(db, student_pk)
    if not ids:
        return []
    return list(db.scalars(select(Subject).where(Subject.id.in_(ids)).order_by(Subject.name)).all())


# ------------------------------------------------------------------ results
def default_exam(db: Session, student_pk: int | None, published_only: bool = False) -> Exam | None:
    """Latest exam that has marks for this student; otherwise simply the latest exam."""
    q = select(Exam)
    if published_only:
        q = q.where(Exam.is_published.is_(True))
    if student_pk:
        with_marks = db.scalars(
            q.where(Exam.id.in_(select(Mark.exam_id).where(Mark.student_id == student_pk))).order_by(Exam.id.desc())
        ).first()
        if with_marks:
            return with_marks
    return db.scalars(q.order_by(Exam.id.desc())).first()


def student_result(db: Session, student: Student, exam: Exam | None, scale_name: str) -> dict:
    subjects = student_subjects(db, student.id)
    marks = {}
    if exam:
        for m in db.scalars(select(Mark).where(Mark.student_id == student.id, Mark.exam_id == exam.id)).all():
            marks[m.subject_id] = m
    rows = []
    for subj in subjects:
        m = marks.get(subj.id)
        obtained = m.marks_obtained if m else None
        max_marks = (m.max_marks if m and m.max_marks else None) or subj.max_marks or 100
        letter, gp, passed = grading.subject_grade(obtained, max_marks, subj.pass_marks, scale_name)
        rows.append(
            {
                "subject_id": subj.id,
                "subject": subj.name,
                "code": subj.code,
                "marks": obtained,
                "max": max_marks,
                "pass_marks": subj.pass_marks,
                "credits": subj.credits if subj.credits is not None else 3.0,
                "grade": letter,
                "grade_point": gp,
                "passed": passed,
            }
        )
    summary = grading.summarize(rows, scale_name)
    return {"subjects": rows, **summary}


def class_results(db: Session, exam: Exam, class_id: int | None, section_id: int | None, scale_name: str) -> list[dict]:
    q = select(Student).where(func.lower(Student.status) != "archived")
    if class_id:
        q = q.where(Student.class_id == class_id)
    if section_id:
        q = q.where(Student.section_id == section_id)
    students = db.scalars(q.order_by(Student.roll_no, Student.name)).all()
    classes, sections = class_maps(db)
    results = []
    for s in students:
        r = student_result(db, s, exam, scale_name)
        info = student_dict(s, classes, sections)
        results.append(
            {
                **r,
                "student": info,
                "student_pk": s.id,
                "student_name": s.name,
                "student_code": info["student_id"],
                "admission_no": s.admission_no,
                "class_name": info["class_name"],
                "section_name": info["section_name"],
            }
        )
    # merit position among students who passed, by GPA then total
    ranked = sorted(
        (r for r in results if r["status"] == "Pass"),
        key=lambda r: (-r["gpa"], -r["total_obtained"]),
    )
    position = {}
    for idx, r in enumerate(ranked, start=1):
        position[r["student_pk"]] = idx
    for r in results:
        r["position"] = position.get(r["student_pk"])
    return results


# ------------------------------------------------------------------ fees
def monthly_fee(db: Session, class_id: int) -> float:
    total = db.scalar(select(func.coalesce(func.sum(FeePlan.amount), 0)).where(FeePlan.class_id == class_id))
    return float(total or 0)


def months_between(start: date, end: date) -> list[str]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def fee_status(db: Session, student: Student, today: date | None = None) -> dict:
    """Dues for the current calendar year: months since January (or admission) x monthly fee - payments."""
    today = today or date.today()
    start = date(today.year, 1, 1)
    try:
        adm = date.fromisoformat(student.admission_date) if student.admission_date else None
    except ValueError:
        adm = None
    if adm and adm > start:
        start = date(adm.year, adm.month, 1)
    months = months_between(start, today) if start <= today else []
    per_month = monthly_fee(db, student.class_id)
    expected = per_month * len(months)
    payments = db.scalars(
        select(Payment)
        .where(Payment.student_id == student.id, Payment.is_void.is_not(True))
        .order_by(Payment.id.desc())
    ).all()
    year_prefix = f"{today.year:04d}-"
    paid_year = sum(
        p.amount or 0 for p in payments if ((p.fee_month or (p.date or "")[:7]) or "").startswith(year_prefix)
    )
    due = round(expected - paid_year, 2)
    return {
        "monthly_fee": per_month,
        "months": len(months),
        "expected": round(expected, 2),
        "paid": round(paid_year, 2),
        "due": max(due, 0.0),
        "advance": max(-due, 0.0),
        "paid_all_time": round(sum(p.amount or 0 for p in payments), 2),
    }


def payment_dict(p: Payment, student: Student | None) -> dict:
    return {
        "id": p.id,
        "receipt_no": p.receipt_no,
        "student_id": p.student_id,
        "student_name": student.name if student else "",
        "admission_no": student.admission_no if student else "",
        "amount": p.amount,
        "date": p.date,
        "fee_month": p.fee_month,
        "fee_head": p.fee_head,
        "method": p.method,
        "note": p.note,
        "collected_by": p.collected_by,
        "is_void": bool(p.is_void),
    }


# ------------------------------------------------------------------ attendance
def attendance_summary(db: Session, student_pk: int, month: str | None = None) -> dict:
    q = select(Attendance).where(Attendance.student_id == student_pk)
    if month:
        q = q.where(Attendance.date.like(f"{month}-%"))
    rows = db.scalars(q.order_by(Attendance.date.desc())).all()
    counts = {s: 0 for s in ATTENDANCE_STATUSES}
    for r in rows:
        if r.status in counts:
            counts[r.status] += 1
    total = len(rows)
    attended = counts["Present"] + counts["Late"]
    return {
        "counts": counts,
        "total": total,
        "percentage": round(attended / total * 100, 1) if total else None,
        "recent": [{"date": r.date, "status": r.status, "marked_by": r.marked_by} for r in rows[:30]],
    }


# ------------------------------------------------------------------ routine & teacher assignments
DAY_NAMES = {
    "Sat": "Saturday",
    "Sun": "Sunday",
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
}
_PY_WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # date.weekday() -> day code


def day_code(d: date | None = None) -> str:
    return _PY_WEEKDAY[(d or date.today()).weekday()]


def working_days(db: Session) -> list[str]:
    raw = school(db).working_days or DEFAULT_WORKING_DAYS
    days = [x.strip() for x in raw.split(",") if x.strip() in ALL_DAYS]
    return [d for d in ALL_DAYS if d in days] or DEFAULT_WORKING_DAYS.split(",")


def periods(db: Session) -> list[Period]:
    return list(db.scalars(select(Period).order_by(Period.order, Period.start_time, Period.id)).all())


def period_dict(p: Period) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "start_time": p.start_time,
        "end_time": p.end_time,
        "is_break": bool(p.is_break),
        "order": p.order or 0,
    }


def teacher_name(u: User | None) -> str:
    return (u.full_name or u.username) if u else ""


def assigned_teacher(db: Session, class_id: int, section_id: int | None, subject_id: int) -> TeacherSubject | None:
    """The teacher assigned to a subject for a section; a section-specific row wins over a class-wide one."""
    rows = db.scalars(
        select(TeacherSubject).where(TeacherSubject.class_id == class_id, TeacherSubject.subject_id == subject_id)
    ).all()
    specific = [r for r in rows if section_id and r.section_id == section_id]
    general = [r for r in rows if r.section_id is None]
    return (specific or general or [None])[0]


def is_assigned(db: Session, teacher_id: int, class_id: int, section_id: int | None, subject_id: int) -> bool:
    q = select(TeacherSubject.id).where(
        TeacherSubject.teacher_id == teacher_id,
        TeacherSubject.class_id == class_id,
        TeacherSubject.subject_id == subject_id,
    )
    rows = db.scalars(q).all()
    if not rows:
        return False
    if section_id is None:
        return True
    return bool(
        db.scalars(q.where((TeacherSubject.section_id.is_(None)) | (TeacherSubject.section_id == section_id))).first()
    )


def teacher_subject_ids(db: Session, teacher: User, class_id: int, section_id: int | None) -> set[int]:
    """Subjects this teacher may enter marks for in a class (and section). Admins: every subject."""
    q = select(TeacherSubject.subject_id).where(
        TeacherSubject.teacher_id == teacher.id, TeacherSubject.class_id == class_id
    )
    if section_id:
        q = q.where((TeacherSubject.section_id.is_(None)) | (TeacherSubject.section_id == section_id))
    return set(db.scalars(q).all())


def can_enter_marks(db: Session, user: User, student: Student, subject_id: int) -> bool:
    if user.role == "admin":
        return True
    if user.role != "teacher":
        return False
    return subject_id in teacher_subject_ids(db, user, student.class_id, student.section_id)


# ------------------------------------------------------------------ 1.3.0: role scope (who may see which students)
def temp_password() -> str:
    """Readable temporary password for a new/reset login: 10 chars, no look-alike characters (0/O, 1/l/I)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(10))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def teacher_scope(db: Session, teacher_id: int) -> set[tuple[int, int | None]]:
    """(class_id, section_id) pairs a teacher works in: subject assignments plus their routine periods.

    section_id None means every section of the class (a class-wide assignment).
    """
    pairs: set[tuple[int, int | None]] = set(
        db.execute(
            select(TeacherSubject.class_id, TeacherSubject.section_id).where(TeacherSubject.teacher_id == teacher_id)
        ).all()
    )
    pairs |= set(
        db.execute(
            select(RoutineSlot.class_id, RoutineSlot.section_id).where(RoutineSlot.teacher_id == teacher_id)
        ).all()
    )
    whole = {c for c, s in pairs if s is None}
    return {(c, s) for c, s in pairs if s is None or c not in whole}


def scope_condition(scope: set[tuple[int, int | None]]):
    """SQL condition on Student for a teacher scope (false() when the teacher has no classes yet)."""
    conds = [
        Student.class_id == c if s is None else and_(Student.class_id == c, Student.section_id == s) for c, s in scope
    ]
    return or_(*conds) if conds else false()


def student_condition(db: Session, user: User):
    """Extra WHERE for student lists: None for admins (everything), the teacher's classes for teachers."""
    if user.role == "admin":
        return None
    if user.role == "teacher":
        return scope_condition(teacher_scope(db, user.id))
    return false()


def in_scope(scope: set[tuple[int, int | None]], class_id: int | None, section_id: int | None) -> bool:
    return (class_id, None) in scope or (class_id, section_id) in scope


def can_view_student(db: Session, user: User, student: Student | None) -> bool:
    """Admin: every student. Teacher: students of the classes/sections they teach. Student: only themselves."""
    if student is None:
        return False
    if user.role == "admin":
        return True
    if user.role == "teacher":
        return in_scope(teacher_scope(db, user.id), student.class_id, student.section_id)
    return user.role == "student" and user.student_id == student.id


def teacher_class_sections(db: Session, user: User) -> dict[int, set[int] | None]:
    """For class pickers: class_id -> allowed section ids (None = every section)."""
    out: dict[int, set[int] | None] = {}
    for c, s in teacher_scope(db, user.id):
        if s is None:
            out[c] = None
        elif out.get(c, set()) is not None:
            out.setdefault(c, set()).add(s)
    return out


def slot_dict(slot: RoutineSlot, subjects: dict, users: dict, classes: dict, sections: dict, db: Session) -> dict:
    subj = subjects.get(slot.subject_id)
    teacher = users.get(slot.teacher_id)
    cls, sec = classes.get(slot.class_id), sections.get(slot.section_id)
    warning = None
    if slot.teacher_id and not is_assigned(db, slot.teacher_id, slot.class_id, slot.section_id, slot.subject_id):
        warning = f"{teacher_name(teacher)} is no longer assigned to {subj.name if subj else 'this subject'}."
    return {
        "id": slot.id,
        "class_id": slot.class_id,
        "section_id": slot.section_id,
        "class_name": cls.name if cls else "",
        "section_name": sec.name if sec else "",
        "day": slot.day,
        "period_id": slot.period_id,
        "subject_id": slot.subject_id,
        "subject_name": subj.name if subj else "",
        "subject_code": subj.code if subj else "",
        "teacher_id": slot.teacher_id,
        "teacher_name": teacher_name(teacher),
        "room": slot.room or "",
        "warning": warning,
    }


def _lookups(db: Session):
    subjects = {s.id: s for s in db.scalars(select(Subject)).all()}
    users = {u.id: u for u in db.scalars(select(User).where(User.role != "student")).all()}
    classes, sections = class_maps(db)
    return subjects, users, classes, sections


def routine_slots(db: Session, *, section_id: int | None = None, teacher_id: int | None = None) -> list[dict]:
    q = select(RoutineSlot)
    if section_id is not None:
        q = q.where(RoutineSlot.section_id == section_id)
    if teacher_id is not None:
        q = q.where(RoutineSlot.teacher_id == teacher_id)
    subjects, users, classes, sections = _lookups(db)
    order = {d: i for i, d in enumerate(ALL_DAYS)}
    per = {p.id: (p.order or 0, p.start_time) for p in periods(db)}
    rows = sorted(db.scalars(q).all(), key=lambda r: (order.get(r.day, 9), per.get(r.period_id, (0, ""))))
    return [slot_dict(r, subjects, users, classes, sections, db) for r in rows]


def teacher_today(db: Session, teacher_id: int, today: date | None = None) -> list[dict]:
    code = day_code(today)
    if code not in working_days(db):
        return []
    per = {p.id: p for p in periods(db)}
    out = []
    for s in routine_slots(db, teacher_id=teacher_id):
        if s["day"] == code and s["period_id"] in per:
            p = per[s["period_id"]]
            out.append({**s, "period_name": p.name, "start_time": p.start_time, "end_time": p.end_time})
    return out


# ------------------------------------------------------------------ 1.0.2: login accounts (teachers, students)
# The API routes only parse the request and shape the response; the rules live here:
#   * a typed password must pass security.password_problem(), otherwise a temporary one is generated;
#   * every create / reset sets must_change_password=True (the owner picks their own password at first login);
#   * only the salted hash is stored; the plain temporary password is returned ONCE in the API response
#     (served with Cache-Control: no-store) and is never written to the database or to a log.
USERNAME_FULL_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")


class AccountError(ValueError):
    """A rule for login accounts was broken; the API turns it into HTTP 400 with this message."""


def choose_password(password: str | None) -> tuple[str, str | None]:
    """Returns (password, generated-or-None). A typed password must pass the password rules."""
    from .security import password_problem

    if password:
        problem = password_problem(password)
        if problem:
            raise AccountError(problem)
        return password, None
    pw = temp_password()
    return pw, pw


def issue_password(user: User, password: str, force_change: bool = True) -> None:
    """Store a new password hash (this also ends the account's open sessions)."""
    from .security import hash_password

    user.password_hash = hash_password(password)
    user.must_change_password = force_change


def username_taken(db: Session, username: str, except_id: int | None = None) -> bool:
    q = select(User.id).where(func.lower(User.username) == username.lower())
    if except_id:
        q = q.where(User.id != except_id)
    return db.scalars(q).first() is not None


def create_teacher_account(
    db: Session, username: str, full_name: str, phone: str | None, photo: str | None, password: str | None
) -> tuple[User, str | None]:
    if username_taken(db, username):
        raise AccountError(f"The username '{username}' is already taken. Choose another one.")
    password, generated = choose_password(password)
    u = User(username=username, full_name=full_name, phone=phone, photo=photo, role="teacher", is_active=True)
    issue_password(u, password)
    db.add(u)
    db.commit()
    return u, generated


def reset_teacher_password(user: User, password: str | None) -> str | None:
    had_password = "$" in (user.password_hash or "")
    password, generated = choose_password(password)
    issue_password(user, password)
    if not had_password:
        user.is_active = True  # sample teachers start disabled without a password
    return generated


def save_student_login(
    db: Session, student: Student, username: str | None, password: str | None
) -> tuple[User, str | None]:
    """Create or reset the login of one student. A reset keeps the username unless a new one is typed."""
    existing = db.scalars(select(User).where(User.student_id == student.id)).first()
    username = username or (existing.username if existing else None) or student.student_id or ""
    if not USERNAME_FULL_RE.match(username):
        raise AccountError("Username must be 3-64 letters, digits, dot, dash or underscore.")
    if username_taken(db, username, except_id=existing.id if existing else None):
        raise AccountError("That username is already taken.")
    password, generated = choose_password(password)
    u = existing or User(role="student", student_id=student.id)
    if existing is None:
        db.add(u)
    u.username, u.full_name, u.is_active = username, student.name, True
    issue_password(u, password)
    db.commit()
    return u, generated


def bulk_student_logins(db: Session, students: list[Student], reset_existing: bool) -> dict:
    """Logins (username = 6-digit student ID) for many students; temporary passwords returned once."""
    classes, sections = class_maps(db)
    creds, skipped = [], []
    created = reset = 0
    for s in students:
        u = db.scalars(select(User).where(User.student_id == s.id)).first()
        if u and not reset_existing:
            continue
        pw = temp_password()
        if u:
            u.is_active = True
            reset += 1
        else:
            username = s.student_id or ""
            if not USERNAME_FULL_RE.match(username) or username_taken(db, username):
                skipped.append(f"{s.name}: username '{username}' is not available; create this login on its own.")
                continue
            u = User(username=username, role="student", full_name=s.name, student_id=s.id, is_active=True)
            db.add(u)
            created += 1
        issue_password(u, pw)
        d = student_dict(s, classes, sections)
        creds.append(
            {
                "student_pk": s.id,
                "student_id": s.student_id,
                "name": s.name,
                "roll_no": s.roll_no,
                "class_name": d.get("class_name", ""),
                "section_name": d.get("section_name", ""),
                "username": u.username,
                "password": pw,
            }
        )
    db.commit()
    return {"created": created, "reset": reset, "skipped": skipped, "credentials": creds}
