"""Request bodies with validation."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import ALL_DAYS
from .services import ATTENDANCE_STATUSES, PAYMENT_METHODS, PHONE_RE, STUDENT_STATUSES

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _date_str(v):
    v = _clean(v)
    if v is None:
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError as exc:
        raise ValueError("Use a date in YYYY-MM-DD format") from exc


class Strict(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class StudentIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    class_id: int = Field(gt=0)
    section_id: int = Field(gt=0)
    student_id: str | None = Field(default=None, max_length=6)
    admission_no: str | None = Field(default=None, max_length=40)
    dob: str | None = None
    gender: str | None = Field(default=None, max_length=10)
    roll_no: int | None = Field(default=None, ge=0, le=100000)
    admission_date: str | None = None
    status: str = "Active"
    address: str | None = Field(default=None, max_length=255)
    guardian_name: str | None = Field(default=None, max_length=120)
    guardian_relation: str | None = Field(default=None, max_length=32)
    guardian_phone: str | None = Field(default=None, max_length=20)
    guardian_address: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=1000)
    photo: str | None = Field(default=None, max_length=500000)
    apply_class_subjects: bool = True

    _c = field_validator(
        "student_id",
        "admission_no",
        "gender",
        "address",
        "guardian_name",
        "guardian_relation",
        "guardian_phone",
        "guardian_address",
        "notes",
        mode="before",
    )(_clean)
    _d = field_validator("dob", "admission_date", mode="before")(_date_str)

    @field_validator("roll_no", mode="before")
    @classmethod
    def _roll(cls, v):
        return None if v in ("", None) else v

    @field_validator("student_id")
    @classmethod
    def _sid(cls, v):
        if v is None:
            return None
        if not v.isdigit():
            raise ValueError("Student ID must be digits only (up to 6)")
        return v.zfill(6)

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in STUDENT_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(STUDENT_STATUSES)}")
        return v

    @field_validator("gender")
    @classmethod
    def _gender(cls, v):
        if v is not None and v not in ("Male", "Female", "Other"):
            raise ValueError("Gender must be Male, Female or Other")
        return v

    @field_validator("guardian_phone")
    @classmethod
    def _phone(cls, v):
        if v is not None and not PHONE_RE.match(v):
            raise ValueError("Phone must contain 6-19 digits (optionally starting with +)")
        return v


class StatusIn(Strict):
    status: str

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in STUDENT_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(STUDENT_STATUSES)}")
        return v


class NameIn(Strict):
    name: str = Field(min_length=1, max_length=64)


class ClassIn(Strict):
    name: str = Field(min_length=1, max_length=64)
    order: int | None = Field(default=None, ge=0, le=100000)


class SectionIn(Strict):
    class_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=32)


class SubjectIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    code: str | None = Field(default=None, max_length=16)
    max_marks: float = Field(default=100, gt=0, le=1000)
    pass_marks: float | None = Field(default=33, ge=0, le=1000)
    credits: float = Field(default=3.0, ge=0, le=20)
    is_active: bool = True
    class_ids: list[int] | None = None

    _c = field_validator("code", mode="before")(_clean)

    @field_validator("pass_marks")
    @classmethod
    def _pass(cls, v, info):
        mx = info.data.get("max_marks")
        if v is not None and mx is not None and v > mx:
            raise ValueError("Pass marks cannot be more than full marks")
        return v


class SubjectIdsIn(Strict):
    subject_ids: list[int] = Field(default_factory=list, max_length=200)


class SubjectIdIn(Strict):
    subject_id: int = Field(gt=0)


class ExamIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    exam_date: str | None = None
    is_published: bool = False

    _d = field_validator("exam_date", mode="before")(_date_str)


class MarkIn(Strict):
    exam_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    marks: float | None = Field(default=None, ge=0)

    @field_validator("marks", mode="before")
    @classmethod
    def _empty(cls, v):
        return None if v == "" else v


class MarkEntry(Strict):
    student_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    marks: float | None = Field(default=None, ge=0)

    @field_validator("marks", mode="before")
    @classmethod
    def _empty(cls, v):
        return None if v == "" else v


class MarksBulkIn(Strict):
    exam_id: int = Field(gt=0)
    entries: list[MarkEntry] = Field(max_length=5000)


class AttendanceRecord(Strict):
    student_id: int = Field(gt=0)
    status: str

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in ATTENDANCE_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(ATTENDANCE_STATUSES)}")
        return v


class AttendanceIn(Strict):
    date: str
    records: list[AttendanceRecord] = Field(max_length=2000)

    _d = field_validator("date", mode="before")(_date_str)

    @field_validator("date")
    @classmethod
    def _not_future(cls, v):
        if v is None:
            raise ValueError("Date is required")
        if date.fromisoformat(v) > date.today():
            raise ValueError("Attendance cannot be saved for a future date")
        return v


class PaymentIn(Strict):
    student_id: int = Field(gt=0)
    amount: float = Field(gt=0, le=10_000_000)
    method: str = "Cash"
    fee_month: str | None = None
    fee_head: str = Field(default="Monthly Tuition", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=255)

    _c = field_validator("fee_month", "note", mode="before")(_clean)

    @field_validator("method")
    @classmethod
    def _method(cls, v):
        if v not in PAYMENT_METHODS:
            raise ValueError(f"Method must be one of {', '.join(PAYMENT_METHODS)}")
        return v

    @field_validator("fee_month")
    @classmethod
    def _month(cls, v):
        if v is not None and not MONTH_RE.match(v):
            raise ValueError("Fee month must be YYYY-MM")
        return v


class FeePlanIn(Strict):
    class_id: int = Field(gt=0)
    amount: float = Field(ge=0, le=10_000_000)
    fee_head: str = Field(default="Monthly Tuition", min_length=1, max_length=64)


class SettingsIn(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tagline: str | None = Field(default=None, max_length=160)  # "" clears it
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    logo: str | None = None
    grading_scale: str | None = None
    currency: str | None = Field(default=None, max_length=8)
    working_days: list[str] | None = Field(default=None, max_length=7)
    # 1.0.5 branding
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    landing_enabled: bool | None = None

    @field_validator("working_days")
    @classmethod
    def _days(cls, v):
        if v is None:
            return v
        bad = [d for d in v if d not in ALL_DAYS]
        if bad:
            raise ValueError(f"Days must be among {', '.join(ALL_DAYS)}")
        if not v:
            raise ValueError("Choose at least one working day")
        return [d for d in ALL_DAYS if d in v]


class LoginCreateIn(Strict):
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)

    _c = field_validator("username", "password", mode="before")(_clean)


class UserIn(Strict):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    role: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ("admin", "teacher"):
            raise ValueError("Role must be admin or teacher")
        return v


class UserUpdateIn(Strict):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=128)

    _c = field_validator("password", mode="before")(_clean)


USERNAME_PATTERN = r"^[A-Za-z0-9_.\-]+$"


def _phone_ok(v):
    if v is not None and not PHONE_RE.match(v):
        raise ValueError("Phone must contain 6-19 digits (optionally starting with +)")
    return v


class TeacherIn(Strict):
    """1.3.0 Teachers page: add a teacher. Blank password = the server generates a temporary one."""

    full_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=64, pattern=USERNAME_PATTERN)
    phone: str | None = Field(default=None, max_length=20)
    password: str | None = Field(default=None, max_length=128)
    photo: str | None = Field(default=None, max_length=500000)

    _c = field_validator("phone", "password", mode="before")(_clean)
    _p = field_validator("phone")(_phone_ok)


class TeacherUpdateIn(Strict):
    full_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=64, pattern=USERNAME_PATTERN)
    phone: str | None = Field(default=None, max_length=20)
    photo: str | None = Field(default=None, max_length=500000)

    _c = field_validator("phone", mode="before")(_clean)
    _p = field_validator("phone")(_phone_ok)


class PasswordResetIn(Strict):
    password: str | None = Field(default=None, max_length=128)  # blank = generate a temporary password

    _c = field_validator("password", mode="before")(_clean)


class ActiveIn(Strict):
    is_active: bool


class BulkLoginIn(Strict):
    class_id: int = Field(gt=0)
    section_id: int | None = Field(default=None, gt=0)
    reset_existing: bool = False  # also give students who already have a login a new temporary password

    @field_validator("section_id", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if v in ("", 0, "0") else v


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PeriodIn(Strict):
    name: str = Field(min_length=1, max_length=40)
    start_time: str
    end_time: str
    is_break: bool = False
    order: int | None = Field(default=None, ge=0, le=1000)

    @field_validator("start_time", "end_time")
    @classmethod
    def _time(cls, v):
        if not TIME_RE.match(v):
            raise ValueError("Use a time in HH:MM (24-hour) format")
        return v

    @model_validator(mode="after")
    def _order(self):
        if self.end_time <= self.start_time:
            raise ValueError("The period must end after it starts")
        return self


class AssignmentIn(Strict):
    teacher_id: int = Field(gt=0)
    class_id: int = Field(gt=0)
    section_id: int | None = Field(default=None, gt=0)  # empty = every section of the class
    subject_id: int = Field(gt=0)

    @field_validator("section_id", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if v in ("", 0, "0") else v


class SlotIn(Strict):
    class_id: int = Field(gt=0)
    section_id: int = Field(gt=0)
    day: str
    period_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    teacher_id: int | None = Field(default=None, gt=0)  # empty = the assigned teacher
    room: str | None = Field(default=None, max_length=32)

    _c = field_validator("room", mode="before")(_clean)

    @field_validator("teacher_id", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if v in ("", 0, "0") else v

    @field_validator("day")
    @classmethod
    def _day(cls, v):
        if v not in ALL_DAYS:
            raise ValueError(f"Day must be one of {', '.join(ALL_DAYS)}")
        return v


# ---------------------------------------------------------------- 1.0.5: currencies and languages
class CurrencyIn(Strict):
    code: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    name: str = Field(min_length=1, max_length=60)
    symbol: str = Field(min_length=1, max_length=8)
    rate: float = Field(default=1.0, gt=0, le=1_000_000)
    decimals: int = Field(default=2, ge=0, le=4)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _upper(cls, v):
        return v.upper()


class LanguageIn(Strict):
    code: str = Field(min_length=2, max_length=10, pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
    name: str = Field(min_length=1, max_length=60)
    native_name: str | None = Field(default=None, max_length=60)
    is_rtl: bool = False
    is_active: bool = True


class TranslationsIn(Strict):
    """{key: text} for one language; an empty text removes the override (built-in text is used again)."""

    items: dict[str, str] = Field(max_length=2000)

    @field_validator("items")
    @classmethod
    def _items(cls, v):
        for key, text in v.items():
            if not re.match(r"^[a-z0-9_.-]{1,120}$", key):
                raise ValueError(f"Invalid key {key[:40]!r}")
            if len(text) > 2000:
                raise ValueError(f"{key}: max. 2000 characters")
        return v


class TestEmailIn(Strict):
    to: str = Field(min_length=3, max_length=254)
