"""1.0.5: interface languages (English, Bangla, Arabic built in; more can be added in Settings > Languages).

Text lookup order for a key: admin edits in the `translations` table -> the built-in catalogue
app/locales/<code>.json -> English (app/locales/en.json) -> the default written in the template.
Templates call ``t("key", "English text")``; JavaScript calls ``MA.t("key", "English text")`` with the same
catalogue (embedded in every page as JSON). Right-to-left languages (Arabic) set <html dir="rtl">.
The chosen language is kept in the session ("lang"); the school default is Settings > Languages.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Language, SchoolSettings, Translation

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
CODE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
KEY_RE = re.compile(r"^[a-z0-9_.-]{1,120}$")
BUILTIN_LANGUAGES = [
    # code, English name, native name, right-to-left
    ("en", "English", "English", False),
    ("bn", "Bangla", "বাংলা", False),
    ("ar", "Arabic", "العربية", True),
]
_cache: dict[str, dict[str, str]] = {}


@lru_cache(maxsize=16)
def builtin(code: str) -> dict[str, str]:
    """Built-in catalogue of one language ({} when there is none, e.g. a language the admin added)."""
    if not CODE_RE.match(code or ""):
        return {}
    path = LOCALES_DIR / f"{code}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str) and not k.startswith("_")}


@lru_cache(maxsize=1)
def js_keys() -> frozenset[str]:
    """Keys used by JavaScript (tools/extract_i18n.py writes the list); only these are embedded in pages."""
    path = LOCALES_DIR / "_js_keys.json"
    return frozenset(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else frozenset()


def for_js(cat: dict[str, str]) -> dict[str, str]:
    keys = js_keys()
    return {k: v for k, v in cat.items() if k in keys}


def base_keys() -> dict[str, str]:
    """Every translatable key with its English text (the list shown in the translation editor)."""
    return builtin("en")


def invalidate() -> None:
    _cache.clear()


def catalog(db: Session, code: str) -> dict[str, str]:
    if code in _cache:
        return _cache[code]
    merged = {**builtin("en"), **builtin(code)}
    for row in db.scalars(select(Translation).where(Translation.language_code == code)).all():
        if row.text:
            merged[row.key] = row.text
    _cache[code] = merged
    return merged


def languages(db: Session, active_only: bool = True) -> list[Language]:
    q = select(Language).order_by(Language.id)
    if active_only:
        q = q.where(Language.is_active.is_(True))
    return list(db.scalars(q).all())


def default_code(db: Session, school: SchoolSettings | None = None) -> str:
    row = db.scalars(select(Language).where(Language.is_default.is_(True), Language.is_active.is_(True))).first()
    if row:
        return row.code
    return (school.default_language if school and school.default_language else None) or "en"


def current(db: Session, session: dict, school: SchoolSettings | None = None) -> Language | None:
    """The visitor's language: session choice if still active, else the school default, else English."""
    active = {lang.code: lang for lang in languages(db)}
    code = session.get("lang") if isinstance(session, dict) or hasattr(session, "get") else None
    if code in active:
        return active[code]
    return active.get(default_code(db, school)) or active.get("en")


class Translator:
    """Callable used in templates: t("nav.students", "Students")."""

    def __init__(self, cat: dict[str, str]):
        self.cat = cat

    def __call__(self, key: str, default: str = "") -> str:
        return self.cat.get(key) or default or key
