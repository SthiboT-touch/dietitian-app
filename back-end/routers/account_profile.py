"""Self-service account profiles shared by all eight NutriCare roles.

No role can read or alter another user's account from these endpoints. Clinical
records, assignments, approvals and account emails are deliberately read-only.
Requires additive migration 020 on PostgreSQL; memory mode needs no migration.
"""

from __future__ import annotations

import io
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator

import config
import database
from role_management import ROLE_LABELS, require_roles
from security import current_identity, hash_password, verify_password
from state import (
    account_profiles_db, admin_sessions_db, client_sessions_db,
    dietitian_sessions_db, staff_sessions_db, admins_db, staff_accounts_db, users_db,
    profile_photos_db,
)

router = APIRouter(prefix="/api/v1/account", tags=["Account Profile"])
identity_required = require_roles(*ROLE_LABELS.keys())
MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone_number: Optional[str] = Field(default=None, max_length=30)
    address: Optional[str] = Field(default=None, max_length=240)
    emergency_contact: Optional[str] = Field(default=None, max_length=120)
    bio: Optional[str] = Field(default=None, max_length=500)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if len(value) < 2 or not any(ch.isalpha() for ch in value):
            raise ValueError("Enter a valid full name")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("Invalid name")
        return value

    @field_validator("phone_number")
    @classmethod
    def clean_phone(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"[+\d ()-]{7,30}", value) or len(re.sub(r"\D", "", value)) < 7:
            raise ValueError("Enter a valid contact number")
        return value

    @field_validator("address", "emergency_contact", "bio")
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        return value.strip() or None


class PreferenceUpdate(BaseModel):
    preferred_contact: Literal["email", "phone"] = "email"
    email_notifications: bool = True
    appointment_reminders: bool = True


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


ACCOUNT_SELECT = {
    "client": (
        "SELECT client_id AS id, name AS full_name, email, phone_number, gender, "
        "date_of_birth, id_number, dietitian_id, 'ACTIVE' AS status "
        "FROM client WHERE client_id = %s"
    ),
    "dietitian": (
        "SELECT dietitian_id AS id, TRIM(first_name || ' ' || last_name) AS full_name, "
        "email, branch_id, registration_number AS license_number, specialisation, status "
        "FROM dietitian WHERE dietitian_id = %s"
    ),
    "admin": (
        "SELECT admin_id AS id, TRIM(first_name || ' ' || last_name) AS full_name, "
        "email, role FROM admin WHERE admin_id = %s"
    ),
    "staff": (
        "SELECT staff_id AS id, full_name, email, role, branch_id, is_active "
        "FROM staff_account WHERE staff_id = %s"
    ),
}


def _account(identity):
    role, account_id = identity
    if config.DATABASE_ENABLED:
        key = role if role in ("client", "dietitian", "admin") else "staff"
        with database.cursor() as cursor:
            cursor.execute(ACCOUNT_SELECT[key], (account_id,))
            row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Account not found")
        if key == "staff" and not row["is_active"]:
            raise HTTPException(403, "Account inactive")
        return dict(row)
    if role == "admin":
        record = admins_db.get(account_id)
    elif role in ("client", "dietitian"):
        record = users_db.get(account_id)
    else:
        record = staff_accounts_db.get(account_id)
    if not record:
        raise HTTPException(404, "Account not found")
    if role not in {"admin", "client", "dietitian"} and not record.get("is_active", True):
        raise HTTPException(403, "Account inactive")
    return {
        "id": account_id, "full_name": record.get("full_name", ""),
        "email": record.get("email", ""), "phone_number": record.get("phone_number"),
        **{k: record.get(k) for k in (
            "gender", "date_of_birth", "id_number", "dietitian_id", "branch_id",
            "license_number", "specialisation", "status", "role", "is_active",
        ) if k in record},
    }


