"""4. Appointments and goals."""

import uuid
import secrets
from urllib.parse import quote, urlsplit
from fastapi import APIRouter, Header, HTTPException, Response
from typing import Optional
from datetime import datetime
import database
import config
from state import appointments_db, goals_db, users_db
from schemas import AppointmentCreate, AppointmentDecision, GoalCreate
from security import current_identity, authorize_client_access, client_is_assigned_to_dietitian

router = APIRouter()


def _new_room_id() -> str:
    """Opaque per-appointment conference room ID; never include patient information."""
    return "nc-" + secrets.token_urlsafe(32)


def _meeting_base_url() -> str:
    """Approved HTTPS meeting host; local memory demo uses an explicitly configured provider."""
    import os
    base_url = os.getenv("NUTRICARE_MEETING_BASE_URL", "").strip().rstrip("/")
    parts = urlsplit(base_url)
    if (
        not base_url
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise HTTPException(503, "Virtual meeting service is not configured with an approved HTTPS provider")
    return base_url


def _appointment_type(appointment: dict) -> str:
    """Compatibility with bookings created before consultation type was added."""
    return appointment.get("consultation_type") or "IN_PERSON"


# --- 4. APPOINTMENTS & GOALS ---


def _authorize_appointment_decision(
    appointment: dict, action: str, identity: tuple[str, str]
) -> None:
    """Only participants or an administrator may change an appointment.

    Clients can cancel their own booking. Dietitians can review requests made
    with them and cancel their own bookings. Clients cannot self-approve.
    """
    role, account_id = identity
    if role == "admin":
        return
    if role == "dietitian" and str(appointment["dietitian_id"]) == account_id:
        return
    if role == "client" and action == "CANCELLED" and str(appointment["client_id"]) == account_id:
        return
    raise HTTPException(status_code=403, detail="Not authorized to change this appointment")


@router.post("/api/v1/appointments", tags=["4. Appointments & Goals"])
def create_appointment(
    data: AppointmentCreate, authorization: Optional[str] = Header(default=None)
):
    # Clients may book any listed dietitian; only the client themselves (or
    # authorized staff) may submit an appointment for their client account.
    authorize_client_access(data.client_id, current_identity(authorization))
    try:
        appointment_date = datetime.fromisoformat(data.appointment_date.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Appointment date must be a valid date and time"
        ) from exc
    now = datetime.now(appointment_date.tzinfo) if appointment_date.tzinfo else datetime.now()
    if appointment_date <= now:
        raise HTTPException(status_code=422, detail="Appointment date must be in the future")
    appt_id = f"appt_{uuid.uuid4().hex[:8]}"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO appointment (appointment_id, client_id, dietitian_id, date_time, duration, status, consultation_type) "
                "VALUES (%s, %s, %s, %s, %s, 'PENDING', %s) RETURNING status, date_time, consultation_type",
                (appt_id, data.client_id, data.dietitian_id, data.appointment_date, 30, data.consultation_type),
            )
            row = cursor.fetchone()
        appointment = {
            "appointment_id": appt_id,
            "client_id": data.client_id,
            "dietitian_id": data.dietitian_id,
            "appointment_date": row["date_time"].isoformat(),
            "status": row["status"],
            "consultation_type": row["consultation_type"],
        }
        return {"message": "Appointment scheduled", "appointment": appointment}
    appointment = {
        "appointment_id": appt_id,
        "status": "PENDING",
        "client_id": data.client_id,
        "dietitian_id": data.dietitian_id,
        "appointment_date": appointment_date.isoformat(),
        "consultation_type": data.consultation_type,
        "virtual_room_id": None,
    }
    appointments_db[appt_id] = appointment
    return {"message": "Appointment scheduled", "appointment": {key: value for key, value in appointment.items() if key != "virtual_room_id"}}


