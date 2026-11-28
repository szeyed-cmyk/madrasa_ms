"""Shared helpers for the API routers (lookups, role scope checks, upload validation).

No routes here. Role guards are the FastAPI dependencies in app/security.py:
require_admin (admin only), require_staff (admin + teacher), current_user (any logged-in user; route
bodies then call ensure_student_access / services.student_condition for record isolation).
"""

from __future__ import annotations

import base64
import binascii
import re
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..models import (
    Class,
    Exam,
    Section,
    TeacherSubject,
    User,
)

MAX_LOGO_BYTES = 300 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024
LOGO_RE = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)$")
LOGO_MAGIC = {"png": b"\x89PNG", "jpeg": b"\xff\xd8\xff", "gif": b"GIF8", "webp": b"RIFF"}


def _get(db: Session, model, pk: int, label: str):
    obj = db.get(model, pk)
    if not obj:
        raise HTTPException(404, f"{label} not found")
    return obj


def _scoped(query, db: Session, user: User):
    """Limit a Student query to what the user may see (admin: all, teacher: own classes)."""
    cond = services.student_condition(db, user)
    return query if cond is None else query.where(cond)


def _check_class_scope(db: Session, user: User, class_id: int, section_id: int = 0) -> dict[int, set[int] | None]:
    """Teachers may only open classes/sections they teach. Returns the teacher's class map ({} for admins)."""
    if user.role != "teacher":
        return {}
    allowed = services.teacher_class_sections(db, user)
    if class_id not in allowed:
        raise HTTPException(403, "This class is not one you teach.")
    secs = allowed[class_id]
    if section_id and secs is not None and section_id not in secs:
        raise HTTPException(403, "This section is not one you teach.")
    return allowed


def _exam_or_latest(db: Session, exam_id: int | None, published_only: bool = False) -> Exam | None:
    if exam_id:
        exam = _get(db, Exam, exam_id, "Exam")
        if published_only and not exam.is_published:
            raise HTTPException(404, "Exam not found")
        return exam
    q = select(Exam)
    if published_only:
        q = q.where(Exam.is_published.is_(True))
    return db.scalars(q.order_by(Exam.id.desc())).first()


# ------------------------------------------------------------------ students (the master database)
def _validate_class_section(db: Session, class_id: int, section_id: int) -> None:
    if not db.get(Class, class_id):
        raise HTTPException(400, "Class not found. Add classes first.")
    sec = db.get(Section, section_id)
    if not sec:
        raise HTTPException(400, "Section not found. Add sections first.")
    if sec.class_id != class_id:
        raise HTTPException(400, "That section does not belong to the selected class.")


def _validate_logo(logo: str) -> str:
    m = LOGO_RE.match(logo)
    if not m:
        raise HTTPException(400, "Logo must be a PNG, JPEG, GIF or WebP image.")
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(400, "Logo image could not be read.") from exc
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Logo is too large (max 300 KB).")
    if not raw.startswith(LOGO_MAGIC[m.group(1)]):
        raise HTTPException(400, "Logo file content does not match its image type.")
    return f"data:image/{m.group(1)};base64," + base64.b64encode(raw).decode()


def _validate_photo(photo: str | None) -> str | None:
    """Validate a student/teacher photo data URL (same rules as logo, max 300 KB)."""
    if not photo:
        return None
    return _validate_logo(photo)


def logo_from_upload(raw: bytes) -> str:
    """1.3.0: turn an uploaded image file (first-run setup) into the same validated data URL Settings stores."""
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(400, "Logo is too large (max 300 KB).")
    kind = next((k for k, magic in LOGO_MAGIC.items() if raw.startswith(magic)), None)
    if kind == "webp" and raw[8:12] != b"WEBP":
        kind = None
    if not kind:
        raise HTTPException(400, "Logo must be a PNG, JPEG, GIF or WebP image.")
    return _validate_logo(f"data:image/{kind};base64," + base64.b64encode(raw).decode())


# ------------------------------------------------------------------ 1.3.0: teachers page (admin)
def _teacher(db: Session, teacher_id: int) -> User:
    u = db.get(User, teacher_id)
    if not u or u.role != "teacher":
        raise HTTPException(404, "Teacher not found")
    return u


@contextmanager
def _account_errors():
    """services.AccountError (a broken login rule) -> HTTP 400 with the same message."""
    try:
        yield
    except services.AccountError as exc:
        raise HTTPException(400, str(exc)) from exc


def _assignment_dict(a: TeacherSubject, users: dict, subjects: dict, classes: dict, sections: dict) -> dict:
    sec = sections.get(a.section_id)
    return {
        "id": a.id,
        "teacher_id": a.teacher_id,
        "teacher_name": services.teacher_name(users.get(a.teacher_id)),
        "class_id": a.class_id,
        "class_name": classes[a.class_id].name if a.class_id in classes else "",
        "section_id": a.section_id,
        "section_name": sec.name if sec else "",
        "subject_id": a.subject_id,
        "subject_name": subjects[a.subject_id].name if a.subject_id in subjects else "",
    }
