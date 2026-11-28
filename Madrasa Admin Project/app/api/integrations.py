"""1.0.5: Settings > Email (SMTP), Payments, SMS, Currencies and Languages.

ACCESS GUARDS (every route; checked by tests/test_auth.py, tests/test_guards_v104.py and tests/test_v105.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/config/{section}                                require_admin
    PUT    /api/config/{section}                                require_admin
    POST   /api/config/smtp/test                                require_admin
    GET    /api/currencies                                      current_user
    POST   /api/currencies                                      require_admin
    PUT    /api/currencies/{currency_id}                        require_admin
    DELETE /api/currencies/{currency_id}                        require_admin
    POST   /api/currencies/{currency_id}/default                require_admin
    GET    /api/languages                                       current_user
    POST   /api/languages                                       require_admin
    PUT    /api/languages/{language_id}                         require_admin
    DELETE /api/languages/{language_id}                         require_admin
    POST   /api/languages/{language_id}/default                 require_admin
    GET    /api/languages/{language_id}/translations            require_admin
    PUT    /api/languages/{language_id}/translations            require_admin
Secrets: GET returns "" + "<field>_set"; demo mode never stores them and cannot send email (app/integrations.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import i18n, integrations, services
from ..config import settings
from ..database import get_db
from ..models import Currency, Language, Translation, User
from ..schemas import CurrencyIn, LanguageIn, TestEmailIn, TranslationsIn
from ..security import current_user, require_admin
from ._common import _get

router = APIRouter()


# ------------------------------------------------------------------ integration settings
@router.get("/config/{section}")
def get_config(section: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    data = integrations.get_section(db, section)
    data["demo_mode"] = settings.demo_auto_login
    return data


@router.put("/config/{section}")
def save_config(
    section: str, data: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    data = {k: v for k, v in data.items() if k != "demo_mode"}
    result = integrations.save_section(db, section, data, demo_mode=settings.demo_auto_login)
    return {"ok": True, **result}


@router.post("/config/smtp/test")
def smtp_test(data: TestEmailIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if settings.demo_auto_login:
        raise HTTPException(403, "Sending email is switched off in the public demo. Your own installation sends it.")
    school = services.school(db)
    integrations.smtp_send(
        db,
        data.to,
        f"{school.name}: test email",
        f"This is a test email from {school.name}. Your SMTP settings work.",
    )
    return {"ok": True}


# ------------------------------------------------------------------ currencies
def _currency_dict(c: Currency) -> dict:
    return {
        "id": c.id,
        "code": c.code,
        "name": c.name,
        "symbol": c.symbol,
        "rate": c.rate,
        "decimals": c.decimals,
        "is_default": bool(c.is_default),
        "is_active": bool(c.is_active),
    }


@router.get("/currencies")
def list_currencies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_currency_dict(c) for c in db.scalars(select(Currency).order_by(Currency.id)).all()]


def _unique_code(db: Session, code: str, own_id: int | None = None) -> None:
    other = db.scalars(select(Currency).where(func.upper(Currency.code) == code.upper())).first()
    if other and other.id != own_id:
        raise HTTPException(400, f"Currency {code} already exists")


@router.post("/currencies")
def add_currency(data: CurrencyIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _unique_code(db, data.code)
    c = Currency(**data.model_dump(), is_default=False)
    db.add(c)
    db.commit()
    return _currency_dict(c)


@router.put("/currencies/{currency_id}")
def edit_currency(
    currency_id: int, data: CurrencyIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    c = _get(db, Currency, currency_id, "Currency")
    _unique_code(db, data.code, c.id)
    if c.is_default and not data.is_active:
        raise HTTPException(400, "The default currency cannot be switched off. Make another one the default first.")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    if c.is_default:
        c.rate = 1.0
        services.school(db).currency = c.symbol
    db.commit()
    return _currency_dict(c)


@router.delete("/currencies/{currency_id}")
def delete_currency(currency_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    c = _get(db, Currency, currency_id, "Currency")
    if c.is_default:
        raise HTTPException(400, "The default currency cannot be deleted. Make another one the default first.")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/currencies/{currency_id}/default")
def default_currency(currency_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Make this the school currency (fees, receipts, reports). Other rates are re-based on it."""
    c = _get(db, Currency, currency_id, "Currency")
    if not c.is_active:
        raise HTTPException(400, "Switch the currency on first")
    base = c.rate or 1.0
    for other in db.scalars(select(Currency)).all():
        other.is_default = other.id == c.id
        other.rate = 1.0 if other.id == c.id else round((other.rate or 1.0) / base, 6)
    services.school(db).currency = c.symbol
    db.commit()
    return _currency_dict(c)


