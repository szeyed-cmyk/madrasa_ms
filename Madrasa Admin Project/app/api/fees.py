"""Fee payments, receipts, voiding, fee plans and dues (admin only).

ACCESS GUARDS (every route; checked by tests/test_auth.py and tests/test_guards_v104.py):
  router-level: Depends(csrf_protect) on every write (app/api/__init__.py)
  per-route   : user: User = Depends(<guard>) as listed
    GET    /api/payments                                        require_admin
    POST   /api/payments                                        require_admin
    POST   /api/payments/{payment_id}/void                      require_admin
    GET    /api/receipt/{payment_id}                            require_admin
    GET    /api/fees/plans                                      require_admin
    PUT    /api/fees/plans                                      require_admin
    GET    /api/fees/dues                                       require_admin
"""

from __future__ import annotations

import secrets
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import (
    Class,
    FeePlan,
    Payment,
    Student,
    User,
)
from ..schemas import (
    FeePlanIn,
    PaymentIn,
)
from ..security import (
    require_admin,
)
from ._common import (
    _get,
)
from .academics import list_classes

router = APIRouter()


# ------------------------------------------------------------------ fees
@router.get("/payments")
def list_payments(
    student_id: int = 0,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    q = select(Payment)
    if student_id:
        q = q.where(Payment.student_id == student_id)
    pays = db.scalars(q.order_by(Payment.id.desc()).limit(limit)).all()
    return [services.payment_dict(p, db.get(Student, p.student_id)) for p in pays]


@router.post("/payments", status_code=201)
def create_payment(data: PaymentIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = _get(db, Student, data.student_id, "Student")
    today = date.today()
    p = Payment(
        student_id=s.id,
        amount=round(data.amount, 2),
        date=today.isoformat(),
        fee_month=data.fee_month or f"{today.year:04d}-{today.month:02d}",
        fee_head=data.fee_head,
        method=data.method,
        note=data.note,
        collected_by=user.username,
        is_void=False,
        receipt_no=f"TMP-{secrets.token_hex(6)}",
    )
    db.add(p)
    db.flush()
    receipt = f"RCP-{today.year}-{p.id:05d}"
    while db.scalars(select(Payment.id).where(Payment.receipt_no == receipt)).first():
        receipt = f"RCP-{today.year}-{p.id:05d}-{secrets.token_hex(2).upper()}"
    p.receipt_no = receipt
    db.commit()
    return {"id": p.id, "receipt_no": p.receipt_no}


@router.post("/payments/{payment_id}/void")
def void_payment(payment_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    p = _get(db, Payment, payment_id, "Payment")
    p.is_void = True
    p.note = ((p.note or "") + f" [voided by {user.username} {date.today().isoformat()}]").strip()[:255]
    db.commit()
    return {"ok": True}


@router.get("/receipt/{payment_id}")
def get_receipt(payment_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    p = _get(db, Payment, payment_id, "Payment")
    st = db.get(Student, p.student_id)
    classes, sections = services.class_maps(db)
    d = services.payment_dict(p, st)
    d["class_name"] = classes[st.class_id].name if st and st.class_id in classes else ""
    return d


@router.get("/fees/plans")
def fee_plans(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return [
        {"class_id": c["id"], "class_name": c["name"], "monthly_fee": c["monthly_fee"]} for c in list_classes(db, user)
    ]


@router.put("/fees/plans")
def set_fee_plan(data: FeePlanIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _get(db, Class, data.class_id, "Class")
    plans = db.scalars(
        select(FeePlan).where(FeePlan.class_id == data.class_id, FeePlan.fee_head == data.fee_head)
    ).all()
    if plans:
        plans[0].amount = data.amount
        for extra in plans[1:]:
            db.delete(extra)
    else:
        db.add(FeePlan(class_id=data.class_id, fee_head=data.fee_head, amount=data.amount))
    db.commit()
    return {"ok": True}


@router.get("/fees/dues")
def fee_dues(
    class_id: int = 0, only_due: bool = True, db: Session = Depends(get_db), user: User = Depends(require_admin)
):
    q = select(Student).where(func.lower(Student.status) == "active")
    if class_id:
        q = q.where(Student.class_id == class_id)
    classes, sections = services.class_maps(db)
    rows = []
    for s in db.scalars(q.order_by(Student.class_id, Student.roll_no, Student.name)).all():
        fs = services.fee_status(db, s)
        if only_due and fs["due"] <= 0:
            continue
        rows.append(
            {
                "id": s.id,
                "name": s.name,
                "student_id": s.student_id,
                "guardian_phone": s.guardian_phone,
                "class_name": classes[s.class_id].name if s.class_id in classes else "",
                **fs,
            }
        )
    return rows
