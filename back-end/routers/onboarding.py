"""FR-1.6 patient photos and FR-1.7 reception-scanned QR check-ins."""

import secrets
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
import config
import database
from onboarding_services import MAX_PHOTO_BYTES, new_checkin_credential, checkin_hash, qr_svg, validate_profile_photo
from role_management import require_roles
from security import current_identity, authorize_client_access
from state import profile_photos_db, checkin_credentials_db, checkin_events_db, staff_accounts_db, appointments_db, users_db

router = APIRouter(tags=["Digital Onboarding"])


def profile_photo_record(role, account_id):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT content_type, file_data FROM account_profile_photo "
                "WHERE account_type=%s AND account_id=%s",
                (role, account_id),
            )
            image = cursor.fetchone()
            if not image and role == "client":
                cursor.execute(
                    "SELECT content_type, file_data FROM client_profile_photo WHERE client_id=%s",
                    (account_id,),
                )
                image = cursor.fetchone()
        return image
    return profile_photos_db.get(f"{role}:{account_id}") or (
        profile_photos_db.get(account_id) if role == "client" else None
    )


@router.get("/api/v1/profile/photo")
def get_my_profile_photo(authorization: Optional[str] = Header(default=None)):
    role, account_id = current_identity(authorization)
    image = profile_photo_record(role, account_id)
    if not image:
        raise HTTPException(404, "No profile photo uploaded")
    return Response(
        content=bytes(image["file_data"] if "file_data" in image else image["bytes"]),
        media_type=image["content_type"],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.put("/api/v1/profile/photo")
async def upload_my_profile_photo(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    role, account_id = current_identity(authorization)
    raw = await file.read(MAX_PHOTO_BYTES + 1)
    validate_profile_photo(file.content_type, raw)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO account_profile_photo (account_type, account_id, file_name, content_type, file_data) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (account_type, account_id) DO UPDATE SET "
                "file_name=EXCLUDED.file_name, content_type=EXCLUDED.content_type, "
                "file_data=EXCLUDED.file_data, uploaded_at=NOW()",
                (role, account_id, "profile-photo", file.content_type, raw),
            )
    else:
        profile_photos_db[f"{role}:{account_id}"] = {
            "filename": "profile-photo",
            "content_type": file.content_type,
            "bytes": raw,
        }
    return {"message": "Profile photo saved"}


@router.delete("/api/v1/profile/photo")
def delete_my_profile_photo(authorization: Optional[str] = Header(default=None)):
    role, account_id = current_identity(authorization)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "DELETE FROM account_profile_photo WHERE account_type=%s AND account_id=%s",
                (role, account_id),
            )
            if role == "client":
                cursor.execute("DELETE FROM client_profile_photo WHERE client_id=%s", (account_id,))
    else:
        profile_photos_db.pop(f"{role}:{account_id}", None)
        if role == "client":
            profile_photos_db.pop(account_id, None)
    return {"message": "Profile photo removed"}


def require_checkin_appointment(client_id, cursor=None, branch_id=None, appointment_id=None, lock=False):
    """Check-in is available after confirmation, for today's or upcoming visits."""
    if cursor is not None:
        cursor.execute(
            "SELECT a.appointment_id FROM appointment a "
            "LEFT JOIN dietitian d ON d.dietitian_id=a.dietitian_id "
            "WHERE a.client_id=%s AND a.status IN ('CONFIRMED','SCHEDULED') "
            "AND a.date_time >= (NOW() AT TIME ZONE 'Africa/Johannesburg')::date "
            "AND (%s IS NULL OR COALESCE(a.branch_id,d.branch_id)=%s) "
            "AND (%s IS NULL OR a.appointment_id=%s) "
            "ORDER BY a.date_time LIMIT 1" + (" FOR UPDATE OF a" if lock else ""),
            (client_id, branch_id, branch_id, appointment_id, appointment_id),
        )
        found = cursor.fetchone()
    else:
        local_timezone = timezone(timedelta(hours=2))  # South Africa uses UTC+02 year round.
        today = datetime.now(local_timezone).date()
        found = False
        for appointment in appointments_db.values():
            if appointment_id and appointment["appointment_id"] != appointment_id:
                continue
            if appointment.get("client_id") != client_id or appointment.get("status") not in {"CONFIRMED", "SCHEDULED"}:
                continue
            appointment_date = datetime.fromisoformat(appointment["appointment_date"].replace("Z", "+00:00"))
            local_date = appointment_date.astimezone(local_timezone).date() if appointment_date.tzinfo else appointment_date.date()
            location = appointment.get("branch_id") or users_db.get(appointment.get("dietitian_id"), {}).get("branch_id")
            if local_date >= today and (branch_id is None or location == branch_id):
                found = appointment
                break
    if not found:
        raise HTTPException(409, "A confirmed appointment for today or an upcoming date is required for check-in at this branch" if branch_id else "Book an appointment and wait for confirmation before generating your check-in QR")
    return str(found["appointment_id"])


