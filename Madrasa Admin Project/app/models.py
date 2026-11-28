"""Database models. The Student table is the central record everything else links to.

1.0.2: every foreign-key column is indexed (index=True) and the frequent filters have composite
indexes (attendance date+student, payments fee_month+student, marks exam+student). database/schema.sql
is generated from these models (tools/gen_schema_sql.py) and tests/test_package_layout.py compares the two,
indexes included.
1.0.4: every foreign key declares its ON DELETE rule (CASCADE for dependent rows such as marks, attendance,
sections, logins; RESTRICT where history must survive: payments, marks of an exam/subject, students of a
class; SET NULL for optional links). The API also deletes/refuses explicitly, so older databases (whose
SQLite FK clauses cannot be altered in place) behave the same.
Passwords: users.password_hash holds a salted PBKDF2-SHA256 hash only; there is no
plaintext password column anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base

DEFAULT_APP_NAME = "Madrasa Admin"
DEFAULT_TAGLINE = "School & Madrasa Management System"
ALL_DAYS = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]
DEFAULT_WORKING_DAYS = "Sat,Sun,Mon,Tue,Wed,Thu"
DEFAULT_PRIMARY_COLOR = "#059669"  # 1.0.5 branding: emerald
DEFAULT_SECONDARY_COLOR = "#D97706"  # 1.0.5 branding: amber / gold accent


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(16), nullable=False)  # admin, teacher, student
    full_name = Column(String(120))
    phone = Column(String(20), nullable=True)  # 1.3.0: optional staff phone (teachers page); added by migrate()
    photo = Column(String, nullable=True)  # data:image/...;base64 staff photo
    is_active = Column(Boolean, default=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=True, index=True)
    must_change_password = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    last_login = Column(DateTime, nullable=True)


class SchoolSettings(Base):
    __tablename__ = "school_settings"
    id = Column(Integer, primary_key=True)
    # App / institution display name: login page, menu, browser tab, print headers. Chosen at first-run setup.
    name = Column(String(120), default=DEFAULT_APP_NAME)
    tagline = Column(String(160), nullable=True, default=DEFAULT_TAGLINE)
    logo_path = Column(String, nullable=True)  # data:image/...;base64 (validated)
    address = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=True)
    grading_scale = Column(String(16), default="standard")
    currency = Column(String(8), default="৳")
    # Working days of the routine, in display order (Bangladesh default: Saturday to Thursday).
    working_days = Column(String(32), default=DEFAULT_WORKING_DAYS)
    # 1.0.5 branding (Settings > Branding): colours applied site-wide, public landing page on/off,
    # default interface language (code of a row in `languages`).
    primary_color = Column(String(7), default=DEFAULT_PRIMARY_COLOR)
    secondary_color = Column(String(7), default=DEFAULT_SECONDARY_COLOR)
    landing_enabled = Column(Boolean, default=True)
    default_language = Column(String(10), default="en")


class AcademicYear(Base):
    __tablename__ = "academic_years"
    id = Column(Integer, primary_key=True)
    name = Column(String(32))
    is_current = Column(Boolean, default=True)


class Class(Base):
    __tablename__ = "classes"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    order = Column(Integer, default=0)
    sections = relationship("Section", back_populates="class_", order_by="Section.name")


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("class_id", "name", name="uq_section_class_name"),)
    id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=False)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    class_ = relationship("Class", back_populates="sections")


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(6), unique=True, index=True)  # 6-digit ID
    admission_no = Column(String(40), unique=True, index=True)
    name = Column(String(120), nullable=False)
    dob = Column(String(10), nullable=True)
    gender = Column(String(10), nullable=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="RESTRICT"), index=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="RESTRICT"), index=True)
    roll_no = Column(Integer, nullable=True)
    admission_date = Column(String(10))
    status = Column(String(16), default="Active")
    address = Column(String(255), nullable=True)
    guardian_name = Column(String(120))
    guardian_relation = Column(String(32), default="Father")
    guardian_phone = Column(String(20))
    guardian_address = Column(String(255), nullable=True)
    notes = Column(String(1000), nullable=True)
    photo = Column(String, nullable=True)  # data:image/...;base64 student photo
    created_at = Column(DateTime, default=utcnow)


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    code = Column(String(16), nullable=True)
    max_marks = Column(Float, default=100)
    pass_marks = Column(Float, default=33)
    credits = Column(Float, default=3.0)
    is_active = Column(Boolean, default=True)


class ClassSubject(Base):
    """Default subjects of a class. New students in the class get these automatically."""

    __tablename__ = "class_subjects"
    __table_args__ = (UniqueConstraint("class_id", "subject_id", name="uq_class_subject"),)
    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)


class StudentSubject(Base):
    __tablename__ = "student_subjects"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    is_active = Column(Boolean, default=True)


class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    name = Column(String(80))
    academic_year_id = Column(Integer, ForeignKey("academic_years.id", ondelete="SET NULL"), nullable=True, index=True)
    exam_date = Column(String(10), nullable=True)
    is_published = Column(Boolean, default=True)


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (Index("ix_marks_exam_student", "exam_id", "student_id"),)
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="RESTRICT"), index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), index=True)
    marks_obtained = Column(Float)
    max_marks = Column(Float, default=100)
    entered_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=utcnow)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (Index("ix_attendance_date_student", "date", "student_id"),)
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), index=True)
    date = Column(String(10))
    status = Column(String(10))  # Present, Absent, Late, Leave
    marked_by = Column(String(64))
    updated_at = Column(DateTime, default=utcnow)


class FeePlan(Base):
    __tablename__ = "fee_plans"
    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    fee_head = Column(String(64))
    amount = Column(Float)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_fee_month_student", "fee_month", "student_id"),)
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    amount = Column(Float)
    date = Column(String(10))
    fee_month = Column(String(7), nullable=True)  # YYYY-MM the payment is for
    fee_head = Column(String(64), default="Monthly Tuition")
    method = Column(String(20))
    receipt_no = Column(String(32), unique=True)
    note = Column(String(255), nullable=True)
    collected_by = Column(String(64))
    is_void = Column(Boolean, default=False)


class Period(Base):
    """One period of the school day (routine column), e.g. "1st period 08:00-08:45" or a tiffin break."""

    __tablename__ = "periods"
    id = Column(Integer, primary_key=True)
    name = Column(String(40), nullable=False)
    start_time = Column(String(5), nullable=False)  # HH:MM (24 h)
    end_time = Column(String(5), nullable=False)
    is_break = Column(Boolean, default=False)
    order = Column(Integer, default=0)


class TeacherSubject(Base):
    """Teacher assignment: who teaches a subject in a class (all sections, or one section)."""

    __tablename__ = "teacher_subjects"
    __table_args__ = (UniqueConstraint("class_id", "section_id", "subject_id", name="uq_teacher_subject_slot"),)
    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    # section_id NULL = every section of the class
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)


class RoutineSlot(Base):
    """Weekly class routine: class/section x day x period -> subject + teacher."""

    __tablename__ = "routine_slots"
    __table_args__ = (UniqueConstraint("section_id", "day", "period_id", name="uq_routine_section_day_period"),)
    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(String(3), nullable=False)  # Sat, Sun, Mon, Tue, Wed, Thu, Fri
    period_id = Column(Integer, ForeignKey("periods.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    room = Column(String(32), nullable=True)


class LoginAttempt(Base):
    """1.0.4: failed logins for the persistent login throttle (survives restarts, shared by workers)."""

    __tablename__ = "login_attempts"
    id = Column(Integer, primary_key=True)
    key = Column(String(200), nullable=False, index=True)  # "<ip>|<username lower-case>"
    attempted_at = Column(DateTime, nullable=False, index=True)


class SchemaMigration(Base):
    """1.0.2: one row per applied numbered migration (see app/database.py MIGRATIONS)."""

    __tablename__ = "schema_migrations"
    version = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String(120), nullable=False)
    applied_at = Column(DateTime, nullable=False)


class AppSetting(Base):
    """1.0.5: integration settings edited in Settings (SMTP, payment gateways, SMS), one row per field.

    key = "<section>.<field>", e.g. "smtp.host". Secret fields (passwords, API secrets) are stored
    encrypted (Fernet, key derived from SECRET_KEY, see app/secret_store.py) with is_secret=True and are
    never sent back to the browser.
    """

    __tablename__ = "app_settings"
    key = Column(String(80), primary_key=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Currency(Base):
    """1.0.5: currencies (Settings > Currencies). The default one is used for fees, receipts and reports;
    `rate` = value of 1 unit of the default currency in this currency (display conversion only)."""

    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True)
    code = Column(String(3), unique=True, nullable=False)  # ISO 4217, e.g. BDT
    name = Column(String(60), nullable=False)
    symbol = Column(String(8), nullable=False)
    rate = Column(Float, default=1.0)
    decimals = Column(Integer, default=2)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)


class Language(Base):
    """1.0.5: interface languages (Settings > Languages). Built-in catalogues: app/locales/<code>.json."""

    __tablename__ = "languages"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)  # e.g. en, bn, ar
    name = Column(String(60), nullable=False)
    native_name = Column(String(60), nullable=True)
    is_rtl = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)


class Translation(Base):
    """1.0.5: admin-edited text for one interface key in one language (overrides the built-in catalogue)."""

    __tablename__ = "translations"
    __table_args__ = (UniqueConstraint("language_code", "key", name="uq_translation_language_key"),)
    id = Column(Integer, primary_key=True)
    language_code = Column(String(10), ForeignKey("languages.code", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(120), nullable=False)
    text = Column(Text, nullable=False)
