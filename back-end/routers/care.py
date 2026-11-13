"""Versioned history, clinician recommendations and progress review snapshots."""
from datetime import datetime, timezone
from copy import deepcopy
from uuid import uuid4
import json
from typing import Literal, Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
import config
import database
from security import authorize_client_access, current_identity
from state import clients_db
from routers.clients import get_progress
from consultations import completed_consultation

router = APIRouter(prefix="/api/v1/clients/{client_id}/care", tags=["Patient care workflow"])


class History(BaseModel):
    medications: str = Field(default="", max_length=4000)
    surgeries: str = Field(default="", max_length=4000)
    family_history: str = Field(default="", max_length=4000)
    dietary_history: str = Field(default="", max_length=4000)
    lifestyle: str = Field(default="", max_length=4000)
    concerns: str = Field(default="", max_length=4000)


class Review(BaseModel):
    appointment_id: Optional[str] = None
    log_date: str
    decision: Literal["APPROVED", "CHANGES_REQUESTED"]
    notes: str = Field(..., min_length=1, max_length=4000)


class Recommendation(BaseModel):
    appointment_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=4000)


def identity_for(client_id, authorization, clinician=False):
    identity = current_identity(authorization)
    authorize_client_access(client_id, identity)
    if clinician and identity[0] != "dietitian":
        raise HTTPException(403, "Only the assigned dietitian may review or recommend")
    return identity


def events(client_id):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT event_id, kind, author_id, created_at, payload FROM client_care_event WHERE client_id=%s ORDER BY created_at, event_id", (client_id,))
            return [{**dict(row), "created_at": row["created_at"].isoformat()} for row in cursor.fetchall()]
    return clients_db.get(client_id, {}).get("care_events", [])


def save(client_id, kind, author_id, payload):
    payload = jsonable_encoder(payload)
    event = dict(event_id=uuid4().hex, kind=kind, author_id=author_id,
                 created_at=datetime.now(timezone.utc).isoformat(), payload=payload)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO client_care_event(event_id,client_id,kind,author_id,payload) VALUES (%s,%s,%s,%s,%s::jsonb)",
                           (event["event_id"], client_id, kind, author_id, json.dumps(payload)))
    else:
        clients_db.setdefault(client_id, {}).setdefault("care_events", []).append(deepcopy(event))
    return event


@router.get("")
def get_care(client_id: str, authorization: Optional[str] = Header(default=None)):
    identity_for(client_id, authorization)
    return events(client_id)


@router.post("/history")
def submit_history(client_id: str, data: History, authorization: Optional[str] = Header(default=None)):
    identity = identity_for(client_id, authorization)
    if not any(value.strip() for value in data.model_dump().values()):
        raise HTTPException(422, "Enter medical history before saving")
    return save(client_id, "HISTORY", identity[1], data.model_dump())


@router.post("/recommendations")
def recommend(client_id: str, data: Recommendation, authorization: Optional[str] = Header(default=None)):
    identity = identity_for(client_id, authorization, clinician=True)
    data.appointment_id = completed_consultation(client_id, identity[1], data.appointment_id)
    if not data.content.strip():
        raise HTTPException(422, "Enter a recommendation")
    return save(client_id, "RECOMMENDATION", identity[1], data.model_dump())


@router.post("/progress-reviews")
def review_progress(client_id: str, data: Review, authorization: Optional[str] = Header(default=None)):
    identity = identity_for(client_id, authorization, clinician=True)
    data.appointment_id = completed_consultation(client_id, identity[1], data.appointment_id)
    entry = next((row for row in get_progress(client_id) if row["log_date"] == data.log_date), None)
    if not entry:
        raise HTTPException(404, "Progress entry not found")
    if not data.notes.strip():
        raise HTTPException(422, "Enter review feedback")
    # Approval is tied to this exact snapshot: editing progress requires a new review.
    return save(client_id, "PROGRESS_REVIEW", identity[1], {**data.model_dump(), "snapshot": entry})
