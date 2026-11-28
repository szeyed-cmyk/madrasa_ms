"""Teachers list, subject assignments, periods and the class routine (timetable).

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/teachers                                        require_staff
    GET    /api/assignments                                     require_staff
    POST   /api/assignments                                     require_admin
    DELETE /api/assignments/{assignment_id}                     require_admin
    GET    /api/periods                                         current_user
    POST   /api/periods                                         require_admin
    PUT    /api/periods/{period_id}                             require_admin
    DELETE /api/periods/{period_id}                             require_admin
    GET    /api/routine                                         current_user
    GET    /api/my/routine                                      require_staff
    PUT    /api/routine/slot                                    require_admin
    DELETE /api/routine/slot/{slot_id}                          require_admin
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Class,
    Period,
    RoutineSlot,
    Section,
    Student,
    Subject,
    TeacherSubject,
    User,
)
from ..schemas import (
    AssignmentIn,
    PeriodIn,
    SlotIn,
)
from ..security import (
    current_user,
    require_admin,
    require_staff,
)
from ._common import (
    _assignment_dict,
    _check_class_scope,
    _get,
)

router = APIRouter()


# ------------------------------------------------------------------ teachers, assignments, periods, routine
@router.get("/teachers")
def list_teachers(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """Staff who can be put on the routine (teachers and admins). A teacher only gets their own entry."""
    q = select(User).where(User.role.in_(("teacher", "admin")))
    if user.role != "admin":
        q = q.where(User.id == user.id)
    rows = db.scalars(q.order_by(User.role.desc(), User.full_name)).all()
    return [
        {
            "id": u.id,
            "name": services.teacher_name(u),
            "username": u.username,
            "role": u.role,
            "is_active": bool(u.is_active),
        }
        for u in rows
    ]


@router.get("/assignments")
def list_assignments(
    class_id: int = 0, teacher_id: int = 0, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    q = select(TeacherSubject)
    if user.role != "admin":  # 1.3.0: a teacher sees only their own assignments
        teacher_id = user.id
    if class_id:
        q = q.where(TeacherSubject.class_id == class_id)
    if teacher_id:
        q = q.where(TeacherSubject.teacher_id == teacher_id)
    subjects, users, classes, sections = services._lookups(db)
    rows = db.scalars(q).all()
    out = [_assignment_dict(a, users, subjects, classes, sections) for a in rows]
    out.sort(
        key=lambda r: (
            classes[r["class_id"]].order if r["class_id"] in classes else 0,
            r["section_name"],
            r["subject_name"],
        )
    )
    return out


@router.post("/assignments", status_code=201)
def save_assignment(data: AssignmentIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Assign a teacher to a subject in a class (or one section). Replaces the teacher already assigned there."""
    teacher = _get(db, User, data.teacher_id, "Teacher")
    if teacher.role not in ("teacher", "admin"):
        raise HTTPException(400, "Only teacher or admin accounts can be assigned to subjects.")
    _get(db, Class, data.class_id, "Class")
    _get(db, Subject, data.subject_id, "Subject")
    if data.section_id:
        sec = _get(db, Section, data.section_id, "Section")
        if sec.class_id != data.class_id:
            raise HTTPException(400, "That section does not belong to the selected class.")
    q = select(TeacherSubject).where(
        TeacherSubject.class_id == data.class_id,
        TeacherSubject.subject_id == data.subject_id,
        TeacherSubject.section_id.is_(None)
        if data.section_id is None
        else TeacherSubject.section_id == data.section_id,
    )
    row = db.scalars(q).first()
    replaced = None
    if row:
        if row.teacher_id != teacher.id:
            replaced = services.teacher_name(db.get(User, row.teacher_id))
        row.teacher_id = teacher.id
    else:
        row = TeacherSubject(
            teacher_id=teacher.id, class_id=data.class_id, section_id=data.section_id, subject_id=data.subject_id
        )
        db.add(row)
    db.commit()
    return {"id": row.id, "replaced": replaced}


