"""Google Calendar/Meet clients, encrypted OAuth storage and visit-specific links.

Google receives appointment time and a generic title, never patient health history.
Connections and links use PostgreSQL, or temporary stores in development.
"""
import base64
import hashlib
import json
import re
import secrets
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import RLock
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
import config
import database
from state import appointments_db

SCOPES = {"https://www.googleapis.com/auth/calendar.events.owned", "https://www.googleapis.com/auth/meetings.space.created"}
connections = {}
meetings = {}
oauth_states = {}
lock = RLock()
_development_key = Fernet.generate_key()


def configured():
    uri = urlsplit(config.GOOGLE_REDIRECT_URI)
    secure_redirect = uri.scheme == "https" or (uri.scheme == "http" and uri.hostname in {"127.0.0.1", "localhost"})
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and secure_redirect and uri.path == "/api/v1/integrations/google/callback" and (not config.DATABASE_ENABLED or config.GOOGLE_TOKEN_ENCRYPTION_KEY))


def cipher():
    key = config.GOOGLE_TOKEN_ENCRYPTION_KEY
    if not key and config.DATABASE_ENABLED:
        raise HTTPException(503, "Google token encryption is not configured")
    try:
        return Fernet(key.encode() if key else _development_key)
    except (ValueError, TypeError):
        raise HTTPException(503, "Google token encryption is not configured correctly") from None


def load_connection(dietitian_id):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT encrypted_tokens, meeting_mode FROM dietitian_google_connection WHERE dietitian_id=%s", (dietitian_id,))
            row = cursor.fetchone()
    else:
        row = connections.get(dietitian_id)
    if not row:
        return None
    try:
        return {"tokens": json.loads(cipher().decrypt(row["encrypted_tokens"].encode())), "mode": row["meeting_mode"]}
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(409, "Reconnect Google to restore this connection") from None


def store_connection(dietitian_id, tokens, mode="calendar"):
    encrypted = cipher().encrypt(json.dumps(tokens).encode()).decode()
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO dietitian_google_connection(dietitian_id,encrypted_tokens,meeting_mode) VALUES (%s,%s,%s) ON CONFLICT(dietitian_id) DO UPDATE SET encrypted_tokens=EXCLUDED.encrypted_tokens, meeting_mode=EXCLUDED.meeting_mode, updated_at=NOW()", (dietitian_id, encrypted, mode))
    else:
        connections[dietitian_id] = {"encrypted_tokens": encrypted, "meeting_mode": mode}


def google_request(method, url, **kwargs):
    try:
        return httpx.request(method, url, timeout=20, follow_redirects=False, **kwargs)
    except httpx.HTTPError:
        raise HTTPException(503, "Google is temporarily unavailable. Try again shortly.") from None


