"""Google integration tests with synthetic Google responses; no network/real tokens."""
from datetime import datetime, timedelta
from urllib.parse import urlsplit, parse_qs
import time
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import app
import config
import google_meet as google
import state

api = TestClient(app.app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "synthetic-client-secret")
    monkeypatch.setattr(config, "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8001/api/v1/integrations/google/callback")
    monkeypatch.setattr(config, "GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    stores = [state.users_db, state.client_sessions_db, state.dietitian_sessions_db,
              state.appointments_db, google.connections, google.meetings, google.oauth_states]
    for store in stores:
        store.clear()
    state.users_db["d"] = {"id": "d", "type": "dietitian", "status": "APPROVED"}
    state.users_db["c"] = {"id": "c", "type": "client", "dietitian_id": "d"}
    state.client_sessions_db.update({"patient": "c", "stranger": "x"})
    state.dietitian_sessions_db.update({"doctor": "d", "another": "other"})
    state.appointments_db["a"] = {"appointment_id": "a", "client_id": "c", "dietitian_id": "d", "status": "CONFIRMED", "consultation_type": "VIRTUAL", "appointment_date": (datetime.now() + timedelta(days=3)).isoformat()}
    monkeypatch.setattr(google, "google_request", lambda *a, **kw: pytest.fail("Unexpected Google request"))
    yield
    for store in stores:
        store.clear()


def connected(mode="calendar", expired=False):
    google.store_connection("d", {"access_token": "test-access-token", "refresh_token": "test-refresh-token", "expires_at": 0 if expired else time.time() + 3600}, mode)


def response(body=None, status=200):
    return httpx.Response(status, json=body if body is not None else {})


def test_unconfigured_installation_has_no_fake_meeting_links(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
    status = api.get("/api/v1/integrations/google", headers=auth("doctor"))
    assert status.json() == {"configured": False, "connected": False, "mode": "calendar"}
    assert api.post("/api/v1/integrations/google/connect", headers=auth("doctor")).status_code == 503
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("doctor")).status_code == 409


def test_oauth_is_approved_dietitian_only():
    assert api.post("/api/v1/integrations/google/connect").status_code == 401
    assert api.post("/api/v1/integrations/google/connect", headers=auth("patient")).status_code == 401
    state.users_db["d"]["status"] = "PENDING"
    assert api.post("/api/v1/integrations/google/connect", headers=auth("doctor")).status_code == 403


