"""School settings and logo.

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/settings                                        current_user
    POST   /api/settings                                        require_admin
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import grading, integrations, services, theme
from ..config import settings
from ..database import get_db
from ..models import (
    ALL_DAYS,
    DEFAULT_PRIMARY_COLOR,
    DEFAULT_SECONDARY_COLOR,
    Currency,
    User,
)
from ..schemas import (
    SettingsIn,
)
from ..security import (
    current_user,
    require_admin,
)
from ._common import (
    _validate_logo,
)

router = APIRouter()


# ------------------------------------------------------------------ settings & users
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = services.school(db)
    return {
        "name": s.name,
        "tagline": s.tagline or "",
        "logo": s.logo_path,
        "address": s.address or "",
        "phone": s.phone or "",
        "grading_scale": s.grading_scale or grading.DEFAULT_SCALE,
        "currency": s.currency or "৳",
        "scales": {k: v["label"] for k, v in grading.SCALES.items()},
        "working_days": services.working_days(db),
        "all_days": ALL_DAYS,
        "day_names": services.DAY_NAMES,
        # 1.0.5: branding, currencies for the display switcher, payment methods incl. enabled gateways
        "primary_color": s.primary_color if theme.valid_hex(s.primary_color) else DEFAULT_PRIMARY_COLOR,
        "secondary_color": s.secondary_color if theme.valid_hex(s.secondary_color) else DEFAULT_SECONDARY_COLOR,
        "landing_enabled": s.landing_enabled is not False,
        "default_language": s.default_language or "en",
        "currencies": [
            {
                "code": c.code,
                "symbol": c.symbol,
                "rate": c.rate,
                "decimals": c.decimals,
                "is_default": bool(c.is_default),
            }
            for c in db.scalars(select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.id)).all()
        ],
        "payment_methods": services.PAYMENT_METHODS[:7] + [g["label"] for g in integrations.enabled_gateways(db)],
        "demo_mode": settings.demo_auto_login,
    }


@router.post("/settings")
def update_settings(data: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = services.school(db)
    if data.name is not None:
        s.name = data.name
    if data.tagline is not None:
        s.tagline = data.tagline or None
    if data.address is not None:
        s.address = data.address
    if data.phone is not None:
        s.phone = data.phone
    if data.currency is not None:
        s.currency = data.currency or "৳"
    if data.grading_scale is not None:
        if data.grading_scale not in grading.SCALES:
            raise HTTPException(400, "Unknown grading scale")
        s.grading_scale = data.grading_scale
    if data.logo is not None:
        s.logo_path = _validate_logo(data.logo) if data.logo else None
    if data.working_days is not None:
        s.working_days = ",".join(data.working_days)
    if data.primary_color is not None:
        s.primary_color = data.primary_color.upper()
    if data.secondary_color is not None:
        s.secondary_color = data.secondary_color.upper()
    if data.landing_enabled is not None:
        s.landing_enabled = data.landing_enabled
    db.commit()
    return {"ok": True}
