"""Participant-scoped virtual appointments and dietitian Google OAuth."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import config
import database
import google_meet as google
from security import current_identity, require_dietitian
from state import users_db

router = APIRouter(tags=["Virtual consultations"])


def approved_dietitian(authorization: Optional[str] = Header(default=None)):
    dietitian_id = require_dietitian(authorization)
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT status FROM dietitian WHERE dietitian_id=%s", (dietitian_id,))
            row = cursor.fetchone()
    else:
        row = users_db.get(dietitian_id)
    if not row or row.get("status") != "APPROVED":
        raise HTTPException(403, "An approved dietitian account is required")
    return dietitian_id


@router.get("/api/v1/integrations/google")
def google_status(dietitian_id: str = Depends(approved_dietitian)):
    connection = google.load_connection(dietitian_id)
    return {"configured": google.configured(), "connected": bool(connection), "mode": connection["mode"] if connection else "calendar"}


@router.post("/api/v1/integrations/google/connect")
def connect_google(dietitian_id: str = Depends(approved_dietitian), authorization: Optional[str] = Header(default=None)):
    return {"authorization_url": google.authorize_url(dietitian_id, authorization)}


@router.get("/api/v1/integrations/google/callback")
def google_callback(request: Request, state: str = "", code: str = "", error: Optional[str] = None):
    # Uvicorn's response-time access log must not include OAuth callback parameters.
    request.scope["query_string"] = b""
    google.finish_authorization(state, code, error)
    return RedirectResponse("/?google=connected", status_code=303, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class GooglePreference(BaseModel):
    mode: Literal["calendar", "meet"]


@router.patch("/api/v1/integrations/google")
def google_preference(data: GooglePreference, dietitian_id: str = Depends(approved_dietitian)):
    connection = google.load_connection(dietitian_id)
    if not connection:
        raise HTTPException(409, "Connect Google first")
    google.store_connection(dietitian_id, connection["tokens"], data.mode)
    return {"connected": True, "mode": data.mode}


@router.post("/api/v1/integrations/google/disconnect")
def disconnect_google(dietitian_id: str = Depends(approved_dietitian)):
    with google.lock:
        connection = google.load_connection(dietitian_id)
        if connection:
            tokens = connection["tokens"]
            response = google.google_request("POST", "https://oauth2.googleapis.com/revoke", data={"token": tokens.get("refresh_token") or tokens["access_token"]})
            if response.status_code not in {200, 400}:
                raise HTTPException(503, "Google disconnect could not be completed. Try again.")
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                cursor.execute("DELETE FROM dietitian_google_connection WHERE dietitian_id=%s", (dietitian_id,))
        else:
            google.connections.pop(dietitian_id, None)
        for key in list(google.oauth_states):
            if google.oauth_states[key]["dietitian_id"] == dietitian_id:
                google.oauth_states.pop(key, None)
    return {"connected": False}


def participant(appointment_id, authorization, doctor_only=False):
    role, account_id = current_identity(authorization)
    appointment = google.appointment_record(appointment_id)
    if not appointment:
        raise HTTPException(404, "Appointment not found")
    allowed = role == "dietitian" and account_id == str(appointment["dietitian_id"])
    if not doctor_only:
        allowed = allowed or (role == "client" and account_id == str(appointment["client_id"]))
    if not allowed:
        raise HTTPException(403, "Only the appointment participants can access its meeting")
    return appointment


def public_meeting(record):
    result = {key: record.get(key) for key in ("appointment_id", "meeting_mode", "meeting_url", "status", "message")}
    if not google.safe_meet_url(result["meeting_url"]):
        result["meeting_url"] = None
    return result


@router.get("/api/v1/appointments/{appointment_id}/meeting")
def get_meeting(appointment_id: str, authorization: Optional[str] = Header(default=None)):
    appointment = participant(appointment_id, authorization)
    if appointment.get("consultation_type") != "VIRTUAL" or appointment["status"] not in {"CONFIRMED", "SCHEDULED"}:
        return {"status": "UNAVAILABLE", "meeting_url": None}
    record = google.load_meeting(appointment_id)
    if not record:
        return {"status": "NOT_CREATED", "meeting_url": None}
    return public_meeting(record)


@router.post("/api/v1/appointments/{appointment_id}/meeting")
def create_meeting(appointment_id: str, authorization: Optional[str] = Header(default=None)):
    participant(appointment_id, authorization, doctor_only=True)
    return public_meeting(google.ensure_meeting(appointment_id))


@router.delete("/api/v1/appointments/{appointment_id}/meeting")
def cleanup_meeting(appointment_id: str, authorization: Optional[str] = Header(default=None)):
    appointment = participant(appointment_id, authorization, doctor_only=True)
    if appointment["status"] != "CANCELLED":
        raise HTTPException(409, "Cancel the appointment before cleaning up its Google meeting")
    google.cancel_meeting(appointment_id)
    return {"status": "CANCELLED"}