def _details(identity, with_photo=False):
    role, account_id = identity
    if config.DATABASE_ENABLED:
        columns = ("phone_number, address, emergency_contact, bio, preferred_contact, "
                   "email_notifications, appointment_reminders, photo_data IS NOT NULL AS has_photo, photo_hidden")
        with database.cursor() as cursor:
            cursor.execute(f"SELECT {columns} FROM account_profile WHERE account_role=%s AND account_id=%s", (role, account_id))
            row = cursor.fetchone()
        return dict(row) if row else {}
    data = account_profiles_db.get((role, account_id), {})
    return {**{k: v for k, v in data.items() if k != "photo_data"}, "has_photo": bool(data.get("photo_data"))}


def _save_details(identity, values):
    role, account_id = identity
    if config.DATABASE_ENABLED:
        fields = list(values)
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO account_profile (account_role, account_id) VALUES (%s,%s) "
                "ON CONFLICT (account_role, account_id) DO NOTHING", (role, account_id)
            )
            cursor.execute(
                "UPDATE account_profile SET " + ", ".join(f"{field}=%s" for field in fields)
                + ", updated_at=NOW() WHERE account_role=%s AND account_id=%s",
                tuple(values.values()) + (role, account_id),
            )
    else:
        account_profiles_db.setdefault((role, account_id), {}).update(values)


def _update_name(identity, name):
    role, account_id = identity
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            if role == "client":
                cursor.execute("UPDATE client SET name=%s WHERE client_id=%s", (name, account_id))
            elif role in ("admin", "dietitian"):
                parts = name.split(" ", 1)
                table, id_field = ("admin", "admin_id") if role == "admin" else ("dietitian", "dietitian_id")
                cursor.execute(
                    f"UPDATE {table} SET first_name=%s, last_name=%s WHERE {id_field}=%s",
                    (parts[0], parts[1] if len(parts) > 1 else "", account_id),
                )
            else:
                cursor.execute("UPDATE staff_account SET full_name=%s WHERE staff_id=%s", (name, account_id))
    else:
        store = (admins_db if role == "admin" else users_db if role in ("client", "dietitian") else staff_accounts_db)
        store[account_id]["full_name"] = name


def _profile_payload(identity):
    account = _account(identity)
    details = _details(identity)
    role = identity[0]
    return {
        **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in account.items()},
        "role": role, "role_label": ROLE_LABELS.get(role, "Team member"),
        "phone_number": details.get("phone_number") or account.get("phone_number"),
        "address": details.get("address"),
        "emergency_contact": details.get("emergency_contact"),
        "bio": details.get("bio"),
        "preferred_contact": details.get("preferred_contact", "email"),
        "email_notifications": details.get("email_notifications", True),
        "appointment_reminders": details.get("appointment_reminders", True),
        "has_photo": bool(details.get("has_photo") or (role == "client" and not details.get("photo_hidden") and _legacy_photo(identity))),
    }


@router.get("/me")
def get_profile(response: Response, identity=Depends(identity_required)):
    response.headers["Cache-Control"] = "private, no-store"
    return _profile_payload(identity)


@router.put("/me")
def save_profile(data: ProfileUpdate, identity=Depends(identity_required)):
    _account(identity)
    if identity[0] != "client" and data.emergency_contact:
        raise HTTPException(422, "Emergency contact is available for patient profiles")
    _update_name(identity, data.full_name)
    values = data.model_dump(exclude={"full_name"})
    _save_details(identity, values)
    return _profile_payload(identity)


@router.put("/preferences")
def save_preferences(data: PreferenceUpdate, identity=Depends(identity_required)):
    _account(identity)
    _save_details(identity, data.model_dump())
    return _profile_payload(identity)


