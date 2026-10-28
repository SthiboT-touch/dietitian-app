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
