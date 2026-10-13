"""Access rules: which signed-in user may see or change which patient's records."""
from typing import Optional

from fastapi import HTTPException

import config
import database
from security import Principal
from state import users_db


def client_dietitian_id(client_id: str) -> Optional[str]:
    """The dietitian a patient is linked to, or None if the patient is unknown or unlinked."""
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT dietitian_id FROM client WHERE client_id = %s", (client_id,))
            row = cursor.fetchone()
            return row["dietitian_id"] if row else None
    user = users_db.get(client_id)
    return user.get("dietitian_id") if user and user.get("type") == "client" else None


def require_client_access(principal: Principal, client_id: str) -> None:
    """Admins may see everyone, a patient only themselves, a dietitian only their linked patients."""
    if principal.role == "admin":
        return
    if principal.role == "client" and principal.id == client_id:
        return
    if principal.role == "dietitian" and client_dietitian_id(client_id) == principal.id:
        return
    raise HTTPException(status_code=403, detail="You do not have access to this patient's records")


def require_staff(principal: Principal) -> None:
    """Dietitians and admins only (patients are refused)."""
    if principal.role == "client":
        raise HTTPException(status_code=403, detail="This action is only available to dietitians")