def access_token(dietitian_id):
    connection = load_connection(dietitian_id)
    if not connection:
        raise HTTPException(409, "Connect Google in Settings before creating a virtual meeting")
    tokens = connection["tokens"]
    if tokens.get("expires_at", 0) > time.time() + 60:
        return tokens["access_token"]
    if not tokens.get("refresh_token"):
        raise HTTPException(409, "Reconnect Google in Settings")
    response = google_request("POST", "https://oauth2.googleapis.com/token", data={"client_id": config.GOOGLE_CLIENT_ID, "client_secret": config.GOOGLE_CLIENT_SECRET, "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
    if response.status_code != 200:
        raise HTTPException(409, "Reconnect Google in Settings to renew access")
    try:
        fresh = response.json()
        tokens.update(access_token=fresh["access_token"], expires_at=time.time() + int(fresh.get("expires_in", 3600)))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "Google returned an invalid authentication response") from None
    store_connection(dietitian_id, tokens, connection["mode"])
    return tokens["access_token"]


def authorize_url(dietitian_id, session):
    if not configured():
        raise HTTPException(503, "Google meetings are not configured on this installation")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with lock:
        for key in list(oauth_states):
            if oauth_states[key]["expires_at"] < time.time() or oauth_states[key]["dietitian_id"] == dietitian_id:
                oauth_states.pop(key, None)
        oauth_states[state] = {"dietitian_id": dietitian_id, "session": session, "verifier": verifier, "expires_at": time.time() + 600}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({"client_id": config.GOOGLE_CLIENT_ID, "redirect_uri": config.GOOGLE_REDIRECT_URI, "response_type": "code", "scope": " ".join(sorted(SCOPES)), "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})


def finish_authorization(state, code, error=None):
    with lock:
        pending = oauth_states.pop(state, None)
    if not pending or pending["expires_at"] < time.time():
        raise HTTPException(400, "Google connection expired. Start again from Settings.")
    from security import require_dietitian
    if require_dietitian(pending["session"]) != pending["dietitian_id"]:
        raise HTTPException(403, "Sign in again before connecting Google")
    if error or not code:
        raise HTTPException(400, "Google connection was not authorized. You can try again from Settings.")
    response = google_request("POST", "https://oauth2.googleapis.com/token", data={"client_id": config.GOOGLE_CLIENT_ID, "client_secret": config.GOOGLE_CLIENT_SECRET, "redirect_uri": config.GOOGLE_REDIRECT_URI, "grant_type": "authorization_code", "code": code, "code_verifier": pending["verifier"]})
    if response.status_code != 200:
        raise HTTPException(400, "Google connection failed. Start again from Settings.")
    try:
        tokens = response.json()
        if not tokens.get("access_token") or not tokens.get("refresh_token") or not SCOPES.issubset(set(tokens.get("scope", "").split())):
            raise ValueError()
        tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600))
    except (ValueError, TypeError):
        raise HTTPException(400, "Grant both Calendar and Meet access to connect Google") from None
    store_connection(pending["dietitian_id"], tokens)


def appointment_record(appointment_id):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT appointment_id, client_id, dietitian_id, date_time AS appointment_date, duration, status, consultation_type FROM appointment WHERE appointment_id=%s", (appointment_id,))
            row = cursor.fetchone()
        return dict(row) if row else None
    return appointments_db.get(appointment_id)


def load_meeting(appointment_id):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("SELECT * FROM appointment_meeting WHERE appointment_id=%s", (appointment_id,))
            row = cursor.fetchone()
        return dict(row) if row else None
    return meetings.get(appointment_id)


def save_meeting(record):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO appointment_meeting(appointment_id,dietitian_id,meeting_mode,meeting_url,google_event_id,google_space_name,status,message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(appointment_id) DO UPDATE SET meeting_url=EXCLUDED.meeting_url,google_event_id=EXCLUDED.google_event_id,google_space_name=EXCLUDED.google_space_name,status=EXCLUDED.status,message=EXCLUDED.message,updated_at=NOW()", tuple(record.get(key) for key in ("appointment_id", "dietitian_id", "meeting_mode", "meeting_url", "google_event_id", "google_space_name", "status", "message")))
    else:
        meetings[record["appointment_id"]] = dict(record)


def safe_meet_url(value):
    return bool(isinstance(value, str) and re.fullmatch(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", value))


@contextmanager
def meeting_lock(appointment_id):
    # Calendar event IDs are deterministic too, preventing duplicates after retries/restarts.
    with lock:
        if config.DATABASE_ENABLED:
            with database.cursor() as cursor:
                key = int.from_bytes(hashlib.sha256(appointment_id.encode()).digest()[:8], "big", signed=True)
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
                yield
        else:
            yield


def ensure_meeting(appointment_id):
    with meeting_lock(appointment_id):
        appointment = appointment_record(appointment_id)
        if not appointment or appointment.get("consultation_type") != "VIRTUAL" or appointment["status"] not in {"CONFIRMED", "SCHEDULED"}:
            raise HTTPException(409, "Only confirmed virtual appointments can have a meeting")
        existing = load_meeting(appointment_id)
        if existing and existing["status"] == "READY":
            return existing
        connection = load_connection(str(appointment["dietitian_id"]))
        if not configured() or not connection:
            raise HTTPException(409, "The dietitian needs to connect Google in Settings first")
        mode = existing["meeting_mode"] if existing else connection["mode"]
        if mode == "meet" and existing and existing["status"] == "UNKNOWN":
            raise HTTPException(409, "Google did not confirm this Meet request. Check your Google account before creating another meeting.")
        headers = {"Authorization": "Bearer " + access_token(str(appointment["dietitian_id"]))}
        record = {"appointment_id": appointment_id, "dietitian_id": str(appointment["dietitian_id"]), "meeting_mode": mode, "status": "PENDING"}
        if mode == "calendar":
            event_id = "nc" + hashlib.sha256(appointment_id.encode()).hexdigest()[:40]
            record["google_event_id"] = event_id
            # Retain the event ID even if the response is lost, so cancellation
            # and retries can find an event that Google may already have created.
            record["message"] = "Google is preparing the meeting link. Check again shortly."
            save_meeting(record)
            when = appointment["appointment_date"]
            when = datetime.fromisoformat(when.replace("Z", "+00:00")) if isinstance(when, str) else when
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone(timedelta(hours=2)))
            body = {"id": event_id, "summary": "NutriCare virtual consultation", "start": {"dateTime": when.isoformat(), "timeZone": "Africa/Johannesburg"}, "end": {"dateTime": (when + timedelta(minutes=appointment.get("duration") or 30)).isoformat(), "timeZone": "Africa/Johannesburg"}, "conferenceData": {"createRequest": {"requestId": event_id, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}
            response = google_request("POST", "https://www.googleapis.com/calendar/v3/calendars/primary/events", headers=headers, params={"conferenceDataVersion": 1, "sendUpdates": "none"}, json=body)
            if response.status_code == 409:
                response = google_request("GET", "https://www.googleapis.com/calendar/v3/calendars/primary/events/" + event_id, headers=headers)
            if response.status_code not in {200, 201}:
                raise HTTPException(502, "Google Calendar could not create this meeting. Check your Google permissions and try again.")
            try:
                event = response.json()
                url = event.get("hangoutLink") or next((entry.get("uri") for entry in event.get("conferenceData", {}).get("entryPoints", []) if entry.get("entryPointType") == "video"), None)
                failed = event.get("conferenceData", {}).get("createRequest", {}).get("status", {}).get("statusCode") == "failure"
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(502, "Google returned an invalid meeting response") from None
            if failed or event.get("status") == "cancelled":
                raise HTTPException(409, "Google could not prepare the conference. Check the event in Google Calendar.")
        else:
            # Meet spaces.create has no idempotency key. Persist ambiguity before sending.
            record["status"] = "UNKNOWN"
            save_meeting(record)
            response = google_request("POST", "https://meet.googleapis.com/v2/spaces", headers=headers, json={"config": {"accessType": "RESTRICTED"}})
            if response.status_code not in {200, 201}:
                raise HTTPException(502, "Google Meet could not create the meeting. Check your Google account.")
            try:
                space = response.json()
                url = space.get("meetingUri")
                record["google_space_name"] = space.get("name")
            except (ValueError, AttributeError):
                raise HTTPException(502, "Google returned an invalid meeting response") from None
        if url and not safe_meet_url(url):
            raise HTTPException(502, "Google returned an invalid meeting link")
        record.update(meeting_url=url, status="READY" if url else "PENDING", message=None if url else "Google is preparing the meeting link. Check again shortly.")
        save_meeting(record)
        return record


def cancel_meeting(appointment_id):
    with meeting_lock(appointment_id):
        record = load_meeting(appointment_id)
        if not record or record["status"] == "CANCELLED":
            return
        record.update(status="CANCEL_PENDING", message="Appointment cancelled. Google calendar cleanup is pending.")
        save_meeting(record)
        headers = {"Authorization": "Bearer " + access_token(record["dietitian_id"])}
        if record.get("google_event_id"):
            response = google_request("DELETE", "https://www.googleapis.com/calendar/v3/calendars/primary/events/" + record["google_event_id"], headers=headers, params={"sendUpdates": "none"})
            if response.status_code not in {200, 204, 404, 410}:
                raise HTTPException(502, "Appointment cancelled, but Google Calendar cleanup needs to be retried")
        elif record.get("google_space_name"):
            response = google_request("POST", "https://meet.googleapis.com/v2/" + record["google_space_name"] + ":endActiveConference", headers=headers, json={})
            if response.status_code not in {200, 204, 400, 404}:
                raise HTTPException(502, "Appointment cancelled, but the active Google conference could not be ended")
        record.update(status="CANCELLED", message=None)
        save_meeting(record)


def after_appointment_change(appointment_id, status):
    try:
        if status == "CONFIRMED":
            ensure_meeting(appointment_id)
        elif status == "CANCELLED":
            cancel_meeting(appointment_id)
    except HTTPException as error:
        # Appointment decisions remain authoritative even when Google is unavailable.
        return error.detail
    return None