def _password_record(identity):
    role, account_id = identity
    if config.DATABASE_ENABLED:
        table, pk, password_col = {
            "client": ("client", "client_id", "password"),
            "dietitian": ("dietitian", "dietitian_id", "password"),
            "admin": ("admin", "admin_id", "password"),
        }.get(role, ("staff_account", "staff_id", "password_hash"))
        with database.cursor() as cursor:
            cursor.execute(f"SELECT {password_col} AS password_hash FROM {table} WHERE {pk}=%s", (account_id,))
            row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Account not found")
        return row["password_hash"]
    store = (admins_db if role == "admin" else users_db if role in ("client", "dietitian") else staff_accounts_db)
    record = store.get(account_id)
    if not record:
        raise HTTPException(404, "Account not found")
    return record.get("password_hash", "")


@router.post("/password")
def change_password(data: PasswordUpdate, identity=Depends(identity_required)):
    old_hash = _password_record(identity)
    if not verify_password(data.current_password, old_hash):
        raise HTTPException(400, "Current password is incorrect")
    if verify_password(data.new_password, old_hash):
        raise HTTPException(422, "Choose a different password")
    new_hash = hash_password(data.new_password)
    role, account_id = identity
    if config.DATABASE_ENABLED:
        table, pk, password_col = {
            "client": ("client", "client_id", "password"),
            "dietitian": ("dietitian", "dietitian_id", "password"),
            "admin": ("admin", "admin_id", "password"),
        }.get(role, ("staff_account", "staff_id", "password_hash"))
        with database.cursor() as cursor:
            cursor.execute(f"UPDATE {table} SET {password_col}=%s WHERE {pk}=%s", (new_hash, account_id))
    else:
        store = (admins_db if role == "admin" else users_db if role in ("client", "dietitian") else staff_accounts_db)
        store[account_id]["password_hash"] = new_hash
    sessions = (admin_sessions_db if role == "admin" else client_sessions_db if role == "client" else dietitian_sessions_db if role == "dietitian" else staff_sessions_db)
    for token, owner in list(sessions.items()):
        if str(owner) == str(account_id):
            sessions.pop(token, None)
    return {"message": "Password changed. Sign in again with your new password."}


def _encode_photo(file_bytes: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(file_bytes)) as original:
            if original.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Use a JPG, PNG or WebP photo")
            if original.width * original.height > 16_000_000:
                raise HTTPException(413, "Photo dimensions are too large")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=83, method=4)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "Invalid photo file") from None


@router.put("/photo")
async def upload_photo(file: UploadFile = File(...), identity=Depends(identity_required)):
    _account(identity)
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Use JPG, PNG or WebP")
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Profile photos must be 2 MB or less")
    if not raw:
        raise HTTPException(422, "Choose a photo")
    processed = _encode_photo(raw)
    _save_details(identity, {"photo_data": processed, "photo_content_type": "image/webp", "photo_hidden": False})
    return {"message": "Profile photo updated", "has_photo": True}


def _legacy_photo(identity):
    role, account_id = identity
    if role != "client":
        return None
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT file_data FROM client_profile_photo WHERE client_id=%s", (account_id,))
            row = cursor.fetchone()
        return bytes(row["file_data"]) if row and row["file_data"] else None
    image = profile_photos_db.get(account_id)
    return image.get("bytes") if image else None


@router.get("/photo")
def read_photo(identity=Depends(identity_required)):
    _account(identity)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT photo_data FROM account_profile WHERE account_role=%s AND account_id=%s",
                identity,
            )
            row = cursor.fetchone()
        content = bytes(row["photo_data"]) if row and row["photo_data"] else None
    else:
        content = account_profiles_db.get(tuple(identity), {}).get("photo_data")
    if not content:
        details = _details(identity)
        if not details.get("photo_hidden"):
            content = _legacy_photo(identity)
            if content:
                # Older patient onboarding images are JPEG or PNG. Return
                # normalized WebP so the shared avatar always uses one format.
                content = _encode_photo(content)
    if not content:
        raise HTTPException(404, "No profile photo")
    return Response(content, media_type="image/webp", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.delete("/photo")
def delete_photo(identity=Depends(identity_required)):
    _account(identity)
    _save_details(identity, {"photo_data": None, "photo_content_type": None, "photo_hidden": True})
    return {"message": "Profile photo removed", "has_photo": False}
