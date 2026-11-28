"""Exams, marks entry (teacher marks-scope check) and results.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    POST   /api/students/{student_pk}/marks                     require_staff
    GET    /api/exams                                           current_user
    POST   /api/exams                                           require_admin
    PUT    /api/exams/{exam_id}                                 require_admin
    DELETE /api/exams/{exam_id}                                 require_admin
    GET    /api/marks                                           require_staff
    POST   /api/marks/bulk                                      require_staff
    GET    /api/results                                         require_staff
    GET    /api/my/results                                      current_user
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import grading, services
from ..database import get_db
from ..models import (
    Class,
    Exam,
    Mark,
    Student,
    StudentSubject,
    Subject,
    User,
    utcnow,
)
from ..schemas import (
    ExamIn,
    MarkIn,
    MarksBulkIn,
)
from ..security import (
    current_user,
    require_admin,
    require_staff,
)
from ._common import (
    _check_class_scope,
    _exam_or_latest,
    _get,
    _scoped,
)

router = APIRouter()


def _save_mark(db: Session, student_pk: int, exam: Exam, subject: Subject, value: float | None, user: User) -> None:
    who = user.username
    if value is not None and value > (subject.max_marks or 100):
        raise HTTPException(400, f"{subject.name}: marks cannot be more than {subject.max_marks:g}.")
    if subject.id not in services.student_subject_ids(db, student_pk):
        raise HTTPException(400, f"{subject.name} is not assigned to this student. Add the subject first.")
    student = db.get(Student, student_pk)
    if not services.can_enter_marks(db, user, student, subject.id):
        raise HTTPException(
            403,
            f"You are not assigned to teach {subject.name} in this class. "
            "Ask the administrator to assign you (Routine > Teacher assignments).",
        )
    rows = db.scalars(
        select(Mark).where(Mark.student_id == student_pk, Mark.exam_id == exam.id, Mark.subject_id == subject.id)
    ).all()
    if value is None:
        for r in rows:
            db.delete(r)
        return
    if rows:
        rows[0].marks_obtained = value
        rows[0].max_marks = subject.max_marks
        rows[0].entered_by = who
        rows[0].updated_at = utcnow()
        for extra in rows[1:]:
            db.delete(extra)
    else:
        db.add(
            Mark(
                student_id=student_pk,
                exam_id=exam.id,
                subject_id=subject.id,
                marks_obtained=value,
                max_marks=subject.max_marks,
                entered_by=who,
            )
        )


@router.post("/students/{student_pk}/marks")
def save_mark(student_pk: int, data: MarkIn, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    _get(db, Student, student_pk, "Student")
    exam = _get(db, Exam, data.exam_id, "Exam")
    subject = _get(db, Subject, data.subject_id, "Subject")
    _save_mark(db, student_pk, exam, subject, data.marks, user)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ exams, marks, results
@router.get("/exams")
def list_exams(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(Exam)
    if user.role == "student":
        q = q.where(Exam.is_published.is_(True))
    counts = dict(db.execute(select(Mark.exam_id, func.count()).group_by(Mark.exam_id)).all())
    return [
        {
            "id": e.id,
            "name": e.name,
            "exam_date": e.exam_date,
            "is_published": bool(e.is_published),
            "marks_count": counts.get(e.id, 0),
        }
        for e in db.scalars(q.order_by(Exam.id.desc())).all()
    ]


@router.post("/exams", status_code=201)
def create_exam(data: ExamIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    year = services.current_year(db)
    if db.scalars(
        select(Exam).where(
            func.lower(Exam.name) == data.name.lower(), Exam.academic_year_id == (year.id if year else None)
        )
    ).first():
        raise HTTPException(400, "An exam with that name already exists this year.")
    e = Exam(
        name=data.name,
        exam_date=data.exam_date,
        is_published=data.is_published,
        academic_year_id=year.id if year else None,
    )
    db.add(e)
    db.commit()
    return {"id": e.id, "name": e.name}


@router.put("/exams/{exam_id}")
def update_exam(exam_id: int, data: ExamIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    e = _get(db, Exam, exam_id, "Exam")
    e.name, e.exam_date, e.is_published = data.name, data.exam_date, data.is_published
    db.commit()
    return {"ok": True}


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    e = _get(db, Exam, exam_id, "Exam")
    n = db.scalar(select(func.count()).select_from(Mark).where(Mark.exam_id == exam_id)) or 0
    if n:
        raise HTTPException(400, f"This exam has {n} marks entered and cannot be deleted.")
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.get("/marks")
def marks_sheet(
    exam_id: int, class_id: int, section_id: int = 0, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    """Grid for subject-wise marks entry: students of a class x the subjects they take."""
    exam = _get(db, Exam, exam_id, "Exam")
    _get(db, Class, class_id, "Class")
    _check_class_scope(db, user, class_id, section_id)
    q = select(Student).where(Student.class_id == class_id, func.lower(Student.status) != "archived")
    q = _scoped(q, db, user)
    if section_id:
        q = q.where(Student.section_id == section_id)
    students = db.scalars(q.order_by(Student.roll_no, Student.name)).all()
    ids = [s.id for s in students]
    assigned: dict[int, set[int]] = {}
    if ids:
        for ss in db.scalars(
            select(StudentSubject).where(StudentSubject.student_id.in_(ids), StudentSubject.is_active.is_not(False))
        ).all():
            assigned.setdefault(ss.student_id, set()).add(ss.subject_id)
    subject_ids = set(services.class_subject_ids(db, class_id))
    for v in assigned.values():
        subject_ids |= v
    subjects = (
        db.scalars(select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.name)).all()
        if subject_ids
        else []
    )
    marks: dict[int, dict[int, float]] = {}
    if ids:
        for m in db.scalars(select(Mark).where(Mark.exam_id == exam.id, Mark.student_id.in_(ids))).all():
            marks.setdefault(m.student_id, {})[m.subject_id] = m.marks_obtained
    if user.role == "admin":
        editable = [s.id for s in subjects]
    else:
        editable = sorted(services.teacher_subject_ids(db, user, class_id, section_id or None))
    return {
        "exam": {"id": exam.id, "name": exam.name},
        "subjects": [{"id": s.id, "name": s.name, "code": s.code, "max_marks": s.max_marks} for s in subjects],
        "editable_subject_ids": editable,
        "students": [
            {
                "id": s.id,
                "name": s.name,
                "student_id": s.student_id,
                "roll_no": s.roll_no,
                "subject_ids": sorted(assigned.get(s.id, set())),
                "marks": {str(k): v for k, v in marks.get(s.id, {}).items()},
            }
            for s in students
        ],
    }


@router.post("/marks/bulk")
def save_marks_bulk(data: MarksBulkIn, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    exam = _get(db, Exam, data.exam_id, "Exam")
    subjects = {s.id: s for s in db.scalars(select(Subject)).all()}
    saved = 0
    for e in data.entries:
        if not db.get(Student, e.student_id):
            raise HTTPException(404, f"Student {e.student_id} not found")
        subj = subjects.get(e.subject_id)
        if not subj:
            raise HTTPException(404, f"Subject {e.subject_id} not found")
        _save_mark(db, e.student_id, exam, subj, e.marks, user)
        saved += 1
    db.commit()
    return {"ok": True, "saved": saved}


@router.get("/results")
def results(
    exam_id: int | None = None,
    class_id: int = 0,
    section_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    exam = _exam_or_latest(db, exam_id)
    if not exam:
        return {"exam": None, "results": [], "scale": services.school(db).grading_scale}
    scale_name = services.school(db).grading_scale
    if class_id:
        _check_class_scope(db, user, class_id, section_id)
    rows = services.class_results(db, exam, class_id or None, section_id or None, scale_name)
    if user.role != "admin":
        visible = set(db.scalars(_scoped(select(Student.id), db, user)).all())
        rows = [r for r in rows if r["student_pk"] in visible]
    return {
        "exam": {"id": exam.id, "name": exam.name},
        "scale": scale_name,
        "scale_label": grading.scale(scale_name)["label"],
        "results": rows,
    }


@router.get("/my/results")
def my_results(exam_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "student" or not user.student_id:
        raise HTTPException(403, "Only for student accounts")
    s = _get(db, Student, user.student_id, "Student")
    exam = _exam_or_latest(db, exam_id, published_only=True) if exam_id else services.default_exam(db, s.id, True)
    return services.student_result(db, s, exam, services.school(db).grading_scale) | {
        "exam": {"id": exam.id, "name": exam.name} if exam else None
    }