def test_oauth_pkce_state_exchange_encrypts_tokens_and_prevents_replay(monkeypatch):
    result = api.post("/api/v1/integrations/google/connect", headers=auth("doctor")).json()
    query = parse_qs(urlsplit(result["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert set(query["scope"][0].split()) == google.SCOPES
    calls = []

    def exchange(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response({"access_token": "oauth-access", "refresh_token": "oauth-refresh", "expires_in": 3600, "scope": " ".join(google.SCOPES)})

    monkeypatch.setattr(google, "google_request", exchange)
    callback = api.get("/api/v1/integrations/google/callback", params={"state": query["state"][0], "code": "synthetic-code"}, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["cache-control"] == "no-store"
    assert "code_verifier" in calls[0][2]["data"]
    assert "oauth-refresh" not in google.connections["d"]["encrypted_tokens"]
    assert google.load_connection("d")["tokens"]["refresh_token"] == "oauth-refresh"
    public = api.get("/api/v1/integrations/google", headers=auth("doctor"))
    assert public.json()["connected"] is True
    assert "oauth-access" not in public.text and "oauth-refresh" not in public.text
    assert api.get("/api/v1/integrations/google/callback", params={"state": query["state"][0], "code": "same"}).status_code == 400


def test_oauth_rejects_invalid_expired_or_cancelled_sessions():
    assert api.get("/api/v1/integrations/google/callback?state=invalid&code=code").status_code == 400
    url = google.authorize_url("d", "Bearer doctor")
    key = parse_qs(urlsplit(url).query)["state"][0]
    google.oauth_states[key]["expires_at"] = 0
    assert api.get("/api/v1/integrations/google/callback", params={"state": key, "code": "code"}).status_code == 400
    url = google.authorize_url("d", "Bearer doctor")
    key = parse_qs(urlsplit(url).query)["state"][0]
    state.dietitian_sessions_db.pop("doctor")
    assert api.get("/api/v1/integrations/google/callback", params={"state": key, "code": "code"}).status_code == 401


def test_calendar_creates_timed_meet_without_health_details_and_is_idempotent(monkeypatch):
    connected()
    calls = []

    def create(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response({"hangoutLink": "https://meet.google.com/abc-defg-hij"})

    monkeypatch.setattr(google, "google_request", create)
    result = api.post("/api/v1/appointments/a/meeting", headers=auth("doctor"))
    assert result.status_code == 200
    assert result.json()["status"] == "READY"
    body = calls[0][2]["json"]
    assert body["summary"] == "NutriCare virtual consultation"
    assert "attendees" not in body and "description" not in body
    assert body["start"]["timeZone"] == "Africa/Johannesburg"
    assert datetime.fromisoformat(body["end"]["dateTime"]) - datetime.fromisoformat(body["start"]["dateTime"]) == timedelta(minutes=30)
    assert calls[0][2]["params"]["conferenceDataVersion"] == 1
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("doctor")).status_code == 200
    assert len(calls) == 1
    assert api.get("/api/v1/appointments/a/meeting", headers=auth("patient")).json()["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert api.get("/api/v1/appointments/a/meeting", headers=auth("stranger")).status_code == 403
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("patient")).status_code == 403


def test_calendar_retry_reuses_same_event_and_handles_pending_conferences(monkeypatch):
    connected()
    calls = []

    def pending(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return response({"conferenceData": {"createRequest": {"status": {"statusCode": "pending"}}}})
        if method == "POST":
            return response(status=409)
        return response({"hangoutLink": "https://meet.google.com/abc-defg-hij"})

    monkeypatch.setattr(google, "google_request", pending)
    assert google.ensure_meeting("a")["status"] == "PENDING"
    assert google.ensure_meeting("a")["status"] == "READY"
    assert calls[0][2]["json"]["id"] == calls[1][2]["json"]["id"]
    assert calls[2][0] == "GET"


def test_meet_only_mode_uses_meet_api(monkeypatch):
    connected("meet")
    calls = []

    def create(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return response({"meetingUri": "https://meet.google.com/abc-defg-hij", "name": "spaces/test"})

    monkeypatch.setattr(google, "google_request", create)
    assert google.ensure_meeting("a")["status"] == "READY"
    assert calls[0][1] == "https://meet.googleapis.com/v2/spaces"
    assert calls[0][2]["json"]["config"]["accessType"] == "RESTRICTED"


def test_uncertain_meet_creation_is_not_repeated(monkeypatch):
    connected("meet")
    monkeypatch.setattr(google, "google_request", lambda *a, **kw: (_ for _ in ()).throw(HTTPException(503, "Google unavailable")))
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("doctor")).status_code == 503
    assert google.meetings["a"]["status"] == "UNKNOWN"
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("doctor")).status_code == 409


@pytest.mark.parametrize("status,kind", [("PENDING", "VIRTUAL"), ("CANCELLED", "VIRTUAL"), ("CONFIRMED", "INITIAL")])
def test_meetings_require_confirmed_virtual_appointment(status, kind):
    connected()
    state.appointments_db["a"].update(status=status, consultation_type=kind)
    assert api.post("/api/v1/appointments/a/meeting", headers=auth("doctor")).status_code == 409
    assert api.get("/api/v1/appointments/a/meeting", headers=auth("patient")).json()["meeting_url"] is None


def test_approval_creates_meeting_and_cancellation_hides_and_deletes_it(monkeypatch):
    connected()
    state.appointments_db["a"]["status"] = "PENDING"
    calls = []

    def google_calls(method, url, **kwargs):
        calls.append((method, url))
        return response({"hangoutLink": "https://meet.google.com/abc-defg-hij"}) if method == "POST" else response(status=204)

    monkeypatch.setattr(google, "google_request", google_calls)
    assert api.patch("/api/v1/appointments/a", json={"action": "APPROVED"}, headers=auth("doctor")).status_code == 200
    assert google.meetings["a"]["status"] == "READY"
    assert api.patch("/api/v1/appointments/a", json={"action": "CANCELLED"}, headers=auth("patient")).status_code == 200
    assert calls[-1][0] == "DELETE"
    assert api.get("/api/v1/appointments/a/meeting", headers=auth("patient")).json()["meeting_url"] is None


def test_google_failure_does_not_roll_back_appointment_approval(monkeypatch):
    connected()
    state.appointments_db["a"]["status"] = "PENDING"
    monkeypatch.setattr(google, "google_request", lambda *a, **kw: response(status=503))
    result = api.patch("/api/v1/appointments/a", json={"action": "APPROVED"}, headers=auth("doctor"))
    assert result.status_code == 200
    assert state.appointments_db["a"]["status"] == "CONFIRMED"
    assert result.json()["meeting_warning"]


def test_expired_tokens_refresh_and_keep_refresh_token_encrypted(monkeypatch):
    connected(expired=True)
    monkeypatch.setattr(google, "google_request", lambda *a, **kw: response({"access_token": "renewed-token", "expires_in": 3600}))
    assert google.access_token("d") == "renewed-token"
    assert google.load_connection("d")["tokens"]["refresh_token"] == "test-refresh-token"
    assert "renewed-token" not in google.connections["d"]["encrypted_tokens"]


def test_preferences_and_disconnect_are_private_and_revoke_google_access(monkeypatch):
    connected()
    assert api.patch("/api/v1/integrations/google", json={"mode": "meet"}, headers=auth("doctor")).status_code == 200
    assert google.load_connection("d")["mode"] == "meet"
    assert api.patch("/api/v1/integrations/google", json={"mode": "evil"}, headers=auth("doctor")).status_code == 422
    monkeypatch.setattr(google, "google_request", lambda *a, **kw: response())
    assert api.post("/api/v1/integrations/google/disconnect", headers=auth("doctor")).status_code == 200
    assert not google.load_connection("d")