@router.get("/api/v1/appointments", tags=["4. Appointments & Goals"])
def get_appointments(
    client_id: Optional[str] = None,
    dietitian_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    role, account_id = current_identity(authorization)
    if role == "client":
        if (client_id and client_id != account_id) or dietitian_id:
            raise HTTPException(status_code=403, detail="Cannot view other appointments")
        client_id = account_id
    elif role == "dietitian":
        if dietitian_id and dietitian_id != account_id:
            raise HTTPException(status_code=403, detail="Cannot view other appointments")
        # The result always stays scoped to this dietitian. A prospective
        # client's pending booking must remain visible before assignment.
        dietitian_id = account_id
    # Admins retain the ability to filter or view appointments network-wide.

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            filters = []
            parameters = []
            if client_id:
                filters.append("client_id = %s")
                parameters.append(client_id)
            if dietitian_id:
                filters.append("dietitian_id = %s")
                parameters.append(dietitian_id)
            query = "SELECT appointment_id, client_id, dietitian_id, date_time AS appointment_date, status, consultation_type FROM appointment"
            if filters:
                query += f" WHERE {' AND '.join(filters)}"
            cursor.execute(f"{query} ORDER BY date_time", tuple(parameters))
            return [
                {**dict(row), "appointment_date": row["appointment_date"].isoformat()}
                for row in cursor.fetchall()
            ]
    appointments = [
        {key: value for key, value in appointment.items() if key != "virtual_room_id"}
        for appointment in appointments_db.values()
    ]
    if client_id:
        appointments = [
            appointment for appointment in appointments if appointment["client_id"] == client_id
        ]
    if dietitian_id:
        appointments = [
            appointment
            for appointment in appointments
            if appointment["dietitian_id"] == dietitian_id
        ]
    return appointments


@router.patch("/api/v1/appointments/{appointment_id}", tags=["4. Appointments & Goals"])
def decide_appointment(
    appointment_id: str,
    data: AppointmentDecision,
    authorization: Optional[str] = Header(default=None),
):
    identity = current_identity(authorization)

    new_status = {"APPROVED": "CONFIRMED", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}[
        data.action
    ]
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT status, client_id, dietitian_id, consultation_type, virtual_room_id, "
                "date_time > CURRENT_TIMESTAMP AS is_future "
                "FROM appointment WHERE appointment_id = %s FOR UPDATE",
                (appointment_id,),
            )
            appointment = cursor.fetchone()
            if not appointment:
                raise HTTPException(status_code=404, detail="Appointment not found")
            _authorize_appointment_decision(appointment, data.action, identity)
            current_status = appointment["status"]
            if data.action == "CANCELLED":
                if (
                    current_status not in {"PENDING", "CONFIRMED", "SCHEDULED"}
                    or not appointment["is_future"]
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Only future pending or confirmed appointments can be cancelled",
                    )
            elif current_status != "PENDING":
                raise HTTPException(
                    status_code=409, detail="Only pending appointment requests can be reviewed"
                )
            # Keep room credentials private in GET responses. Generate only on confirmation.
            room_id = appointment["virtual_room_id"]
            if new_status == "CONFIRMED" and appointment["consultation_type"] == "VIRTUAL":
                room_id = room_id or _new_room_id()
            cursor.execute(
                "UPDATE appointment SET status = %s, virtual_room_id = %s WHERE appointment_id = %s "
                "RETURNING appointment_id, client_id, dietitian_id, date_time AS appointment_date, "
                "status, consultation_type",
                (new_status, room_id, appointment_id),
            )
            updated = cursor.fetchone()
            if new_status == "CONFIRMED" and updated["dietitian_id"]:
                cursor.execute(
                    "UPDATE client SET dietitian_id = %s WHERE client_id = %s",
                    (updated["dietitian_id"], updated["client_id"]),
                )
        return {
            "message": "Appointment status updated",
            "appointment": {
                **dict(updated),
                "appointment_date": updated["appointment_date"].isoformat(),
            },
        }

    appointment = appointments_db.get(appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _authorize_appointment_decision(appointment, data.action, identity)
    current_status = appointment["status"]
    if data.action == "CANCELLED":
        appointment_date = datetime.fromisoformat(
            appointment["appointment_date"].replace("Z", "+00:00")
        )
        now = datetime.now(appointment_date.tzinfo) if appointment_date.tzinfo else datetime.now()
        if current_status not in {"PENDING", "CONFIRMED", "SCHEDULED"} or appointment_date <= now:
            raise HTTPException(
                status_code=409,
                detail="Only future pending or confirmed appointments can be cancelled",
            )
    elif current_status != "PENDING":
        raise HTTPException(
            status_code=409, detail="Only pending appointment requests can be reviewed"
        )
    appointment["status"] = new_status
    if new_status == "CONFIRMED" and _appointment_type(appointment) == "VIRTUAL":
        appointment["virtual_room_id"] = appointment.get("virtual_room_id") or _new_room_id()
    if new_status == "CONFIRMED":
        client = users_db.get(appointment["client_id"])
        if client:
            client["dietitian_id"] = appointment["dietitian_id"]
    return {
        "message": "Appointment status updated",
        "appointment": {key: value for key, value in appointment.items() if key != "virtual_room_id"},
    }


@router.get("/api/v1/appointments/{appointment_id}/meeting", tags=["4. Appointments & Goals"])
def get_virtual_meeting(
    appointment_id: str,
    response: Response,
    authorization: Optional[str] = Header(default=None),
):
    """Share a private room URL only with either confirmed appointment participant.

    The provider is responsible for participant authentication and clinical
    privacy. A bare public conferencing URL is suitable for demos only.
    """
    role, account_id = current_identity(authorization)
    response.headers["Cache-Control"] = "private, no-store"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT appointment_id, client_id, dietitian_id, status, consultation_type, "
                "virtual_room_id FROM appointment WHERE appointment_id=%s",
                (appointment_id,),
            )
            appt = cursor.fetchone()
    else:
        appt = appointments_db.get(appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")
    if not (
        (role == "client" and str(appt["client_id"]) == account_id)
        or (role == "dietitian" and str(appt["dietitian_id"]) == account_id)
    ):
        raise HTTPException(403, "Only appointment participants can access the meeting")
    if _appointment_type(appt) != "VIRTUAL":
        raise HTTPException(409, "This appointment is in person")
    if appt["status"] != "CONFIRMED" or not appt.get("virtual_room_id"):
        raise HTTPException(409, "The dietitian must confirm the virtual appointment first")
    url = _meeting_base_url() + "/" + quote(appt["virtual_room_id"], safe="")
    return {
        "appointment_id": appt["appointment_id"],
        "consultation_type": "VIRTUAL",
        "meeting_url": url,
        "notice": "External video service. Do not share this link; use an approved healthcare provider for real consultations.",
    }


@router.post("/api/v1/goals", tags=["4. Appointments & Goals"])
def set_goal(data: GoalCreate, authorization: Optional[str] = Header(default=None)):
    """Only the client's assigned dietitian may prescribe a nutrition goal.

    Hiding the form in the patient UI is not sufficient: clients must also be
    blocked from sending POST requests directly to this endpoint.
    """
    role, account_id = current_identity(authorization)
    if role != "dietitian" or not client_is_assigned_to_dietitian(data.client_id, account_id):
        raise HTTPException(status_code=403, detail="Only the assigned dietitian can set patient goals")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO nutrition_goal (client_id, goal_type, target_value) VALUES (%s, %s, %s) "
                "RETURNING goal_id",
                (data.client_id, data.target_metric, data.target_value),
            )
            goal_id = cursor.fetchone()["goal_id"]
    else:
        goal_id = f"goal_{uuid.uuid4().hex[:8]}"
        goals_db.setdefault(data.client_id, []).append({"goal_id": goal_id, **data.model_dump()})
    return {
        "message": "Target goal created successfully",
        "goal": {"goal_id": goal_id, **data.model_dump()},
    }


@router.get("/api/v1/goals", tags=["4. Appointments & Goals"])
def get_goals(client_id: str, authorization: Optional[str] = Header(default=None)):
    authorize_client_access(client_id, current_identity(authorization))
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT goal_id, goal_type AS target_metric, current_value, target_value, target_date "
                "FROM nutrition_goal WHERE client_id = %s ORDER BY target_date NULLS LAST, goal_id",
                (client_id,),
            )
            return [
                {
                    **dict(row),
                    "target_date": row["target_date"].isoformat() if row["target_date"] else None,
                }
                for row in cursor.fetchall()
            ]
    return goals_db.get(client_id, [])
