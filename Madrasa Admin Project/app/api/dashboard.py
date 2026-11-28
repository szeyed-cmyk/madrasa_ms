"""Who am I + the staff dashboard.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/me                                              current_user
    GET    /api/dashboard                                       require_staff
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Attendance,
    Class,
    Exam,
    Mark,
    Payment,
    RoutineSlot,
    Student,
    Subject,
    TeacherSubject,
    User,
)
from ..security import (
    current_user,
    require_staff,
)
from ._common import (
    _scoped,
)

router = APIRouter()


# ------------------------------------------------------------------ me / dashboard
@router.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "student_id": user.student_id,
        "phone": user.phone,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    today = date.today()
    active = func.lower(Student.status) == "active"
    cond = services.student_condition(db, user)  # 1.3.0: a teacher's numbers cover only their own classes
    att_q = (
        select(Attendance.status, func.count())
        .join(Student, Student.id == Attendance.student_id)
        .where(Attendance.date == today.isoformat())
    )
    if cond is not None:
        att_q = att_q.where(cond)
    att_rows = db.execute(att_q.group_by(Attendance.status)).all()
    n_classes = (
        len(services.teacher_class_sections(db, user))
        if user.role == "teacher"
        else db.scalar(select(func.count()).select_from(Class)) or 0
    )
    data = {
        "students": db.scalar(_scoped(select(func.count()).select_from(Student).where(active), db, user)) or 0,
        "students_total": db.scalar(_scoped(select(func.count()).select_from(Student), db, user)) or 0,
        "classes": n_classes,
        "subjects": db.scalar(select(func.count()).select_from(Subject).where(Subject.is_active.is_not(False))) or 0,
        "exams": db.scalar(select(func.count()).select_from(Exam)) or 0,
        "attendance_today": {status: count for status, count in att_rows},
        "role": user.role,
        "today": today.isoformat(),
        "today_day": services.day_code(today),
        "is_working_day": services.day_code(today) in services.working_days(db),
        "my_classes_today": services.teacher_today(db, user.id, today),
        "routine_slots": db.scalar(select(func.count()).select_from(RoutineSlot)) or 0,
        "teachers": db.scalar(
            select(func.count()).select_from(User).where(User.role == "teacher", User.is_active.is_(True))
        )
        or 0,
        "activity": _recent_activity(db, user),
    }
    data["attendance_trend"] = _attendance_trend(db, cond, today)
    data["class_breakdown"] = _class_breakdown(db, user)
    if user.role == "teacher":
        data["my_assignments"] = len(
            db.scalars(select(TeacherSubject.id).where(TeacherSubject.teacher_id == user.id)).all()
        )
    if user.role == "admin":
        month = f"{today.year:04d}-{today.month:02d}"
        not_void = Payment.is_void.is_not(True)
        data["collected"] = float(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(not_void)) or 0)
        data["collected_month"] = float(
            db.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(not_void, Payment.date.like(f"{month}-%"))
            )
            or 0
        )
        students = db.scalars(select(Student).where(active)).all()
        data["dues_total"] = round(sum(services.fee_status(db, s, today)["due"] for s in students), 2)
        data["fee_trend"] = _fee_trend(db, today)
        recent = db.scalars(select(Payment).order_by(Payment.id.desc()).limit(5)).all()
        data["recent_payments"] = [services.payment_dict(p, db.get(Student, p.student_id)) for p in recent]
    return data


def _fee_trend(db: Session, today: date, months: int = 6) -> list[dict]:
    """1.0.5 chart: fees collected per calendar month (payment date), oldest first."""
    out = []
    for back in range(months - 1, -1, -1):
        y, m = today.year, today.month - back
        while m < 1:
            y, m = y - 1, m + 12
        key = f"{y:04d}-{m:02d}"
        total = db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.is_void.is_not(True), Payment.date.like(f"{key}-%")
            )
        )
        out.append({"month": key, "total": float(total or 0)})
    return out


def _attendance_trend(db: Session, cond, today: date, days: int = 14) -> list[dict]:
    """1.0.5 chart: present / late / absent per day for the last ``days`` days that have attendance."""
    since = (today - timedelta(days=days * 2)).isoformat()
    q = (
        select(Attendance.date, Attendance.status, func.count())
        .join(Student, Student.id == Attendance.student_id)
        .where(Attendance.date >= since, Attendance.date <= today.isoformat())
    )
    if cond is not None:
        q = q.where(cond)
    per_day: dict[str, dict] = {}
    for day, status, n in db.execute(q.group_by(Attendance.date, Attendance.status)).all():
        row = per_day.setdefault(day, {"date": day, "Present": 0, "Late": 0, "Absent": 0, "Leave": 0})
        row[status] = row.get(status, 0) + n
    rows = [per_day[d] for d in sorted(per_day)][-days:]
    for r in rows:
        total = r["Present"] + r["Late"] + r["Absent"] + r.get("Leave", 0)
        r["rate"] = round(100 * (r["Present"] + r["Late"]) / total, 1) if total else 0
    return rows


def _class_breakdown(db: Session, user: User, limit: int = 6) -> list[dict]:
    """1.0.5 chart: active students per class (largest first; a teacher sees own classes only)."""
    q = (
        select(Class.name, func.count(Student.id))
        .join(Student, Student.class_id == Class.id)
        .where(func.lower(Student.status) == "active")
    )
    cond = services.student_condition(db, user)
    if cond is not None:
        q = q.where(cond)
    rows = db.execute(q.group_by(Class.id, Class.name).order_by(func.count(Student.id).desc())).all()
    return [{"name": name, "count": n} for name, n in rows[:limit]]


def _recent_activity(db: Session, user: User, limit: int = 8) -> list[dict]:
    """Latest things that happened: attendance taken, marks entered, students added, fees collected."""
    items: list[dict] = []
    mine = user.role != "admin"  # 1.3.0: teachers see only their own attendance / marks activity
    att_q = select(Attendance.date, Attendance.marked_by, func.count(), func.max(Attendance.updated_at))
    if mine:
        att_q = att_q.where(Attendance.marked_by == user.username)
    att = db.execute(
        att_q.group_by(Attendance.date, Attendance.marked_by)
        .order_by(func.max(Attendance.updated_at).desc())
        .limit(limit)
    ).all()
    for day, who, n, when in att:
        items.append(
            {
                "kind": "attendance",
                "when": (when.isoformat(timespec="minutes") + "Z" if when else day),
                "text": f"Attendance for {day}: {n} student(s)",
                "by": who or "",
            }
        )
    mk_q = select(Mark.exam_id, Mark.entered_by, func.count(), func.max(Mark.updated_at))
    if mine:
        mk_q = mk_q.where(Mark.entered_by == user.username)
    marks = db.execute(
        mk_q.group_by(Mark.exam_id, Mark.entered_by).order_by(func.max(Mark.updated_at).desc()).limit(limit)
    ).all()
    exams = {e.id: e.name for e in db.scalars(select(Exam)).all()}
    for exam_id, who, n, when in marks:
        items.append(
            {
                "kind": "marks",
                "when": when.isoformat(timespec="minutes") + "Z" if when else "",
                "text": f"{n} mark(s) in {exams.get(exam_id, 'an exam')}",
                "by": who or "",
            }
        )
    for st in db.scalars(_scoped(select(Student), db, user).order_by(Student.id.desc()).limit(limit)).all():
        items.append(
            {
                "kind": "student",
                "when": st.created_at.isoformat(timespec="minutes") + "Z" if st.created_at else "",
                "text": f"Student added: {st.name}",
                "by": "",
            }
        )
    if user.role == "admin":
        for p in db.scalars(select(Payment).order_by(Payment.id.desc()).limit(limit)).all():
            st = db.get(Student, p.student_id)
            items.append(
                {
                    "kind": "payment",
                    "when": p.date or "",
                    "text": f"Receipt {p.receipt_no}: {st.name if st else ''}" + (" (void)" if p.is_void else ""),
                    "amount": p.amount,
                    "by": p.collected_by or "",
                }
            )
    items.sort(key=lambda x: x["when"], reverse=True)
    return items[:limit]
