"""Patient photo uploads and appointment-linked, single-use reception QR check-in."""

import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

import config
import database
from onboarding_services import checkin_hash, new_checkin_credential, qr_svg
from role_management import require_roles
from security import authorize_client_access, current_identity
from state import (
    appointments_db,
    checkin_credentials_db,
    checkin_events_db,
    profile_photos_db,
    staff_accounts_db,
    users_db,
)

router = APIRouter(tags=["Digital Onboarding"])
CONFIRMED_STATUSES = {"CONFIRMED", "SCHEDULED"}


def _appointment_is_future(appointment_date) -> bool:
    """Compare both naive local and timezone-aware appointment timestamps safely."""
    try:
        date = appointment_date if isinstance(appointment_date, datetime) else datetime.fromisoformat(
            str(appointment_date).replace("Z", "+00:00")
        )
        now = datetime.now(date.tzinfo) if date.tzinfo else datetime.now()
        return date > now
    except (TypeError, ValueError):
        return False


def _client_identity(client_id: str, authorization: Optional[str]) -> None:
    """Only patients can generate codes for themselves, not admins or other staff."""
    role, account = current_identity(authorization)
    if role != "client" or account != client_id:
        raise HTTPException(403, "Only the patient can request their check-in code")


def _eligible_in_memory(client_id: str) -> list[dict]:
    appointments = []
    for entry in appointments_db.values():
        if (
            str(entry.get("client_id")) == client_id
            and entry.get("status") in CONFIRMED_STATUSES
            and entry.get("consultation_type", "IN_PERSON") == "IN_PERSON"
            and _appointment_is_future(entry.get("appointment_date"))
        ):
            appointments.append(entry)
    return sorted(appointments, key=lambda a: str(a.get("appointment_date")))


def _eligible_in_database(client_id: str) -> list[dict]:
    with database.cursor() as cursor:
        cursor.execute(
            "SELECT appointment_id, client_id, dietitian_id, date_time AS appointment_date, status "
            "FROM appointment WHERE client_id=%s AND consultation_type='IN_PERSON' "
            "AND status IN ('CONFIRMED','SCHEDULED') "
            "AND date_time > CURRENT_TIMESTAMP ORDER BY date_time",
            (client_id,),
        )
        rows = cursor.fetchall()
    return [
        {**dict(row), "appointment_date": row["appointment_date"].isoformat()}
        for row in rows
    ]


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


@router.get("/api/v1/clients/{client_id}/checkin-appointments")
def list_checkin_appointments(
    client_id: str, response: Response, authorization: Optional[str] = Header(default=None)
):
    """Only confirmed upcoming appointments are eligible for QR check-in."""
    _client_identity(client_id, authorization)
    response.headers["Cache-Control"] = "no-store"
    appointments = (
        _eligible_in_database(client_id) if config.DATABASE_ENABLED else _eligible_in_memory(client_id)
    )
    return [
        {
            "appointment_id": a["appointment_id"],
            "appointment_date": a["appointment_date"],
            "dietitian_id": a["dietitian_id"],
            "status": a["status"],
        }
        for a in appointments
    ]


class CheckinCodeRequest(BaseModel):
    appointment_id: str = Field(..., min_length=1, max_length=36)


@router.post("/api/v1/clients/{client_id}/checkin-code")
def new_client_checkin_code(
    client_id: str,
    data: CheckinCodeRequest,
    response: Response,
    authorization: Optional[str] = Header(default=None),
):
    """Generate a short-lived QR *only* for the patient's confirmed appointment.

    The appointment is validated on issuance and again when reception scans
    the code. QR credentials never reveal personal IDs or clinical records.
    """
    _client_identity(client_id, authorization)
    response.headers["Cache-Control"] = "no-store"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT appointment_id FROM appointment "
                "WHERE appointment_id=%s AND client_id=%s "
                "AND consultation_type='IN_PERSON' "
                "AND status IN ('CONFIRMED','SCHEDULED') "
                "AND date_time > CURRENT_TIMESTAMP",
                (data.appointment_id, client_id),
            )
            if not cursor.fetchone():
                raise HTTPException(409, "QR check-in is available only for a confirmed upcoming appointment")
            cursor.execute(
                "SELECT 1 FROM client_checkin_event WHERE appointment_id=%s",
                (data.appointment_id,),
            )
            if cursor.fetchone():
                raise HTTPException(409, "This appointment has already been checked in")
            token, digest = new_checkin_credential()
            cursor.execute(
                "INSERT INTO client_checkin_credential (client_id, appointment_id, token_hash) "
                "VALUES (%s,%s,%s) ON CONFLICT (client_id) DO UPDATE SET "
                "appointment_id=EXCLUDED.appointment_id, token_hash=EXCLUDED.token_hash, "
                "rotated_at=NOW(), expires_at=NOW()+INTERVAL '10 minutes'",
                (client_id, data.appointment_id, digest),
            )
    else:
        eligible = _eligible_in_memory(client_id)
        if not any(a["appointment_id"] == data.appointment_id for a in eligible):
            raise HTTPException(409, "QR check-in is available only for a confirmed upcoming appointment")
        if any(e.get("appointment_id") == data.appointment_id for e in checkin_events_db):
            raise HTTPException(409, "This appointment has already been checked in")
        token, digest = new_checkin_credential()
        checkin_credentials_db[client_id] = {
            "token_hash": digest,
            "appointment_id": data.appointment_id,
            "expires_at": datetime.now(timezone.utc).timestamp() + 600,
        }
    return {
        "appointment_id": data.appointment_id,
        "qr_svg": qr_svg("NC1:" + token),
        "checkin_code": "NC1:" + token,
        "instructions": "Show this QR to reception for your confirmed appointment. It expires in 10 minutes and can be used once.",
    }