@router.delete("/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.delete(_get(db, TeacherSubject, assignment_id, "Assignment"))
    db.commit()
    return {"ok": True}


@router.get("/periods")
def list_periods(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [services.period_dict(p) for p in services.periods(db)]


def _check_period(db: Session, data: PeriodIn, period_id: int | None) -> None:
    for p in services.periods(db):
        if p.id != period_id and p.start_time < data.end_time and data.start_time < p.end_time:
            raise HTTPException(400, f"The time overlaps with {p.name} ({p.start_time}-{p.end_time}).")


@router.post("/periods", status_code=201)
def create_period(data: PeriodIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _check_period(db, data, None)
    highest = db.scalar(select(func.max(Period.order))) or 0
    p = Period(
        name=data.name,
        start_time=data.start_time,
        end_time=data.end_time,
        is_break=data.is_break,
        order=data.order if data.order is not None else highest + 1,
    )
    db.add(p)
    db.commit()
    return services.period_dict(p)


@router.put("/periods/{period_id}")
def update_period(period_id: int, data: PeriodIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    p = _get(db, Period, period_id, "Period")
    _check_period(db, data, period_id)
    if data.is_break and not p.is_break:
        n = db.scalar(select(func.count()).select_from(RoutineSlot).where(RoutineSlot.period_id == period_id)) or 0
        if n:
            raise HTTPException(400, f"{p.name} has {n} class(es) in the routine. Clear them before making it a break.")
    p.name, p.start_time, p.end_time, p.is_break = data.name, data.start_time, data.end_time, data.is_break
    if data.order is not None:
        p.order = data.order
    db.commit()
    return services.period_dict(p)


@router.delete("/periods/{period_id}")
def delete_period(period_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    p = _get(db, Period, period_id, "Period")
    n = db.execute(delete(RoutineSlot).where(RoutineSlot.period_id == period_id)).rowcount or 0
    db.delete(p)
    db.commit()
    return {"ok": True, "slots_removed": n}


def _routine_section(db: Session, user: User, class_id: int, section_id: int) -> Section:
    if user.role == "student":
        own = db.get(Student, user.student_id) if user.student_id else None
        if not own:
            raise HTTPException(403, "This student account is not linked to a student record.")
        class_id, section_id = own.class_id, own.section_id
    sec = _get(db, Section, section_id, "Section")
    if class_id and sec.class_id != class_id:
        raise HTTPException(400, "That section does not belong to the selected class.")
    return sec


def _routine_payload(db: Session, slots: list[dict]) -> dict:
    return {
        "days": services.working_days(db),
        "day_names": services.DAY_NAMES,
        "periods": [services.period_dict(p) for p in services.periods(db)],
        "slots": slots,
        "today": services.day_code(),
    }


@router.get("/routine")
def class_routine(
    class_id: int = 0, section_id: int = 0, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Weekly routine of one class section. Students always get their own section."""
    if user.role != "student" and not section_id:
        raise HTTPException(400, "Choose a class and section.")
    sec = _routine_section(db, user, class_id, section_id)
    if user.role == "teacher":
        _check_class_scope(db, user, sec.class_id, sec.id)
    cls = db.get(Class, sec.class_id)
    data = _routine_payload(db, services.routine_slots(db, section_id=sec.id))
    data.update(
        {
            "class_id": sec.class_id,
            "section_id": sec.id,
            "class_name": cls.name if cls else "",
            "section_name": sec.name,
        }
    )
    if user.role != "student":
        # default teacher per subject for this section (shown when filling the grid)
        subject_ids = set(services.class_subject_ids(db, sec.class_id))
        subject_ids |= {
            a.subject_id
            for a in db.scalars(select(TeacherSubject).where(TeacherSubject.class_id == sec.class_id)).all()
        }
        defaults = {}
        for sid in subject_ids:
            a = services.assigned_teacher(db, sec.class_id, sec.id, sid)
            defaults[str(sid)] = a.teacher_id if a else None
        data["default_teachers"] = defaults
        data["subject_ids"] = sorted(subject_ids)
    return data


@router.get("/my/routine")
def my_routine(teacher_id: int = 0, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    """A teacher's own weekly routine. Admins may look at any teacher's routine."""
    tid = teacher_id if (teacher_id and user.role == "admin") else user.id
    teacher = _get(db, User, tid, "Teacher")
    data = _routine_payload(db, services.routine_slots(db, teacher_id=tid))
    data.update({"teacher_id": tid, "teacher_name": services.teacher_name(teacher)})
    data["today_classes"] = services.teacher_today(db, tid)
    return data


@router.put("/routine/slot")
def save_slot(data: SlotIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    sec = _get(db, Section, data.section_id, "Section")
    if sec.class_id != data.class_id:
        raise HTTPException(400, "That section does not belong to the selected class.")
    if data.day not in services.working_days(db):
        raise HTTPException(400, f"{services.DAY_NAMES[data.day]} is not a working day (see Settings).")
    period = _get(db, Period, data.period_id, "Period")
    if period.is_break:
        raise HTTPException(400, f"{period.name} is a break. Classes cannot be put in a break.")
    subject = _get(db, Subject, data.subject_id, "Subject")
    teacher_id = data.teacher_id
    if teacher_id is None:
        a = services.assigned_teacher(db, data.class_id, data.section_id, data.subject_id)
        teacher_id = a.teacher_id if a else None
    if teacher_id is not None:
        teacher = _get(db, User, teacher_id, "Teacher")
        if teacher.role not in ("teacher", "admin"):
            raise HTTPException(400, "Only teacher or admin accounts can teach a class.")
        if not services.is_assigned(db, teacher_id, data.class_id, data.section_id, data.subject_id):
            raise HTTPException(
                400,
                f"{services.teacher_name(teacher)} is not assigned to {subject.name} in this class. "
                "Assign the teacher first (Teacher assignments).",
            )
        clash = db.scalars(
            select(RoutineSlot).where(
                RoutineSlot.teacher_id == teacher_id,
                RoutineSlot.day == data.day,
                RoutineSlot.period_id == data.period_id,
                RoutineSlot.section_id != data.section_id,
            )
        ).first()
        if clash:
            c, s2 = db.get(Class, clash.class_id), db.get(Section, clash.section_id)
            raise HTTPException(
                400,
                f"{services.teacher_name(teacher)} already teaches {c.name if c else ''}"
                f"{' - ' + s2.name if s2 else ''} on {services.DAY_NAMES[data.day]}, {period.name}.",
            )
    slot = db.scalars(
        select(RoutineSlot).where(
            RoutineSlot.section_id == data.section_id,
            RoutineSlot.day == data.day,
            RoutineSlot.period_id == data.period_id,
        )
    ).first()
    if not slot:
        slot = RoutineSlot(section_id=data.section_id, day=data.day, period_id=data.period_id, class_id=data.class_id)
        db.add(slot)
    slot.class_id, slot.subject_id, slot.teacher_id, slot.room = data.class_id, data.subject_id, teacher_id, data.room
    db.commit()
    return next(s for s in services.routine_slots(db, section_id=data.section_id) if s["id"] == slot.id)


@router.delete("/routine/slot/{slot_id}")
def delete_slot(slot_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    db.delete(_get(db, RoutineSlot, slot_id, "Routine slot"))
    db.commit()
    return {"ok": True}
