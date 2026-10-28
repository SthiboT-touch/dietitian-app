"""Staff directory and restricted administrator provisioning.

This is a backend foundation for the extra BRS roles. No staff role receives
client health record privileges or broad administrator permissions by default.
"""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import config
import database
from role_management import STAFF_ROLES, BRANCH_REQUIRED_ROLES, ROLE_LABELS, require_roles
from security import hash_password
from state import branches_db, staff_accounts_db, staff_sessions_db, users_db, admins_db

router = APIRouter(tags=["Staff Roles & Permissions"])
StaffRole = Literal[
    "reception", "branch_manager", "compliance_officer", "executive", "content_manager"
]


class StaffCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role: StaffRole
    branch_id: Optional[str] = None


class StaffUpdate(BaseModel):
    role: StaffRole
    branch_id: Optional[str] = None
    is_active: bool


def _present(row):
    return {
        key: value for key, value in dict(row).items() if key not in ("password_hash", "password")
    }


def _check_branch(role, branch_id):
    if role in BRANCH_REQUIRED_ROLES and not branch_id:
        raise HTTPException(status_code=422, detail="This role requires a branch_id")
    if not branch_id:
        return
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT 1 FROM branch WHERE branch_id = %s", (branch_id,))
            found = cursor.fetchone()
    else:
        found = branches_db.get(branch_id)
    if not found:
        raise HTTPException(status_code=422, detail="Branch does not exist")


def _ensure_unique_email(email):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM client WHERE LOWER(email) = LOWER(%s) "
                "UNION ALL SELECT 1 FROM dietitian WHERE LOWER(email) = LOWER(%s) "
                "UNION ALL SELECT 1 FROM admin WHERE LOWER(email) = LOWER(%s) "
                "UNION ALL SELECT 1 FROM staff_account WHERE LOWER(email) = LOWER(%s) LIMIT 1",
                (email, email, email, email),
            )
            taken = cursor.fetchone() is not None
    else:
        taken = any(
            u.get("email", "").casefold() == email.casefold()
            for u in list(users_db.values())
            + list(admins_db.values())
            + list(staff_accounts_db.values())
        )
    if taken:
        raise HTTPException(status_code=409, detail="An account with this email already exists")


@router.get("/api/v1/auth/roles")
def list_available_roles(identity=Depends(require_roles("admin"))):
    """Administrative view of available roles, not access to clinical records."""
    return [{"role": k, "label": v} for k, v in ROLE_LABELS.items()]


@router.get("/api/v1/staff/me")
def my_staff_profile(identity=Depends(require_roles(*sorted(STAFF_ROLES)))):
    _, staff_id = identity
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT staff_id, full_name, email, role, branch_id, is_active "
                "FROM staff_account WHERE staff_id = %s",
                (staff_id,),
            )
            record = cursor.fetchone()
    else:
        record = staff_accounts_db.get(staff_id)
    if not record or not record.get("is_active", False):
        raise HTTPException(status_code=401, detail="Staff account is not active")
    return _present(record)


@router.get("/api/v1/admin/staff")
def list_staff(identity=Depends(require_roles("admin"))):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT staff_id, full_name, email, role, branch_id, is_active "
                "FROM staff_account ORDER BY LOWER(full_name)"
            )
            return [dict(row) for row in cursor.fetchall()]
    return sorted(
        (_present(r) for r in staff_accounts_db.values()), key=lambda r: r["full_name"].casefold()
    )


@router.post("/api/v1/admin/staff", status_code=201)
def create_staff(data: StaffCreate, identity=Depends(require_roles("admin"))):
    email = data.email.strip().lower()
    name = data.full_name.strip()
    if not name or not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Valid full name and email are required")
    _check_branch(data.role, data.branch_id)
    _ensure_unique_email(email)
    record = {
        "staff_id": str(uuid.uuid4()),
        "full_name": name,
        "email": email,
        "password_hash": hash_password(data.password),
        "role": data.role,
        "branch_id": data.branch_id,
        "is_active": True,
    }
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staff_account "
                "(staff_id, full_name, email, password_hash, role, branch_id, is_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
                (
                    record["staff_id"],
                    name,
                    email,
                    record["password_hash"],
                    data.role,
                    data.branch_id,
                ),
            )
    else:
        staff_accounts_db[record["staff_id"]] = record
    return _present(record)


@router.put("/api/v1/admin/staff/{staff_id}")
def update_staff(staff_id: str, data: StaffUpdate, identity=Depends(require_roles("admin"))):
    _check_branch(data.role, data.branch_id)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "UPDATE staff_account SET role = %s, branch_id = %s, is_active = %s, "
                "updated_at = NOW() WHERE staff_id = %s "
                "RETURNING staff_id, full_name, email, role, branch_id, is_active",
                (data.role, data.branch_id, data.is_active, staff_id),
            )
            record = cursor.fetchone()
    else:
        record = staff_accounts_db.get(staff_id)
        if record:
            record.update(role=data.role, branch_id=data.branch_id, is_active=data.is_active)
    if not record:
        raise HTTPException(status_code=404, detail="Staff account not found")
    # Changes take effect immediately: old sessions cannot retain an outdated role.
    for token, account in list(staff_sessions_db.items()):
        if account == staff_id:
            staff_sessions_db.pop(token, None)
    return _present(record)
