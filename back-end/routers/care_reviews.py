"""Dietitian clinical follow-up reviews, linked to confirmed consultations.

The review is an explicit clinician action, not an inference that attendance happened.
Patients can only read their own reviews; assigned dietitians can read and write.
"""

from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import config
import database
from security import authorize_client_access, client_is_assigned_to_dietitian, current_identity
from state import appointments_db, care_reviews_db

router = APIRouter()


class CareReviewCreate(BaseModel):
    client_id: str = Field(min_length=1, max_length=36)
    appointment_id: str = Field(min_length=1, max_length=36)
    review_summary: str = Field(min_length=10, max_length=2000)
    monitoring_plan: str = Field(min_length=10, max_length=2000)
    decision: Literal["CONTINUE_PLAN", "ADJUST_PLAN", "FOLLOW_UP"] = "FOLLOW_UP"
    next_review_date: Optional[date] = None


def _serialize(row: dict) -> dict:
    return {
        "review_id": str(row["review_id"]),
        "client_id": str(row["client_id"]),
        "dietitian_id": str(row["dietitian_id"]),
        "appointment_id": str(row["appointment_id"]),
        "review_summary": row["review_summary"],
        "monitoring_plan": row["monitoring_plan"],
        "decision": row["decision"],
        "next_review_date": (row["next_review_date"].isoformat() if isinstance(row.get("next_review_date"), date) else row.get("next_review_date")),
        "reviewed_at": (row["reviewed_at"].isoformat() if isinstance(row.get("reviewed_at"), datetime) else row.get("reviewed_at")),
    }


def _appointment_has_started(appointment_date) -> bool:
    if isinstance(appointment_date, str):
        appointment_date = datetime.fromisoformat(appointment_date.replace("Z", "+00:00"))
    now = datetime.now(appointment_date.tzinfo) if appointment_date.tzinfo else datetime.now()
    return appointment_date <= now


@router.get("/api/v1/care-reviews", tags=["7. Care Journey & Monitoring"])
def list_care_reviews(
    client_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """Read follow-up reviews without exposing other patients' clinical notes."""
    authorize_client_access(client_id, current_identity(authorization))
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT review_id, client_id, dietitian_id, appointment_id, review_summary, "
                "monitoring_plan, decision, next_review_date, reviewed_at FROM care_review "
                "WHERE client_id=%s ORDER BY reviewed_at DESC, review_id DESC",
                (client_id,),
            )
            rows = cursor.fetchall()
    else:
        rows = [row for row in care_reviews_db.values() if row["client_id"] == client_id]
        rows.sort(key=lambda row: row["reviewed_at"], reverse=True)
    return [_serialize(dict(row)) for row in rows]


@router.post("/api/v1/care-reviews", status_code=201, tags=["7. Care Journey & Monitoring"])
def create_care_review(
    data: CareReviewCreate,
    authorization: Optional[str] = Header(default=None),
):
    """Record a clinician's actual review following a confirmed consultation.

    This does not automatically prescribe or change a meal plan or a goal;
    those require their existing separate dietitian approval workflows.
    """
    role, dietitian_id = current_identity(authorization)
    if role != "dietitian" or not client_is_assigned_to_dietitian(data.client_id, dietitian_id):
        raise HTTPException(403, "Only the assigned dietitian can record a care review")
    if data.next_review_date is not None and data.next_review_date < date.today():
        raise HTTPException(422, "Next review date cannot be in the past")

    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT client_id, dietitian_id, status, date_time FROM appointment "
                "WHERE appointment_id = %s FOR UPDATE",
                (data.appointment_id,),
            )
            appointment = cursor.fetchone()
            if not appointment:
                raise HTTPException(404, "Appointment not found")
            if (str(appointment["client_id"]) != data.client_id
                or str(appointment["dietitian_id"]) != dietitian_id
                or appointment["status"] != "CONFIRMED"):
                raise HTTPException(409, "Review must match your confirmed consultation")
            if not _appointment_has_started(appointment["date_time"]):
                raise HTTPException(409, "The consultation has not started yet")
            cursor.execute(
                "INSERT INTO care_review "
                "(review_id, client_id, dietitian_id, appointment_id, review_summary, monitoring_plan, decision, next_review_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING review_id, client_id, dietitian_id, appointment_id, review_summary, monitoring_plan, decision, next_review_date, reviewed_at",
                (str(uuid4()), data.client_id, dietitian_id, data.appointment_id,
                 data.review_summary.strip(), data.monitoring_plan.strip(),
                 data.decision, data.next_review_date),
            )
            record = dict(cursor.fetchone())
    else:
        appointment = appointments_db.get(data.appointment_id)
        if not appointment:
            raise HTTPException(404, "Appointment not found")
        if (str(appointment["client_id"]) != data.client_id
            or str(appointment["dietitian_id"]) != dietitian_id
            or appointment["status"] != "CONFIRMED"):
            raise HTTPException(409, "Review must match your confirmed consultation")
        if not _appointment_has_started(appointment["appointment_date"]):
            raise HTTPException(409, "The consultation has not started yet")
        record = {
            "review_id": str(uuid4()),
            "client_id": data.client_id,
            "dietitian_id": dietitian_id,
            "appointment_id": data.appointment_id,
            "review_summary": data.review_summary.strip(),
            "monitoring_plan": data.monitoring_plan.strip(),
            "decision": data.decision,
            "next_review_date": data.next_review_date,
            "reviewed_at": datetime.now(timezone.utc),
        }
        care_reviews_db[record["review_id"]] = record
    return {"message": "Care review saved", "review": _serialize(record)}
