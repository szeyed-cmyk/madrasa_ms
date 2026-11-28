"""Staff accounts, teacher accounts and student logins (admin only). Password logic lives in services.py.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/users                                           require_admin
    POST   /api/users                                           require_admin
    PUT    /api/users/{user_id}                                 require_admin
    POST   /api/students/{student_pk}/create-login              require_admin
    POST   /api/students/{student_pk}/disable-login             require_admin
    GET    /api/students/{student_pk}/login-status              require_admin
    POST   /api/students/{student_pk}/enable-login              require_admin
    GET    /api/teachers/manage                                 require_admin
    POST   /api/teachers                                        require_admin
    PUT    /api/teachers/{teacher_id}                           require_admin
    POST   /api/teachers/{teacher_id}/reset-password            require_admin
    POST   /api/teachers/{teacher_id}/status                    require_admin
    GET    /api/student-logins                                  require_admin
    POST   /api/student-logins/bulk                             require_admin
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Class,
    RoutineSlot,
    Student,
    TeacherSubject,
    User,
)
from ..schemas import (
    ActiveIn,
    BulkLoginIn,
    LoginCreateIn,
    PasswordResetIn,
    TeacherIn,
    TeacherUpdateIn,
    UserIn,
    UserUpdateIn,
)
from ..security import (
    require_admin,
)
from ._common import (
    _account_errors,
    _assignment_dict,
    _get,
    _teacher,
    _validate_class_section,
    _validate_photo,
)

router = APIRouter()


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": bool(u.is_active),
            "must_change_password": bool(u.must_change_password),
            "student_id": u.student_id,
            "phone": u.phone,
            "last_login": u.last_login.isoformat(timespec="minutes") + "Z" if u.last_login else None,
            "has_password": "$" in (u.password_hash or ""),  # sample teachers start without a password
        }
        for u in db.scalars(select(User).order_by(User.role, User.username)).all()
    ]


@router.post("/users", status_code=201)
def create_user(data: UserIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.scalars(select(User).where(func.lower(User.username) == data.username.lower())).first():
        raise HTTPException(400, "Username already taken.")
    with _account_errors():
        password, _ = services.choose_password(data.password)
    u = User(username=data.username, full_name=data.full_name, role=data.role, is_active=True)
    services.issue_password(u, password)  # must_change_password=True: the new admin picks their own
    db.add(u)
    db.commit()
    return {"id": u.id, "username": u.username}


@router.put("/users/{user_id}")
def update_user(user_id: int, data: UserUpdateIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    u = _get(db, User, user_id, "User")
    if data.is_active is False and u.id == user.id:
        raise HTTPException(400, "You cannot deactivate your own account.")
    if data.is_active is False and u.role == "admin":
        admins = (
            db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0
        )
        if admins <= 1:
            raise HTTPException(400, "At least one active admin is required.")
    if data.full_name is not None:
        u.full_name = data.full_name
    if data.is_active is not None:
        u.is_active = data.is_active
    if data.password:
        with _account_errors():
            password, _ = services.choose_password(data.password)
        services.issue_password(u, password, force_change=u.id != user.id)
    db.commit()
    return {"ok": True}


@router.post("/students/{student_pk}/create-login")
def create_student_login(
    student_pk: int, data: LoginCreateIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    s = _get(db, Student, student_pk, "Student")
    with _account_errors():
        u, generated = services.save_student_login(db, s, data.username, data.password)
    username = u.username
    return {
        "ok": True,
        "username": username,
        "temporary_password": generated,
        "message": "Student login saved. The student must change the password at first login.",
    }


@router.post("/students/{student_pk}/disable-login")
def disable_student_login(student_pk: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _get(db, Student, student_pk, "Student")
    for u in db.scalars(select(User).where(User.student_id == student_pk)).all():
        u.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/students/{student_pk}/login-status")
def student_login_status(student_pk: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    u = db.scalars(select(User).where(User.student_id == student_pk)).first()
    if not u:
        return {"has_login": False}
    return {
        "has_login": True,
        "username": u.username,
        "is_active": bool(u.is_active),
        "must_change": bool(u.must_change_password),
    }


@router.post("/students/{student_pk}/enable-login")
def enable_student_login(student_pk: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = _get(db, Student, student_pk, "Student")
    if (s.status or "").lower() == "archived":
        raise HTTPException(400, "This student is archived. Change the status first.")
    logins = db.scalars(select(User).where(User.student_id == student_pk)).all()
    if not logins:
        raise HTTPException(400, "This student has no login yet. Create one first.")
    for u in logins:
        u.is_active = True
    db.commit()
    return {"ok": True}


@router.get("/teachers/manage")
def manage_teachers(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Every teacher account with login status, assigned subjects/classes and weekly periods."""
    subjects, users, classes, sections = services._lookups(db)
    by_teacher: dict[int, list[dict]] = {}
    for a in db.scalars(select(TeacherSubject)).all():
        by_teacher.setdefault(a.teacher_id, []).append(_assignment_dict(a, users, subjects, classes, sections))
    periods = dict(
        db.execute(
            select(RoutineSlot.teacher_id, func.count())
            .where(RoutineSlot.teacher_id.is_not(None))
            .group_by(RoutineSlot.teacher_id)
        ).all()
    )
    out = []
    for u in db.scalars(select(User).where(User.role == "teacher").order_by(User.full_name, User.username)).all():
        asg = sorted(by_teacher.get(u.id, []), key=lambda r: (r["class_name"], r["section_name"], r["subject_name"]))
        out.append(
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name or "",
                "phone": u.phone or "",
                "photo": u.photo,
                "is_active": bool(u.is_active),
                "has_password": "$" in (u.password_hash or ""),
                "must_change_password": bool(u.must_change_password),
                "last_login": u.last_login.isoformat(timespec="minutes") + "Z" if u.last_login else None,
                "assignments": asg,
                "classes": sorted(
                    {r["class_name"] + (" - " + r["section_name"] if r["section_name"] else "") for r in asg}
                ),
                "periods_per_week": periods.get(u.id, 0),
            }
        )
    return out