# ------------------------------------------------------------------ languages
def _language_dict(lang: Language) -> dict:
    return {
        "id": lang.id,
        "code": lang.code,
        "name": lang.name,
        "native_name": lang.native_name or "",
        "is_rtl": bool(lang.is_rtl),
        "is_active": bool(lang.is_active),
        "is_default": bool(lang.is_default),
        "builtin": bool(i18n.builtin(lang.code)),
    }


@router.get("/languages")
def list_languages(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_language_dict(x) for x in i18n.languages(db, active_only=False)]


@router.post("/languages")
def add_language(data: LanguageIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.scalars(select(Language).where(Language.code == data.code)).first():
        raise HTTPException(400, f"Language {data.code} already exists")
    lang = Language(**data.model_dump(), is_default=False)
    db.add(lang)
    db.commit()
    i18n.invalidate()
    return _language_dict(lang)


@router.put("/languages/{language_id}")
def edit_language(
    language_id: int, data: LanguageIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    lang = _get(db, Language, language_id, "Language")
    if data.code != lang.code:
        raise HTTPException(400, "The language code cannot be changed. Add a new language instead.")
    if lang.is_default and not data.is_active:
        raise HTTPException(400, "The default language cannot be switched off. Make another one the default first.")
    lang.name, lang.native_name, lang.is_rtl, lang.is_active = data.name, data.native_name, data.is_rtl, data.is_active
    db.commit()
    i18n.invalidate()
    return _language_dict(lang)


@router.delete("/languages/{language_id}")
def delete_language(language_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lang = _get(db, Language, language_id, "Language")
    if lang.is_default:
        raise HTTPException(400, "The default language cannot be deleted. Make another one the default first.")
    if lang.code == "en":
        raise HTTPException(400, "English is the base language and cannot be deleted (you can switch it off).")
    db.execute(delete(Translation).where(Translation.language_code == lang.code))
    db.delete(lang)
    db.commit()
    i18n.invalidate()
    return {"ok": True}


@router.post("/languages/{language_id}/default")
def default_language(language_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    lang = _get(db, Language, language_id, "Language")
    if not lang.is_active:
        raise HTTPException(400, "Switch the language on first")
    for other in db.scalars(select(Language)).all():
        other.is_default = other.id == lang.id
    services.school(db).default_language = lang.code
    db.commit()
    i18n.invalidate()
    return _language_dict(lang)


@router.get("/languages/{language_id}/translations")
def get_translations(language_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Every interface key: English text, built-in translation and the admin's own text (if any)."""
    lang = _get(db, Language, language_id, "Language")
    own = {r.key: r.text for r in db.scalars(select(Translation).where(Translation.language_code == lang.code)).all()}
    built = i18n.builtin(lang.code)
    return {
        "language": _language_dict(lang),
        "items": [
            {"key": k, "english": v, "builtin": built.get(k, ""), "custom": own.get(k, "")}
            for k, v in sorted(i18n.base_keys().items())
        ],
    }


@router.put("/languages/{language_id}/translations")
def save_translations(
    language_id: int, data: TranslationsIn, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    lang = _get(db, Language, language_id, "Language")
    known = i18n.base_keys()
    unknown = [k for k in data.items if k not in known]
    if unknown:
        raise HTTPException(400, f"Unknown key(s): {', '.join(unknown[:5])}")
    rows = {r.key: r for r in db.scalars(select(Translation).where(Translation.language_code == lang.code)).all()}
    changed = 0
    for key, text in data.items.items():
        text = text.strip()
        row = rows.get(key)
        if not text:
            if row is not None:
                db.delete(row)
                changed += 1
            continue
        if row is None:
            db.add(Translation(language_code=lang.code, key=key, text=text))
        elif row.text != text:
            row.text = text
        else:
            continue
        changed += 1
    db.commit()
    i18n.invalidate()
    return {"ok": True, "changed": changed}
