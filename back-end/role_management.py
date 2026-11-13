"""Central role registry for BRS staff roles.

This module deliberately grants no clinical-record access to new staff roles.
Permissions must be added explicitly to an endpoint after branch scoping is tested.
"""

from typing import Optional
from fastapi import Header, HTTPException
from security import current_identity

STAFF_ROLES = frozenset(
    {"reception", "branch_manager", "compliance_officer", "executive", "content_manager"}
)
BRANCH_REQUIRED_ROLES = frozenset({"reception", "branch_manager"})
ROLE_LABELS = {
    "admin": "System Administrator",
    "client": "Client",
    "dietitian": "Dietitian",
    "reception": "Reception Staff",
    "branch_manager": "Branch Manager",
    "compliance_officer": "Compliance Officer",
    "executive": "Executive",
    "content_manager": "Content Manager",
}


def require_roles(*allowed_roles):
    """Return a dependency enforcing the precise role list for a route."""
    if not allowed_roles or any(role not in ROLE_LABELS for role in allowed_roles):
        raise ValueError("Explicit valid roles are required")

    def check_role(authorization: Optional[str] = Header(default=None)):
        identity = current_identity(authorization)
        if identity[0] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return identity

    return check_role


def require_admin_or_branch_manager(authorization: Optional[str] = Header(default=None)):
    """Keep admin-route authentication semantics while allowing branch-scoped managers."""
    identity = current_identity(authorization)
    if identity[0] not in {"admin", "branch_manager"}:
        raise HTTPException(status_code=401, detail="Admin sign-in required")
    return identity


def branch_id_for_manager(staff_id: str) -> str:
    """Return the active branch assignment for a branch manager."""
    import config
    import database
    from state import branches_db, staff_accounts_db

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT branch_id FROM staff_account "
                "WHERE staff_id = %s AND role = 'branch_manager' AND is_active = TRUE",
                (staff_id,),
            )
            record = cursor.fetchone()
    else:
        staff = staff_accounts_db.get(staff_id)
        record = (
            {"branch_id": staff.get("branch_id")}
            if staff
            and staff.get("role") == "branch_manager"
            and staff.get("is_active")
            and staff.get("branch_id") in branches_db
            else None
        )
    if not record or not record.get("branch_id"):
        raise HTTPException(status_code=403, detail="No active branch assignment")
    return str(record["branch_id"])