@router.get("/api/v1/clients/{client_id}/profile-photo")
def get_profile_photo(client_id: str, authorization: Optional[str] = Header(default=None)):
    authorize_client_access(client_id, current_identity(authorization))
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT content_type, file_data FROM client_profile_photo WHERE client_id=%s",
                (client_id,),
            )
            image = cursor.fetchone()
    else:
        image = profile_photos_db.get(client_id)
    if not image:
        raise HTTPException(404, "No profile photo uploaded")
    return Response(
        content=bytes(image["file_data"] if "file_data" in image else image["bytes"]),
        media_type=image["content_type"],
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


class CheckinCodeRequest(BaseModel):
    appointment_id: Optional[str] = None


@router.post("/api/v1/clients/{client_id}/checkin-code")
def new_client_checkin_code(
    client_id: str, response: Response, data: Optional[CheckinCodeRequest] = None, authorization: Optional[str] = Header(default=None)
):
    """Generate short-lived display credential (previous code is revoked).

    Only the actual client can issue their own code; a privileged admin may
    inspect records but cannot impersonate a patient at check-in.
    """
    role, account = current_identity(authorization)
    if role != "client" or account != client_id:
        raise HTTPException(403, "Only the patient can request their check-in code")
    response.headers["Cache-Control"] = "no-store"
    token, digest = new_checkin_credential()
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            appointment_id = require_checkin_appointment(client_id, cursor, appointment_id=data.appointment_id if data else None)
            cursor.execute(
                "INSERT INTO client_checkin_credential (client_id, token_hash, appointment_id) VALUES (%s,%s,%s) "
                "ON CONFLICT (client_id) DO UPDATE SET token_hash=EXCLUDED.token_hash, appointment_id=EXCLUDED.appointment_id, rotated_at=NOW(), expires_at=NOW()+INTERVAL '10 minutes'",
                (client_id, digest, appointment_id),
            )
    else:
        appointment_id = require_checkin_appointment(client_id, appointment_id=data.appointment_id if data else None)
        checkin_credentials_db[client_id] = {
            "appointment_id": appointment_id,
            "token_hash": digest,
            "expires_at": datetime.now(timezone.utc).timestamp() + 600,
        }
    return {
        "client_id": client_id,
        "appointment_id": appointment_id,
        "qr_svg": qr_svg("NC1:" + token),
        "checkin_code": "NC1:" + token,
        "instructions": "Show this code to reception within 10 minutes. Generating a new code revokes the old one.",
    }


class CheckinRequest(BaseModel):
    checkin_code: str = Field(..., min_length=20, max_length=200)


def _appointment_qr_is_valid_today(appointment: dict) -> bool:
    if appointment.get("status") not in {"PENDING", "CONFIRMED", "SCHEDULED"}:
        return False
    appointment_date = appointment["date_time"] if "date_time" in appointment else appointment["appointment_date"]
    if isinstance(appointment_date, str):
        appointment_date = datetime.fromisoformat(
            appointment_date.replace("Z", "+00:00")
        )
    local_date = (
        appointment_date.astimezone(timezone(timedelta(hours=2))).date()
        if appointment_date.tzinfo
        else appointment_date.date()
    )
    return local_date == datetime.now(timezone(timedelta(hours=2))).date()


@router.post("/api/v1/reception/check-in", status_code=201)
def scan_checkin(
    data: CheckinRequest, identity=Depends(require_roles("reception", "branch_manager"))
):
    """Staff-only check-in; never derive a client ID from scanned text."""
    staff_role, staff_id = identity
    token = data.checkin_code.removeprefix("NC1:").strip()
    if len(token) < 32:
        raise HTTPException(422, "Invalid check-in code")
    if token.startswith("APPT:"):
        appointment_id = token.removeprefix("APPT:")
        if not appointment_id:
            raise HTTPException(422, "Invalid appointment check-in code")
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                cursor.execute(
                    "SELECT branch_id, is_active FROM staff_account WHERE staff_id=%s",
                    (staff_id,),
                )
                staff = cursor.fetchone()
                if not staff or not staff["is_active"] or not staff["branch_id"]:
                    raise HTTPException(403, "An active branch assignment is required")
                cursor.execute(
                    "SELECT a.client_id, a.status, a.date_time, "
                    "COALESCE(a.branch_id, d.branch_id) AS appointment_branch "
                    "FROM appointment a JOIN dietitian d ON d.dietitian_id=a.dietitian_id "
                    "WHERE a.appointment_id=%s FOR UPDATE OF a",
                    (appointment_id,),
                )
                appointment = cursor.fetchone()
                if not appointment:
                    raise HTTPException(404, "Appointment QR not found")
                if str(appointment["appointment_branch"]) != str(staff["branch_id"]):
                    raise HTTPException(403, "This appointment belongs to another branch")
                if not _appointment_qr_is_valid_today(appointment):
                    raise HTTPException(
                        409, "This QR is valid only on its active appointment date"
                    )
                cursor.execute(
                    "SELECT 1 FROM client_checkin_event WHERE appointment_id=%s LIMIT 1",
                    (appointment_id,),
                )
                if cursor.fetchone():
                    raise HTTPException(409, "This appointment has already been checked in")
                client_id = appointment["client_id"]
                cursor.execute(
                    "INSERT INTO client_checkin_event "
                    "(checkin_id, client_id, staff_id, branch_id, appointment_id) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (
                        str(uuid4()),
                        client_id,
                        staff_id,
                        staff["branch_id"],
                        appointment_id,
                    ),
                )
                branch_id = staff["branch_id"]
        else:
            staff = staff_accounts_db.get(staff_id)
            if not staff or not staff.get("is_active") or not staff.get("branch_id"):
                raise HTTPException(403, "An active branch assignment is required")
            appointment = appointments_db.get(appointment_id)
            if not appointment:
                raise HTTPException(404, "Appointment QR not found")
            dietitian = users_db.get(appointment.get("dietitian_id"), {})
            appointment_branch = appointment.get("branch_id") or dietitian.get("branch_id")
            if str(appointment_branch) != str(staff["branch_id"]):
                raise HTTPException(403, "This appointment belongs to another branch")
            if not _appointment_qr_is_valid_today(appointment):
                raise HTTPException(
                    409, "This QR is valid only on its active appointment date"
                )
            if any(
                event.get("appointment_id") == appointment_id
                for event in checkin_events_db
            ):
                raise HTTPException(409, "This appointment has already been checked in")
            client_id = appointment["client_id"]
            checkin_events_db.append(
                {
                    "checkin_id": str(uuid4()),
                    "client_id": client_id,
                    "staff_id": staff_id,
                    "branch_id": staff["branch_id"],
                    "appointment_id": appointment_id,
                    "checked_in_at": datetime.now(timezone.utc),
                }
            )
            branch_id = staff["branch_id"]
        return {
            "message": "Patient checked in",
            "appointment_id": appointment_id,
            "client_id": client_id,
            "branch_id": branch_id,
        }

    digest = checkin_hash(token)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT branch_id, is_active FROM staff_account WHERE staff_id=%s", (staff_id,)
            )
            staff = cursor.fetchone()
            if not staff or not staff["is_active"] or not staff["branch_id"]:
                raise HTTPException(403, "An active branch assignment is required")
            cursor.execute(
                "SELECT client_id, appointment_id FROM client_checkin_credential WHERE token_hash=%s AND expires_at > NOW() FOR UPDATE",
                (digest,),
            )
            credential = cursor.fetchone()
            if not credential:
                raise HTTPException(404, "Invalid or expired check-in code")
            client_id = credential["client_id"]
            appointment_id = credential["appointment_id"]
            if not appointment_id:
                raise HTTPException(409, "Generate a new QR code for a confirmed appointment")
            require_checkin_appointment(client_id, cursor, staff["branch_id"], appointment_id, lock=True)
            cursor.execute(
                "SELECT 1 FROM client_checkin_event WHERE appointment_id=%s LIMIT 1",
                (appointment_id,),
            )
            if cursor.fetchone():
                raise HTTPException(409, "This appointment has already been checked in")
            cursor.execute("DELETE FROM client_checkin_credential WHERE client_id=%s", (client_id,))
            cursor.execute(
                "INSERT INTO client_checkin_event (checkin_id, client_id, staff_id, branch_id, appointment_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (str(uuid4()), client_id, staff_id, staff["branch_id"], appointment_id),
            )
    else:
        staff = staff_accounts_db.get(staff_id)
        if not staff or not staff.get("is_active") or not staff.get("branch_id"):
            raise HTTPException(403, "An active branch assignment is required")
        client_id = next(
            (
                cid
                for cid, details in checkin_credentials_db.items()
                if secrets.compare_digest(details["token_hash"], digest)
                and details["expires_at"] > datetime.now(timezone.utc).timestamp()
            ),
            None,
        )
        if not client_id:
            raise HTTPException(404, "Invalid or expired check-in code")
        appointment_id = checkin_credentials_db[client_id].get("appointment_id")
        if not appointment_id:
            raise HTTPException(409, "Generate a new QR code for a confirmed appointment")
        require_checkin_appointment(client_id, branch_id=staff["branch_id"], appointment_id=appointment_id)
        if any(
            event.get("appointment_id") == appointment_id
            for event in checkin_events_db
        ):
            raise HTTPException(409, "This appointment has already been checked in")
        checkin_credentials_db.pop(client_id, None)  # single-use QR credential
        checkin_events_db.append(
            {
                "checkin_id": str(uuid4()),
                "client_id": client_id,
                "appointment_id": appointment_id,
                "staff_id": staff_id,
                "branch_id": staff["branch_id"],
                "checked_in_at": datetime.now(timezone.utc),
            }
        )
    return {
        "message": "Patient checked in",
        "appointment_id": appointment_id,
        "client_id": client_id,
        "branch_id": staff["branch_id"],
    }
