"""Classes, sections, subjects and the subjects of each class.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/classes                                         require_staff
    POST   /api/classes                                         require_admin
    PUT    /api/classes/{class_id}                              require_admin
    DELETE /api/classes/{class_id}                              require_admin
    POST   /api/sections                                        require_admin
    DELETE /api/sections/{section_id}                           require_admin
    GET    /api/subjects                                        require_staff
    POST   /api/subjects                                        require_admin
    PUT    /api/subjects/{subject_id}                           require_admin
    DELETE /api/subjects/{subject_id}                           require_admin
    GET    /api/classes/{class_id}/subjects                     require_staff
    PUT    /api/classes/{class_id}/subjects                     require_admin
    POST   /api/classes/{class_id}/subjects/apply               require_admin
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Class,
    ClassSubject,
    FeePlan,
    Mark,
    RoutineSlot,
    Section,
    Student,
    StudentSubject,
    Subject,
    TeacherSubject,
    User,
)
from ..schemas import (
    ClassIn,
    SectionIn,
    SubjectIdsIn,
    SubjectIn,
)
from ..security import (
    require_admin,
    require_staff,
)
from ._common import (
    _get,
)

router = APIRouter()


# ------------------------------------------------------------------ classes & sections
@router.get("/classes")
def list_classes(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    counts = dict(
        db.execute(
            select(Student.class_id, func.count())
            .where(func.lower(Student.status) != "archived")
            .group_by(Student.class_id)
        ).all()
    )
    defaults: dict[int, list[int]] = {}
    for cs in db.scalars(select(ClassSubject)).all():
        defaults.setdefault(cs.class_id, []).append(cs.subject_id)
    fees = {}
    for fp in db.scalars(select(FeePlan)).all():
        fees[fp.class_id] = fees.get(fp.class_id, 0) + (fp.amount or 0)
    out = [
        {
            "id": c.id,
            "name": c.name,
            "order": c.order,
            "sections": [{"id": s.id, "name": s.name} for s in c.sections],
            "student_count": counts.get(c.id, 0),
            "subject_ids": defaults.get(c.id, []),
            "monthly_fee": fees.get(c.id, 0),
        }
        for c in db.scalars(select(Class).order_by(Class.order, Class.name)).all()
    ]
    if user.role == "teacher":  # 1.3.0: only the classes/sections the teacher teaches, no fee amounts
        allowed = services.teacher_class_sections(db, user)
        rows = []
        for c in out:
            if c["id"] not in allowed:
                continue
            secs = allowed[c["id"]]
            if secs is not None:
                c["sections"] = [x for x in c["sections"] if x["id"] in secs]
            c["monthly_fee"] = None
            rows.append(c)
        out = rows
    return out


@router.post("/classes", status_code=201)
def create_class(data: ClassIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.scalars(select(Class).where(func.lower(Class.name) == data.name.lower())).first():
        raise HTTPException(400, "A class with that name already exists.")
    highest = db.scalar(select(func.max(Class.order))) or 0
    c = Class(name=data.name, order=data.order if data.order is not None else highest + 1)
    db.add(c)
    db.flush()
    db.add(Section(name="A", class_id=c.id))
    db.commit()
    return {"id": c.id, "name": c.name}


@router.put("/classes/{class_id}")
def update_class(class_id: int, data: ClassIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = _get(db, Class, class_id, "Class")
    clash = db.scalars(select(Class).where(func.lower(Class.name) == data.name.lower(), Class.id != class_id)).first()
    if clash:
        raise HTTPException(400, "A class with that name already exists.")
    c.name = data.name
    if data.order is not None:
        c.order = data.order
    db.commit()
    return {"ok": True}


@router.delete("/classes/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = _get(db, Class, class_id, "Class")
    if db.scalar(select(func.count()).select_from(Student).where(Student.class_id == class_id)):
        raise HTTPException(400, "Cannot delete a class that still has students. Move or delete them first.")
    db.execute(delete(RoutineSlot).where(RoutineSlot.class_id == class_id))
    db.execute(delete(TeacherSubject).where(TeacherSubject.class_id == class_id))
    db.execute(delete(Section).where(Section.class_id == class_id))
    db.execute(delete(ClassSubject).where(ClassSubject.class_id == class_id))
    db.execute(delete(FeePlan).where(FeePlan.class_id == class_id))
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/sections", status_code=201)
def create_section(data: SectionIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _get(db, Class, data.class_id, "Class")
    if db.scalars(
        select(Section).where(Section.class_id == data.class_id, func.lower(Section.name) == data.name.lower())
    ).first():
        raise HTTPException(400, "Section already exists in this class.")
    s = Section(name=data.name, class_id=data.class_id)
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name}


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = _get(db, Section, section_id, "Section")
    if db.scalar(select(func.count()).select_from(Student).where(Student.section_id == section_id)):
        raise HTTPException(400, "Cannot delete a section that still has students.")
    db.execute(delete(RoutineSlot).where(RoutineSlot.section_id == section_id))
    db.execute(delete(TeacherSubject).where(TeacherSubject.section_id == section_id))
    db.delete(s)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ subjects
def _subject_dict(db: Session, s: Subject, class_map: dict[int, list[int]], counts: dict[int, int]) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "code": s.code,
        "max_marks": s.max_marks,
        "pass_marks": s.pass_marks,
        "credits": s.credits,
        "is_active": s.is_active is not False,
        "class_ids": class_map.get(s.id, []),
        "student_count": counts.get(s.id, 0),
    }


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    class_map: dict[int, list[int]] = {}
    for cs in db.scalars(select(ClassSubject)).all():
        class_map.setdefault(cs.subject_id, []).append(cs.class_id)
    counts = dict(
        db.execute(
            select(StudentSubject.subject_id, func.count())
            .where(StudentSubject.is_active.is_not(False))
            .group_by(StudentSubject.subject_id)
        ).all()
    )
    return [_subject_dict(db, s, class_map, counts) for s in db.scalars(select(Subject).order_by(Subject.name)).all()]


def _set_subject_classes(db: Session, subject_id: int, class_ids: list[int]) -> None:
    valid = set(db.scalars(select(Class.id).where(Class.id.in_(class_ids))).all()) if class_ids else set()
    if set(class_ids) - valid:
        raise HTTPException(400, "One or more classes do not exist.")
    db.execute(delete(ClassSubject).where(ClassSubject.subject_id == subject_id, ClassSubject.class_id.not_in(valid)))
    have = set(db.scalars(select(ClassSubject.class_id).where(ClassSubject.subject_id == subject_id)).all())
    for cid in valid - have:
        db.add(ClassSubject(class_id=cid, subject_id=subject_id))


@router.post("/subjects", status_code=201)
def create_subject(data: SubjectIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.scalars(select(Subject).where(func.lower(Subject.name) == data.name.lower())).first():
        raise HTTPException(400, "A subject with that name already exists.")
    s = Subject(
        name=data.name,
        code=data.code,
        max_marks=data.max_marks,
        pass_marks=data.pass_marks,
        credits=data.credits,
        is_active=data.is_active,
    )
    db.add(s)
    db.flush()
    if data.class_ids:
        _set_subject_classes(db, s.id, data.class_ids)
    db.commit()
    return {"id": s.id, "name": s.name}


@router.put("/subjects/{subject_id}")
def update_subject(
    subject_id: int, data: SubjectIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    s = _get(db, Subject, subject_id, "Subject")
    clash = db.scalars(
        select(Subject).where(func.lower(Subject.name) == data.name.lower(), Subject.id != subject_id)
    ).first()
    if clash:
        raise HTTPException(400, "A subject with that name already exists.")
    highest = db.scalar(select(func.max(Mark.marks_obtained)).where(Mark.subject_id == subject_id))
    if highest is not None and highest > data.max_marks:
        raise HTTPException(400, f"Full marks cannot be lower than marks already entered ({highest:g}).")
    s.name, s.code, s.max_marks, s.pass_marks, s.credits, s.is_active = (
        data.name,
        data.code,
        data.max_marks,
        data.pass_marks,
        data.credits,
        data.is_active,
    )
    for m in db.scalars(select(Mark).where(Mark.subject_id == subject_id)).all():
        m.max_marks = data.max_marks
    if data.class_ids is not None:
        _set_subject_classes(db, subject_id, data.class_ids)
    db.commit()
    return {"ok": True}


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = _get(db, Subject, subject_id, "Subject")
    marks = db.scalar(select(func.count()).select_from(Mark).where(Mark.subject_id == subject_id)) or 0
    if marks:
        raise HTTPException(400, f"{s.name} has {marks} marks entered. Mark it inactive instead of deleting.")
    db.execute(delete(ClassSubject).where(ClassSubject.subject_id == subject_id))
    db.execute(delete(StudentSubject).where(StudentSubject.subject_id == subject_id))
    db.execute(delete(TeacherSubject).where(TeacherSubject.subject_id == subject_id))
    db.execute(delete(RoutineSlot).where(RoutineSlot.subject_id == subject_id))
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/classes/{class_id}/subjects")
def get_class_subjects(class_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    _get(db, Class, class_id, "Class")
    return {"class_id": class_id, "subject_ids": services.class_subject_ids(db, class_id)}


@router.put("/classes/{class_id}/subjects")
def set_class_subjects(
    class_id: int, data: SubjectIdsIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    _get(db, Class, class_id, "Class")
    wanted = set(data.subject_ids)
    valid = set(db.scalars(select(Subject.id).where(Subject.id.in_(wanted))).all()) if wanted else set()
    if wanted - valid:
        raise HTTPException(400, "One or more subjects do not exist.")
    db.execute(delete(ClassSubject).where(ClassSubject.class_id == class_id, ClassSubject.subject_id.not_in(wanted)))
    have = set(services.class_subject_ids(db, class_id))
    for sid in wanted - have:
        db.add(ClassSubject(class_id=class_id, subject_id=sid))
    db.commit()
    return {"ok": True, "subject_ids": sorted(wanted)}


@router.post("/classes/{class_id}/subjects/apply")
def apply_class_subjects(class_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _get(db, Class, class_id, "Class")
    total = 0
    students = db.scalars(
        select(Student).where(Student.class_id == class_id, func.lower(Student.status) != "archived")
    ).all()
    for s in students:
        total += services.apply_class_defaults(db, s)
    db.commit()
    return {"ok": True, "students": len(students), "assignments_added": total}
