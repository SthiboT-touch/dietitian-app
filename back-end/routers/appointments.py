"""4. Appointments and goals."""

import uuid
from fastapi import APIRouter, Header, HTTPException, Response
from typing import Optional
from datetime import datetime, timezone, timedelta
import database
import config

from state import (
 appointments_db,goals_db,
users_db, clients_db, checkin_events_db,
)
from schemas import AppointmentCreate, AppointmentDecision, GoalCreate
from security import current_identity, authorize_client_access
from consultations import completed_consultation
from virtual_meetings import (
    ACTIVE_MEETING_STATUSES, ensure_meeting_link, is_virtual, meeting_lock, public_appointment,
)

router = APIRouter()
SOUTH_AFRICA = timezone(timedelta(hours=2))


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
    authorize_client_access(data.client_id, current_identity(authorization))

    try:
        appointment_date = datetime.fromisoformat(
            data.appointment_date.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Appointment date must be a valid date and time",
        ) from exc

    now = (
        datetime.now(appointment_date.tzinfo)
        if appointment_date.tzinfo
        else datetime.now()
    )

    if appointment_date <= now:
        raise HTTPException(
            status_code=422,
            detail="Appointment date must be in the future",
        )

    if data.branch_id:
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                cursor.execute("SELECT branch_id, status FROM dietitian WHERE dietitian_id=%s", (data.dietitian_id,))
                dietitian = cursor.fetchone()
        else:
            dietitian = users_db.get(data.dietitian_id)
        if not dietitian or dietitian.get("status") != "APPROVED":
            raise HTTPException(422, "Choose an approved dietitian")
        if str(dietitian.get("branch_id")) != data.branch_id:
            raise HTTPException(422, "Dietitian does not practice at the selected branch")
    appt_id = f"appt_{uuid.uuid4().hex[:8]}"

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO appointment (
                    appointment_id,
                    client_id,
                    dietitian_id,
                    date_time,
                    duration,
                    status,
                    appointment_type,
                    meeting_link,
                    branch_id,
                    consultation_type
                )
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s, NULL, %s, %s)
                RETURNING status, date_time, appointment_type, meeting_link, branch_id, consultation_type
                """,
                (
                    appt_id,
                    data.client_id,
                    data.dietitian_id,
                    data.appointment_date,
                    30,
                    data.appointment_type,
                    data.branch_id,
                    data.consultation_type,
                ),
            )
            row = cursor.fetchone()

        appointment = {
            "appointment_id": appt_id,
            "client_id": data.client_id,
            "dietitian_id": data.dietitian_id,
            "appointment_date": row["date_time"].isoformat(),
            "status": row["status"],
            "appointment_type": row["appointment_type"],
            "meeting_link": row["meeting_link"],
            "branch_id": row["branch_id"],
            "consultation_type": row["consultation_type"],
        }

        return {
            "message": "Appointment scheduled",
            "appointment": appointment,
        }

    appointment = {
        "appointment_id": appt_id,
        "status": "PENDING",
        "client_id": data.client_id,
        "dietitian_id": data.dietitian_id,
        "appointment_date": appointment_date.isoformat(),
        "appointment_type": data.appointment_type,
        "meeting_link": None,
        "branch_id": data.branch_id,
        "consultation_type": data.consultation_type,
    }

    appointments_db[appt_id] = appointment

    return {
        "message": "Appointment scheduled",
        "appointment": appointment,
    }

@router.get("/api/v1/appointments/calendar", tags=["4. Appointments & Goals"])
def get_appointment_calendar(
    authorization: Optional[str] = Header(default=None),
):
    role, dietitian_id = current_identity(authorization)

    if role != "dietitian":
        raise HTTPException(
            status_code=403,
            detail="Only dietitians can view their appointment calendar",
        )

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.appointment_id,
                    a.client_id,
                    a.dietitian_id,
                    a.date_time AS appointment_date,
                    a.status,
                    a.branch_id,
                    a.consultation_type,
                    a.appointment_type,
                    a.meeting_link,
                    c.name AS client_name,
                    checkin.checked_in_at
                FROM appointment a
                JOIN client c
                    ON c.client_id = a.client_id
                JOIN dietitian d
                    ON d.dietitian_id = a.dietitian_id
                LEFT JOIN LATERAL (
                    SELECT e.checked_in_at
                    FROM client_checkin_event e
                    WHERE e.client_id = a.client_id
                      AND e.appointment_id = a.appointment_id
                      AND e.branch_id = COALESCE(a.branch_id, d.branch_id)
                      AND (e.checked_in_at AT TIME ZONE 'Africa/Johannesburg')::date
                          = a.date_time::date
                    ORDER BY e.checked_in_at DESC
                    LIMIT 1
                ) checkin ON TRUE
                WHERE a.dietitian_id = %s
                ORDER BY a.date_time
                """,
                (dietitian_id,),
            )

            return [
                {
                    **public_appointment(row, (role, dietitian_id)),
                    "appointment_date": row["appointment_date"].isoformat(),
                    "checked_in_at": (
                        row["checked_in_at"].isoformat()
                        if row["checked_in_at"]
                        else None
                    ),
                }
                for row in cursor.fetchall()
            ]

    # In-memory fallback for tests and development.
    dietitian = users_db.get(dietitian_id, {})
    branch_id = dietitian.get("branch_id")
    results = []

    for appointment in appointments_db.values():
        if appointment.get("dietitian_id") != dietitian_id:
            continue

        patient = clients_db.get(appointment["client_id"]) or users_db.get(
            appointment["client_id"], {}
        )

        appointment_date = datetime.fromisoformat(
            appointment["appointment_date"].replace("Z", "+00:00")
        )
        local_date = appointment_date.astimezone(
            SOUTH_AFRICA
        ).date() if appointment_date.tzinfo else appointment_date.date()

        checked_in_at = None

        for event in checkin_events_db:
            if event.get("appointment_id") != appointment["appointment_id"]:
                continue
            if event.get("client_id") != appointment["client_id"]:
                continue
            visit_branch = appointment.get("branch_id") or branch_id
            if not visit_branch or event.get("branch_id") != visit_branch:
                continue

            event_time = event.get("checked_in_at")
            if not event_time:
                continue

            if isinstance(event_time, str):
                event_time = datetime.fromisoformat(
                    event_time.replace("Z", "+00:00")
                )

            event_date = (
                event_time.astimezone(SOUTH_AFRICA).date()
                if event_time.tzinfo
                else event_time.date()
            )

            if event_date == local_date:
                if checked_in_at is None or event_time > checked_in_at:
                    checked_in_at = event_time

        results.append(
            {
                **public_appointment(appointment, (role, dietitian_id)),
                "client_name": patient.get("name")
                or patient.get("full_name")
                or appointment["client_id"],
                "checked_in_at": (
                    checked_in_at.isoformat() if checked_in_at else None
                ),
            }
        )

    return sorted(results, key=lambda item: item["appointment_date"])


