"""JSON API used by the web UI, split by domain (1.0.4). Every route checks login + role; writes need CSRF.

SHARED GUARDS (app/security.py), visible on every route as a FastAPI dependency:
  * csrf_protect   - router-level dependency below: every POST/PUT/DELETE needs the X-CSRF-Token header.
  * require_admin  - admin only (all DELETE routes, fees, settings, accounts, classes, subjects, exams).
  * require_staff  - admin or teacher; teachers are then limited to their own classes/subjects
                     (services.teacher_scope / student_condition / can_enter_marks).
  * current_user   - any logged-in user; student records go through ensure_student_access (IDOR check).
Full table: docs/ROUTES.md. Evidence: docs/SECURITY-EVIDENCE.md.
"""

from fastapi import APIRouter, Depends

from ..security import csrf_protect
from . import (
    academics,
    accounts,
    attendance,
    dashboard,
    exams,
    fees,
    integrations,
    routine,
    school_settings,
    students,
)
from ._common import MAX_LOGO_BYTES, logo_from_upload

router = APIRouter(prefix="/api", dependencies=[Depends(csrf_protect)])
# Each route is registered on this router (prefix + csrf_protect) so router.routes lists every APIRoute
# with its full path; tests/test_auth.py walks that list to prove login, role and CSRF on every route.
for _module in (
    dashboard,
    students,
    exams,
    academics,
    attendance,
    fees,
    school_settings,
    integrations,
    accounts,
    routine,
):
    for _route in _module.router.routes:
        router.add_api_route(
            _route.path,
            _route.endpoint,
            methods=sorted(_route.methods),
            status_code=_route.status_code,
            name=_route.name,
        )

__all__ = ["MAX_LOGO_BYTES", "logo_from_upload", "router"]