@router.post("/teachers", status_code=201)
def create_teacher(data: TeacherIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    photo = _validate_photo(data.photo)
    with _account_errors():
        u, generated = services.create_teacher_account(
            db, data.username, data.full_name, data.phone, photo, data.password
        )
    return {
        "id": u.id,
        "username": u.username,
        "temporary_password": generated,
        "message": "Teacher added. They must change the password at first login.",
    }


@router.put("/teachers/{teacher_id}")
def update_teacher(
    teacher_id: int, data: TeacherUpdateIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    u = _teacher(db, teacher_id)
    if services.username_taken(db, data.username, except_id=u.id):
        raise HTTPException(400, f"The username '{data.username}' is already taken. Choose another one.")
    u.full_name, u.username, u.phone = data.full_name, data.username, data.phone
    if data.photo is not None:
        u.photo = _validate_photo(data.photo)
    db.commit()
    return {"ok": True}


@router.post("/teachers/{teacher_id}/reset-password")
def reset_teacher_password(
    teacher_id: int, data: PasswordResetIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    u = _teacher(db, teacher_id)
    with _account_errors():
        generated = services.reset_teacher_password(u, data.password)  # also ends the teacher's sessions
    db.commit()
    return {"ok": True, "username": u.username, "temporary_password": generated, "is_active": bool(u.is_active)}


@router.post("/teachers/{teacher_id}/status")
def set_teacher_status(
    teacher_id: int, data: ActiveIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    u = _teacher(db, teacher_id)
    if data.is_active and "$" not in (u.password_hash or ""):
        raise HTTPException(400, "Set a password first (Reset password); the login is enabled with it.")
    u.is_active = data.is_active
    db.commit()
    return {"ok": True, "is_active": bool(u.is_active)}


# ------------------------------------------------------------------ 1.3.0: student logins page (admin)
@router.get("/student-logins")
def student_logins(
    class_id: int = 0,
    section_id: int = 0,
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    query = select(Student).where(func.lower(Student.status) != "archived")
    if class_id:
        query = query.where(Student.class_id == class_id)
    if section_id:
        query = query.where(Student.section_id == section_id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(Student.name.ilike(like), Student.student_id.ilike(like)))
    students = db.scalars(query.order_by(Student.class_id, Student.section_id, Student.roll_no, Student.name)).all()
    logins = {u.student_id: u for u in db.scalars(select(User).where(User.role == "student")).all()}
    classes, sections = services.class_maps(db)
    out = []
    for s in students:
        u = logins.get(s.id)
        d = services.student_dict(s, classes, sections)
        out.append(
            {
                "id": s.id,
                "student_id": s.student_id,
                "name": s.name,
                "roll_no": s.roll_no,
                "class_name": d.get("class_name", ""),
                "section_name": d.get("section_name", ""),
                "has_login": bool(u),
                "username": u.username if u else None,
                "is_active": bool(u.is_active) if u else False,
                "must_change": bool(u.must_change_password) if u else False,
                "last_login": u.last_login.isoformat(timespec="minutes") + "Z" if u and u.last_login else None,
            }
        )
    return out


@router.post("/student-logins/bulk")
def bulk_student_logins(data: BulkLoginIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Create logins (username = 6-digit student ID) for every current student of a class or section.

    The temporary passwords are returned once, for the printable credentials slip; only hashes are stored.
    """
    _get(db, Class, data.class_id, "Class")
    if data.section_id:
        _validate_class_section(db, data.class_id, data.section_id)
    query = select(Student).where(Student.class_id == data.class_id, func.lower(Student.status) != "archived")
    if data.section_id:
        query = query.where(Student.section_id == data.section_id)
    students = list(db.scalars(query.order_by(Student.section_id, Student.roll_no, Student.name)).all())
    return services.bulk_student_logins(db, students, data.reset_existing)
