"""Daily attendance and the monthly attendance report.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/attendance                                      require_staff
    POST   /api/attendance                                      require_staff
    GET    /api/attendance/report                               require_staff
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Attendance,
    Student,
    User,
    utcnow,
)
from ..schemas import (
    AttendanceIn,
)
from ..security import (
    require_staff,
)
from ._common import (
    _check_class_scope,
    _scoped,
)

router = APIRouter()


# ------------------------------------------------------------------ attendance
@router.get("/attendance")
def get_attendance(
    date_: str = Query(alias="date"),
    class_id: int = 0,
    section_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    try:
        day = date.fromisoformat(date_).isoformat()
    except ValueError as exc:
        raise HTTPException(400, "Use a date in YYYY-MM-DD format") from exc
    if class_id:
        _check_class_scope(db, user, class_id, section_id)
    q = _scoped(select(Student).where(func.lower(Student.status) == "active"), db, user)
    if class_id:
        q = q.where(Student.class_id == class_id)
    if section_id:
        q = q.where(Student.section_id == section_id)
    students = db.scalars(q.order_by(Student.roll_no, Student.name)).all()
    ids = [s.id for s in students]
    saved = {}
    if ids:
        saved = {
            a.student_id: a.status
            for a in db.scalars(select(Attendance).where(Attendance.date == day, Attendance.student_id.in_(ids))).all()
        }
    classes, sections = services.class_maps(db)
    return {
        "date": day,
        "already_saved": bool(saved),
        "students": [
            {
                "id": s.id,
                "name": s.name,
                "student_id": s.student_id,
                "roll_no": s.roll_no,
                "class_name": classes[s.class_id].name if s.class_id in classes else "",
                "section_name": sections[s.section_id].name if s.section_id in sections else "",
                "guardian_phone": s.guardian_phone,
                "status": saved.get(s.id),
                "saved": s.id in saved,
            }
            for s in students
        ],
    }


@router.post("/attendance")
def save_attendance(data: AttendanceIn, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    ids = [r.student_id for r in data.records]
    found = set(db.scalars(select(Student.id).where(Student.id.in_(ids))).all()) if ids else set()
    missing = set(ids) - found
    if missing:
        raise HTTPException(404, f"Student(s) not found: {sorted(missing)}")
    if user.role != "admin" and ids:
        allowed = set(db.scalars(_scoped(select(Student.id).where(Student.id.in_(ids)), db, user)).all())
        if set(ids) - allowed:
            raise HTTPException(403, "You can only take attendance for students of the classes you teach.")
    for r in data.records:
        rows = db.scalars(
            select(Attendance).where(Attendance.student_id == r.student_id, Attendance.date == data.date)
        ).all()
        if rows:
            rows[0].status, rows[0].marked_by, rows[0].updated_at = r.status, user.username, utcnow()
            for extra in rows[1:]:
                db.delete(extra)
        else:
            db.add(Attendance(student_id=r.student_id, date=data.date, status=r.status, marked_by=user.username))
    db.commit()
    return {"ok": True, "saved": len(data.records)}


@router.get("/attendance/report")
def attendance_report(
    month: str, class_id: int = 0, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(400, "Month must be YYYY-MM")
    if class_id:
        _check_class_scope(db, user, class_id)
    q = _scoped(select(Student).where(func.lower(Student.status) == "active"), db, user)
    if class_id:
        q = q.where(Student.class_id == class_id)
    rows = []
    for s in db.scalars(q.order_by(Student.roll_no, Student.name)).all():
        summ = services.attendance_summary(db, s.id, month)
        rows.append(
            {
                "id": s.id,
                "name": s.name,
                "student_id": s.student_id,
                **summ["counts"],
                "total": summ["total"],
                "percentage": summ["percentage"],
            }
        )
    return {"month": month, "rows": rows}
