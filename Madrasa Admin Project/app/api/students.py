"""Student records: list/create/update/status/delete, CSV import/export, profile and per-student subjects.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/students                                        require_staff
    POST   /api/students                                        require_admin
    GET    /api/students/export.csv                             require_admin
    POST   /api/students/import                                 require_admin
    GET    /api/students/{student_pk}                           current_user
    PUT    /api/students/{student_pk}                           require_admin
    POST   /api/students/{student_pk}/status                    require_admin
    DELETE /api/students/{student_pk}                           require_admin
    GET    /api/students/{student_pk}/profile                   current_user
    GET    /api/students/{student_pk}/subjects                  current_user
    POST   /api/students/{student_pk}/subjects                  require_staff
    PUT    /api/students/{student_pk}/subjects                  require_staff
    POST   /api/students/{student_pk}/subjects/apply-class-defaults require_staff
    DELETE /api/students/{student_pk}/subjects/{subject_id}     require_staff
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Attendance,
    Class,
    Exam,
    Mark,
    Payment,
    Student,
    StudentSubject,
    Subject,
    User,
)
from ..schemas import (
    StatusIn,
    StudentIn,
    SubjectIdIn,
    SubjectIdsIn,
)
from ..security import (
    current_user,
    ensure_student_access,
    require_admin,
    require_staff,
)
from ._common import (
    MAX_CSV_BYTES,
    _exam_or_latest,
    _get,
    _scoped,
    _validate_class_section,
    _validate_photo,
)

router = APIRouter()


@router.get("/students")
def list_students(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    q: str = Query("", max_length=100),
    class_id: int = 0,
    section_id: int = 0,
    status: str = Query("", max_length=16),
):
    query = _scoped(select(Student), db, user)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Student.name.ilike(like),
                Student.admission_no.ilike(like),
                Student.student_id.ilike(like),
                Student.guardian_phone.ilike(like),
            )
        )
    if class_id:
        query = query.where(Student.class_id == class_id)
    if section_id:
        query = query.where(Student.section_id == section_id)
    if status == "current":
        query = query.where(func.lower(Student.status) != "archived")
    elif status:
        query = query.where(func.lower(Student.status) == status.lower())
    students = db.scalars(query.order_by(Student.class_id, Student.roll_no, Student.name)).all()
    classes, sections = services.class_maps(db)
    counts = dict(
        db.execute(
            select(StudentSubject.student_id, func.count())
            .where(StudentSubject.is_active.is_not(False))
            .group_by(StudentSubject.student_id)
        ).all()
    )
    out = []
    for s in students:
        d = services.student_dict(s, classes, sections)
        d["subject_count"] = counts.get(s.id, 0)
        out.append(d)
    return out


def _apply_student(db: Session, s: Student, data: StudentIn, creating: bool) -> None:
    _validate_class_section(db, data.class_id, data.section_id)
    if data.student_id:
        clash = db.scalars(
            select(Student).where(Student.student_id == data.student_id, Student.id != (s.id or 0))
        ).first()
        if clash:
            raise HTTPException(400, f"Student ID {data.student_id} is already used by {clash.name}.")
        s.student_id = data.student_id
    elif creating:
        s.student_id = services.next_student_code(db)
    adm = data.admission_no or s.admission_no or f"ADM-{date.today().year}-{s.student_id}"
    clash = db.scalars(select(Student).where(Student.admission_no == adm, Student.id != (s.id or 0))).first()
    if clash:
        raise HTTPException(400, f"Admission number {adm} is already used by {clash.name}.")
    s.admission_no = adm
    for field in (
        "name",
        "dob",
        "gender",
        "class_id",
        "section_id",
        "roll_no",
        "status",
        "address",
        "guardian_name",
        "guardian_relation",
        "guardian_phone",
        "guardian_address",
        "notes",
    ):
        setattr(s, field, getattr(data, field))
    s.admission_date = data.admission_date or s.admission_date or date.today().isoformat()
    if data.photo is not None:
        s.photo = _validate_photo(data.photo)


@router.post("/students", status_code=201)
def create_student(data: StudentIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = Student()
    _apply_student(db, s, data, creating=True)
    db.add(s)
    db.flush()
    added = services.apply_class_defaults(db, s) if data.apply_class_subjects else 0
    db.commit()
    return {"id": s.id, "student_id": s.student_id, "admission_no": s.admission_no, "subjects_added": added}


@router.get("/students/export.csv")
def export_students(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    classes, sections = services.class_maps(db)
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = [
        "student_id",
        "admission_no",
        "name",
        "dob",
        "gender",
        "class_name",
        "section_name",
        "roll_no",
        "admission_date",
        "status",
        "guardian_name",
        "guardian_relation",
        "guardian_phone",
        "address",
    ]
    w.writerow(cols)
    for s in db.scalars(select(Student).order_by(Student.class_id, Student.roll_no, Student.name)).all():
        d = services.student_dict(s, classes, sections)
        w.writerow([_csv_safe(d.get(c)) for c in cols])
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="students.csv"'},
    )


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    # stop spreadsheet formula injection
    if text[:1] in ("=", "+", "-", "@", "\t", "\r") and not re.fullmatch(r"[+-]?\d[\d\s-]*", text):
        return "'" + text
    return text


@router.post("/students/import")
async def import_students(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(400, "File too large (max 2 MB).")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file (in Excel: File > Save As > CSV UTF-8).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(400, "CSV must have a header row with at least: name, class_name, section_name")
    classes = {c.name.strip().lower(): c for c in db.scalars(select(Class)).all()}
    created, errors = 0, []
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not any(row.values()):
            continue
        cls = classes.get(row.get("class_name", "").lower())
        if not cls:
            errors.append(f"Row {line_no}: class '{row.get('class_name', '')}' not found")
            continue
        sec = next((x for x in cls.sections if x.name.lower() == (row.get("section_name") or "A").lower()), None)
        if not sec:
            errors.append(f"Row {line_no}: section '{row.get('section_name', '')}' not found in {cls.name}")
            continue
        try:
            data = StudentIn(
                name=row.get("name", ""),
                class_id=cls.id,
                section_id=sec.id,
                student_id=row.get("student_id") or None,
                admission_no=row.get("admission_no") or None,
                dob=row.get("dob") or None,
                gender=row.get("gender") or None,
                roll_no=row.get("roll_no") or None,
                admission_date=row.get("admission_date") or None,
                status=row.get("status") or "Active",
                guardian_name=row.get("guardian_name") or None,
                guardian_relation=row.get("guardian_relation") or None,
                guardian_phone=row.get("guardian_phone") or None,
                address=row.get("address") or None,
            )
            s = Student()
            _apply_student(db, s, data, creating=True)
            db.add(s)
            db.flush()
            services.apply_class_defaults(db, s)
            db.commit()
            created += 1
        except HTTPException as exc:
            db.rollback()
            errors.append(f"Row {line_no}: {exc.detail}")
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            db.rollback()
            msg = "; ".join(e.get("msg", "") for e in getattr(exc, "errors", lambda: [])()) or str(exc)
            errors.append(f"Row {line_no}: {msg}")
        if len(errors) > 200:
            errors.append("Too many errors; stopped.")
            break
    return {"created": created, "errors": errors}


@router.get("/students/{student_pk}")
def get_student(student_pk: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_student_access(user, student_pk, db)
    s = _get(db, Student, student_pk, "Student")
    classes, sections = services.class_maps(db)
    return services.student_dict(s, classes, sections)


@router.put("/students/{student_pk}")
def update_student(
    student_pk: int, data: StudentIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    s = _get(db, Student, student_pk, "Student")
    old_class = s.class_id
    _apply_student(db, s, data, creating=False)
    added = 0
    if data.apply_class_subjects and old_class != data.class_id:
        added = services.apply_class_defaults(db, s)
    db.commit()
    return {"ok": True, "subjects_added": added}


@router.post("/students/{student_pk}/status")
def update_student_status(
    student_pk: int, data: StatusIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    s = _get(db, Student, student_pk, "Student")
    s.status = data.status
    if data.status != "Active":
        for login in db.scalars(select(User).where(User.student_id == s.id)).all():
            login.is_active = False if data.status == "Archived" else login.is_active
    db.commit()
    return {"ok": True, "status": s.status}


@router.delete("/students/{student_pk}")
def delete_student(student_pk: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = _get(db, Student, student_pk, "Student")
    if db.scalar(select(func.count()).select_from(Payment).where(Payment.student_id == s.id)):
        raise HTTPException(400, "This student has fee payments. Set the status to Archived instead of deleting.")
    for model in (Mark, Attendance, StudentSubject):
        db.execute(delete(model).where(model.student_id == s.id))
    db.execute(delete(User).where(User.student_id == s.id))
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/students/{student_pk}/profile")
def student_profile(
    student_pk: int, exam_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    """Everything about one student in one call: details, subjects, marks, attendance, fees, login."""
    ensure_student_access(user, student_pk, db)
    s = _get(db, Student, student_pk, "Student")
    classes, sections = services.class_maps(db)
    settings = services.school(db)
    is_student = user.role == "student"
    exams_q = select(Exam)
    if is_student:
        exams_q = exams_q.where(Exam.is_published.is_(True))
    exams = db.scalars(exams_q.order_by(Exam.id.desc())).all()
    if exam_id:
        exam = _exam_or_latest(db, exam_id, published_only=is_student)
    else:
        exam = services.default_exam(db, s.id, published_only=is_student)
    result = services.student_result(db, s, exam, settings.grading_scale)
    data = {
        **services.student_dict(s, classes, sections),
        "school_name": settings.name,
        "logo": settings.logo_path,
        "currency": settings.currency or "৳",
        "exams": [{"id": e.id, "name": e.name, "is_published": bool(e.is_published)} for e in exams],
        "exam": {"id": exam.id, "name": exam.name} if exam else None,
        "result": result,
        "subjects": result["subjects"],
        "class_default_subject_ids": services.class_subject_ids(db, s.class_id),
        "attendance": services.attendance_summary(db, s.id),
        "grading_scale": settings.grading_scale,
    }
    if user.role == "admin" or is_student:
        payments = db.scalars(select(Payment).where(Payment.student_id == s.id).order_by(Payment.id.desc())).all()
        data["fees"] = services.fee_status(db, s)
        data["payments"] = [services.payment_dict(p, s) for p in payments]
    if user.role == "admin":
        login = db.scalars(select(User).where(User.student_id == s.id)).first()
        data["login"] = (
            {
                "has_login": True,
                "username": login.username,
                "is_active": bool(login.is_active),
                "must_change": bool(login.must_change_password),
            }
            if login
            else {"has_login": False}
        )
    return data


# ------------------------------------------------------------------ student subjects & marks
@router.get("/students/{student_pk}/subjects")
def get_student_subjects(student_pk: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ensure_student_access(user, student_pk, db)
    _get(db, Student, student_pk, "Student")
    return [
        {"id": s.id, "name": s.name, "code": s.code, "max_marks": s.max_marks}
        for s in services.student_subjects(db, student_pk)
    ]


@router.post("/students/{student_pk}/subjects")
def add_student_subject(
    student_pk: int, data: SubjectIdIn, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    _get(db, Student, student_pk, "Student")
    ensure_student_access(user, student_pk, db)
    _get(db, Subject, data.subject_id, "Subject")
    added = services.assign_subject(db, student_pk, data.subject_id)
    db.commit()
    return {"ok": True, "added": added}


@router.put("/students/{student_pk}/subjects")
def set_student_subjects(
    student_pk: int, data: SubjectIdsIn, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    _get(db, Student, student_pk, "Student")
    ensure_student_access(user, student_pk, db)
    wanted = set(data.subject_ids)
    valid = set(db.scalars(select(Subject.id).where(Subject.id.in_(wanted))).all()) if wanted else set()
    if wanted - valid:
        raise HTTPException(400, "One or more subjects do not exist.")
    db.execute(
        delete(StudentSubject).where(StudentSubject.student_id == student_pk, StudentSubject.subject_id.not_in(wanted))
    )
    for sid in wanted:
        services.assign_subject(db, student_pk, sid)
    db.commit()
    return {"ok": True, "subject_ids": sorted(wanted)}


@router.post("/students/{student_pk}/subjects/apply-class-defaults")
def student_apply_defaults(student_pk: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    s = _get(db, Student, student_pk, "Student")
    ensure_student_access(user, student_pk, db)
    added = services.apply_class_defaults(db, s)
    db.commit()
    return {"ok": True, "added": added}


@router.delete("/students/{student_pk}/subjects/{subject_id}")
def remove_student_subject(
    student_pk: int, subject_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    _get(db, Student, student_pk, "Student")
    ensure_student_access(user, student_pk, db)
    db.execute(
        delete(StudentSubject).where(StudentSubject.student_id == student_pk, StudentSubject.subject_id == subject_id)
    )
    db.commit()
    return {"ok": True}