@router.get("/api/v1/appointments", tags=["4. Appointments & Goals"])
def get_appointments(
    client_id: Optional[str] = None,
    dietitian_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    role, account_id = current_identity(authorization)

    if role == "client":
        if (client_id and client_id != account_id) or dietitian_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot view other appointments",
            )
        client_id = account_id

    elif role == "dietitian":
        if dietitian_id and dietitian_id != account_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot view other appointments",
            )
        dietitian_id = account_id

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

            query = """
                SELECT
                    appointment_id,
                    client_id,
                    dietitian_id,
                    date_time AS appointment_date,
                    status,
                    branch_id,
                    consultation_type,
                    appointment_type,
                    meeting_link
                FROM appointment
            """

            if filters:
                query += f" WHERE {' AND '.join(filters)}"

            cursor.execute(
                f"{query} ORDER BY date_time",
                tuple(parameters),
            )

            return [
                {
                    **public_appointment(row, (role, account_id)),
                    "appointment_date": row["appointment_date"].isoformat(),
                }
                for row in cursor.fetchall()
            ]

    appointments = list(appointments_db.values())

    if client_id:
        appointments = [
            appointment
            for appointment in appointments
            if appointment["client_id"] == client_id
        ]

    if dietitian_id:
        appointments = [
            appointment
            for appointment in appointments
            if appointment["dietitian_id"] == dietitian_id
        ]

    return [public_appointment(a, (role, account_id)) for a in appointments]