class CheckinRequest(BaseModel):
    checkin_code: str = Field(..., min_length=20, max_length=200)


@router.post("/api/v1/reception/check-in", status_code=201)
def scan_checkin(
    data: CheckinRequest, identity=Depends(require_roles("reception", "branch_manager"))
):
    """Check in only at the confirmed appointment's assigned branch."""
    _, staff_id = identity
    token = data.checkin_code.removeprefix("NC1:").strip()
    if len(token) < 32:
        raise HTTPException(422, "Invalid check-in code")
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
                "SELECT client_id, appointment_id FROM client_checkin_credential "
                "WHERE token_hash=%s AND expires_at > NOW() FOR UPDATE",
                (digest,),
            )
            credential = cursor.fetchone()
            if not credential or not credential["appointment_id"]:
                raise HTTPException(404, "Invalid or expired check-in code")
            appointment_id = credential["appointment_id"]
            client_id = credential["client_id"]
            cursor.execute(
                "SELECT a.appointment_id, a.status, a.consultation_type, "
                "a.date_time > CURRENT_TIMESTAMP AS is_future, "
                "d.branch_id FROM appointment a "
                "JOIN dietitian d ON d.dietitian_id=a.dietitian_id "
                "WHERE a.appointment_id=%s AND a.client_id=%s FOR UPDATE OF a",
                (appointment_id, client_id),
            )
            appointment = cursor.fetchone()
            if (
                not appointment
                or appointment["status"] not in CONFIRMED_STATUSES
                or appointment["consultation_type"] != "IN_PERSON"
                or not appointment["is_future"]
            ):
                raise HTTPException(409, "This appointment is no longer eligible for check-in")
            if appointment["branch_id"] != staff["branch_id"]:
                raise HTTPException(403, "Check-in must be completed at the appointment branch")
            cursor.execute(
                "SELECT 1 FROM client_checkin_event WHERE appointment_id=%s",
                (appointment_id,),
            )
            if cursor.fetchone():
                raise HTTPException(409, "This appointment has already been checked in")
            cursor.execute(
                "DELETE FROM client_checkin_credential WHERE client_id=%s", (client_id,)
            )
            cursor.execute(
                "INSERT INTO client_checkin_event (checkin_id, client_id, appointment_id, staff_id, branch_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (str(uuid4()), client_id, appointment_id, staff_id, staff["branch_id"]),
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
        appointment = appointments_db.get(appointment_id)
        if (
            not appointment
            or appointment.get("client_id") != client_id
            or appointment.get("status") not in CONFIRMED_STATUSES
            or appointment.get("consultation_type", "IN_PERSON") != "IN_PERSON"
            or not _appointment_is_future(appointment.get("appointment_date"))
        ):
            raise HTTPException(409, "This appointment is no longer eligible for check-in")
        dietitian = users_db.get(appointment.get("dietitian_id"), {})
        # When running locally without a populated dietitian record, don't
        # silently assume the appointment and the reception branch match.
        if dietitian.get("branch_id") != staff["branch_id"]:
            raise HTTPException(403, "Check-in must be completed at the appointment branch")
        if any(event.get("appointment_id") == appointment_id for event in checkin_events_db):
            raise HTTPException(409, "This appointment has already been checked in")
        checkin_credentials_db.pop(client_id, None)
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
        "message": "Patient checked in for confirmed appointment",
        "appointment_id": appointment_id,
        "client_id": client_id,
        "branch_id": staff["branch_id"],
    }
