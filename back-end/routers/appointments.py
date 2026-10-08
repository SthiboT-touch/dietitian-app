"""4. Appointments and goals."""
import uuid
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime
import database
import config
from state import appointments_db, goals_db, users_db
from schemas import AppointmentCreate, AppointmentDecision, GoalCreate


router = APIRouter()


# --- 4. APPOINTMENTS & GOALS ---

@router.post("/api/v1/appointments", tags=["4. Appointments & Goals"])
def create_appointment(data: AppointmentCreate):
    try:
        appointment_date = datetime.fromisoformat(data.appointment_date.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Appointment date must be a valid date and time") from exc
    now = datetime.now(appointment_date.tzinfo) if appointment_date.tzinfo else datetime.now()
    if appointment_date <= now:
        raise HTTPException(status_code=422, detail="Appointment date must be in the future")
    appt_id = f"appt_{uuid.uuid4().hex[:8]}"
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO appointment (appointment_id, client_id, dietitian_id, date_time, duration, status) "
                "VALUES (%s, %s, %s, %s, %s, 'PENDING') RETURNING status, date_time",
                (appt_id, data.client_id, data.dietitian_id, data.appointment_date, 30),
            )
            row = cursor.fetchone()
        appointment = {
            "appointment_id": appt_id,
            "client_id": data.client_id,
            "dietitian_id": data.dietitian_id,
            "appointment_date": row["date_time"].isoformat(),
            "status": row["status"],
        }
        return {"message": "Appointment scheduled", "appointment": appointment}
    appointment = {
        "appointment_id": appt_id,
        "status": "PENDING",
        "client_id": data.client_id,
        "dietitian_id": data.dietitian_id,
        "appointment_date": appointment_date.isoformat(),
    }
    appointments_db[appt_id] = appointment
    return {"message": "Appointment scheduled", "appointment": appointment}

@router.get("/api/v1/appointments", tags=["4. Appointments & Goals"])
def get_appointments(client_id: Optional[str] = None, dietitian_id: Optional[str] = None):
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
            query = "SELECT appointment_id, client_id, dietitian_id, date_time AS appointment_date, status FROM appointment"
            if filters:
                query += f" WHERE {' AND '.join(filters)}"
            cursor.execute(f"{query} ORDER BY date_time", tuple(parameters))
            return [
                {**dict(row), "appointment_date": row["appointment_date"].isoformat()}
                for row in cursor.fetchall()
            ]
    appointments = list(appointments_db.values())
    if client_id:
        appointments = [appointment for appointment in appointments if appointment["client_id"] == client_id]
    if dietitian_id:
        appointments = [appointment for appointment in appointments if appointment["dietitian_id"] == dietitian_id]
    return appointments


@router.patch("/api/v1/appointments/{appointment_id}", tags=["4. Appointments & Goals"])
def decide_appointment(appointment_id: str, data: AppointmentDecision):
    new_status = {"APPROVED": "CONFIRMED", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED"}[data.action]
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT status, date_time > CURRENT_TIMESTAMP AS is_future "
                "FROM appointment WHERE appointment_id = %s FOR UPDATE",
                (appointment_id,),
            )
            appointment = cursor.fetchone()
            if not appointment:
                raise HTTPException(status_code=404, detail="Appointment not found")
            current_status = appointment["status"]
            if data.action == "CANCELLED":
                if current_status not in {"PENDING", "CONFIRMED", "SCHEDULED"} or not appointment["is_future"]:
                    raise HTTPException(status_code=409, detail="Only future pending or confirmed appointments can be cancelled")
            elif current_status != "PENDING":
                raise HTTPException(status_code=409, detail="Only pending appointment requests can be reviewed")
            cursor.execute(
                "UPDATE appointment SET status = %s WHERE appointment_id = %s "
                "RETURNING appointment_id, client_id, dietitian_id, date_time AS appointment_date, status",
                (new_status, appointment_id),
            )
            updated = cursor.fetchone()
            if new_status == "CONFIRMED" and updated["dietitian_id"]:
                cursor.execute(
                    "UPDATE client SET dietitian_id = %s WHERE client_id = %s",
                    (updated["dietitian_id"], updated["client_id"]),
                )
        return {"message": "Appointment status updated", "appointment": {
            **dict(updated), "appointment_date": updated["appointment_date"].isoformat(),
        }}

    appointment = appointments_db.get(appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    current_status = appointment["status"]
    if data.action == "CANCELLED":
        appointment_date = datetime.fromisoformat(appointment["appointment_date"].replace("Z", "+00:00"))
        now = datetime.now(appointment_date.tzinfo) if appointment_date.tzinfo else datetime.now()
        if current_status not in {"PENDING", "CONFIRMED", "SCHEDULED"} or appointment_date <= now:
            raise HTTPException(status_code=409, detail="Only future pending or confirmed appointments can be cancelled")
    elif current_status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending appointment requests can be reviewed")
    appointment["status"] = new_status
    if new_status == "CONFIRMED":
        client = users_db.get(appointment["client_id"])
        if client:
            client["dietitian_id"] = appointment["dietitian_id"]
    return {"message": "Appointment status updated", "appointment": appointment}

@router.post("/api/v1/goals", tags=["4. Appointments & Goals"])
def set_goal(data: GoalCreate):
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
    return {"message": "Target goal created successfully", "goal": {"goal_id": goal_id, **data.model_dump()}}


@router.get("/api/v1/goals", tags=["4. Appointments & Goals"])
def get_goals(client_id: str):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT goal_id, goal_type AS target_metric, current_value, target_value, target_date "
                "FROM nutrition_goal WHERE client_id = %s ORDER BY target_date NULLS LAST, goal_id",
                (client_id,),
            )
            return [
                {**dict(row), "target_date": row["target_date"].isoformat() if row["target_date"] else None}
                for row in cursor.fetchall()
            ]
    return goals_db.get(client_id, [])