@router.patch("/api/v1/appointments/{appointment_id}", tags=["4. Appointments & Goals"])
def decide_appointment(
    appointment_id: str,
    data: AppointmentDecision,
    authorization: Optional[str] = Header(default=None),
):
    identity = current_identity(authorization)

    new_status = {
        "APPROVED": "CONFIRMED",
        "REJECTED": "REJECTED",
        "CANCELLED": "CANCELLED",
    }[data.action]

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, client_id, dietitian_id, appointment_type, consultation_type, meeting_link,
                       date_time > CURRENT_TIMESTAMP AS is_future
                FROM appointment
                WHERE appointment_id = %s
                FOR UPDATE
                """,
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
                    status_code=409,
                    detail="Only pending appointment requests can be reviewed",
                )

            meeting_link = (
                ensure_meeting_link(appointment, data.meeting_link)
                if new_status == "CONFIRMED" else None
            )

            cursor.execute(
                """
                UPDATE appointment
                SET status = %s, meeting_link = %s
                WHERE appointment_id = %s
                RETURNING appointment_id, client_id, dietitian_id,
                          date_time AS appointment_date, status,
                          appointment_type, meeting_link, branch_id, consultation_type
                """,
                (new_status, meeting_link, appointment_id),
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
                **public_appointment(updated, identity),
                "appointment_date": updated["appointment_date"].isoformat(),
            },
        }

    with meeting_lock:
        appointment = appointments_db.get(appointment_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        _authorize_appointment_decision(appointment, data.action, identity)

        current_status = appointment["status"]

        if data.action == "CANCELLED":
            appointment_date = datetime.fromisoformat(
                appointment["appointment_date"].replace("Z", "+00:00")
            )
            now = (
                datetime.now(appointment_date.tzinfo)
                if appointment_date.tzinfo
                else datetime.now()
            )

            if (
                current_status not in {"PENDING", "CONFIRMED", "SCHEDULED"}
                or appointment_date <= now
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Only future pending or confirmed appointments can be cancelled",
                )
        elif current_status != "PENDING":
            raise HTTPException(
                status_code=409,
                detail="Only pending appointment requests can be reviewed",
            )

        appointment["meeting_link"] = (
            ensure_meeting_link(appointment, data.meeting_link)
            if new_status == "CONFIRMED" else None
        )
        appointment["status"] = new_status
        if new_status == "CONFIRMED":
            client = users_db.get(appointment["client_id"])
            if client:
                client["dietitian_id"] = appointment["dietitian_id"]

        return {"message": "Appointment status updated", "appointment": public_appointment(appointment, identity)}


def _authorize_meeting(appointment, identity, create=False):
    role, account_id = identity
    doctor = role == "dietitian" and str(appointment["dietitian_id"]) == account_id
    patient = role == "client" and str(appointment["client_id"]) == account_id
    if not doctor and (create or not patient):
        raise HTTPException(403, "Only the appointment participants can access this meeting; only its dietitian can create the link")
    if not is_virtual(appointment) or appointment["status"] not in ACTIVE_MEETING_STATUSES:
        raise HTTPException(409, "A confirmed virtual appointment is required")


@router.get("/api/v1/appointments/{appointment_id}/meeting", tags=["4. Appointments & Goals"])
def get_appointment_meeting(appointment_id: str, response: Response, authorization: Optional[str] = Header(default=None)):
    identity = current_identity(authorization)
    response.headers["Cache-Control"] = "no-store"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT appointment_id, client_id, dietitian_id, status, appointment_type, consultation_type, meeting_link "
                "FROM appointment WHERE appointment_id=%s", (appointment_id,),
            )
            appointment = cursor.fetchone()
    else:
        appointment = appointments_db.get(appointment_id)
    if not appointment:
        raise HTTPException(404, "Appointment not found")
    _authorize_meeting(appointment, identity)
    return {"appointment_id": appointment_id, "meeting_link": appointment.get("meeting_link")}


@router.post("/api/v1/appointments/{appointment_id}/meeting", tags=["4. Appointments & Goals"])
def create_appointment_meeting(appointment_id: str, response: Response, authorization: Optional[str] = Header(default=None)):
    """Backfill missing links on existing confirmed visits; retries reuse the room."""
    identity = current_identity(authorization)
    if identity[0] != "dietitian":
        raise HTTPException(403, "Only the appointment's dietitian can create its meeting link")
    response.headers["Cache-Control"] = "no-store"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT appointment_id, client_id, dietitian_id, status, appointment_type, consultation_type, meeting_link "
                "FROM appointment WHERE appointment_id=%s FOR UPDATE", (appointment_id,),
            )
            appointment = cursor.fetchone()
            if not appointment:
                raise HTTPException(404, "Appointment not found")
            _authorize_meeting(appointment, identity, create=True)
            link = ensure_meeting_link(appointment)
            cursor.execute("UPDATE appointment SET meeting_link=%s WHERE appointment_id=%s", (link, appointment_id))
    else:
        with meeting_lock:
            appointment = appointments_db.get(appointment_id)
            if not appointment:
                raise HTTPException(404, "Appointment not found")
            _authorize_meeting(appointment, identity, create=True)
            link = ensure_meeting_link(appointment)
    return {"appointment_id": appointment_id, "meeting_link": link}


@router.post("/api/v1/appointments/{appointment_id}/complete", tags=["4. Appointments & Goals"])
def complete_appointment(appointment_id: str, authorization: Optional[str] = Header(default=None)):
    role, account_id = current_identity(authorization)
    if role != "dietitian":
        raise HTTPException(403, "Only the appointment's dietitian can complete the consultation")
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT client_id, dietitian_id, status, date_time <= (NOW() AT TIME ZONE 'Africa/Johannesburg') AS has_started FROM appointment WHERE appointment_id=%s FOR UPDATE", (appointment_id,))
            appointment = cursor.fetchone()
            if not appointment:
                raise HTTPException(404, "Appointment not found")
            if str(appointment["dietitian_id"]) != account_id:
                raise HTTPException(403, "Not your appointment")
            if appointment["status"] not in {"CONFIRMED", "SCHEDULED"} or not appointment["has_started"]:
                raise HTTPException(409, "Only a confirmed consultation whose scheduled time has arrived can be completed")
            cursor.execute("UPDATE appointment SET status='COMPLETED' WHERE appointment_id=%s", (appointment_id,))
    else:
        appointment = appointments_db.get(appointment_id)
        if not appointment:
            raise HTTPException(404, "Appointment not found")
        if appointment["dietitian_id"] != account_id:
            raise HTTPException(403, "Not your appointment")
        when = datetime.fromisoformat(appointment["appointment_date"].replace("Z", "+00:00"))
        from datetime import timezone, timedelta
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone(timedelta(hours=2)))
        if appointment["status"] not in {"CONFIRMED", "SCHEDULED"} or when > datetime.now(timezone.utc):
            raise HTTPException(409, "Only a confirmed consultation whose scheduled time has arrived can be completed")
        appointment["status"] = "COMPLETED"
    return {"message": "Consultation completed", "appointment_id": appointment_id, "status": "COMPLETED"}


@router.post("/api/v1/goals", tags=["4. Appointments & Goals"])
def set_goal(data: GoalCreate, authorization: Optional[str] = Header(default=None)):
    identity = current_identity(authorization)
    if identity[0] != "dietitian":
        raise HTTPException(status_code=403, detail="Only the assigned dietitian can set goals")
    authorize_client_access(data.client_id, identity)
    data.appointment_id = completed_consultation(data.client_id, identity[1], data.appointment_id)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO nutrition_goal (client_id, goal_type, target_value, appointment_id) VALUES (%s, %s, %s, %s) "
                "RETURNING goal_id",
                (data.client_id, data.target_metric, data.target_value, data.appointment_id),
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
                "SELECT goal_id, appointment_id, goal_type AS target_metric, current_value, target_value, target_date "
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
