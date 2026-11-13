"""Virtual visit lifecycle and link access; no real meetings or provider calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient
import pytest

import app
import config
import state
from routers import appointments

api = TestClient(app.app)


def auth(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    stores = (state.users_db, state.clients_db, state.appointments_db,
              state.client_sessions_db, state.dietitian_sessions_db, state.admin_sessions_db)
    for store in stores:
        store.clear()
    state.users_db["private-patient-id"] = {
        "id": "private-patient-id", "type": "client", "full_name": "Synthetic Patient",
        "dietitian_id": "private-doctor-id",
    }
    state.client_sessions_db.update({"patient": "private-patient-id", "stranger": "someone-else"})
    state.dietitian_sessions_db.update({"doctor": "private-doctor-id", "other-doctor": "different-doctor"})
    state.admin_sessions_db["admin"] = "admin-account"
    # Clinical sessions represent practitioners with a current reviewed card.
    for clinician_id in state.dietitian_sessions_db.values():
        clinician = state.users_db.setdefault(clinician_id, {"id": clinician_id, "type": "dietitian"})
        clinician.update(status="APPROVED")
    yield
    for store in stores:
        store.clear()


def visit(key="visit", status="PENDING", format="VIRTUAL", link=None):
    record = {
        "appointment_id": key, "client_id": "private-patient-id", "dietitian_id": "private-doctor-id",
        "appointment_date": (datetime.now() + timedelta(days=1)).isoformat(),
        "appointment_type": format, "consultation_type": "FOLLOW_UP", "status": status,
        "meeting_link": link,
    }
    state.appointments_db[key] = record
    return record


def approve(key="visit", **extra):
    return api.patch(f"/api/v1/appointments/{key}", json={"action": "APPROVED", **extra}, headers=auth("doctor"))


def test_virtual_approval_creates_private_room_and_participants_receive_same_link():
    visit()
    path = "/api/v1/appointments/visit/meeting"
    assert api.get(path, headers=auth("patient")).status_code == 409
    assert api.patch("/api/v1/appointments/visit", json={"action": "APPROVED"}, headers=auth("patient")).status_code == 403
    result = approve()
    assert result.status_code == 200
    link = result.json()["appointment"]["meeting_link"]
    assert re.fullmatch(r"https://meet\.jit\.si/NutriCare-[a-f0-9]{64}", link)
    assert "private-patient-id" not in link and "private-doctor-id" not in link
    for token in ("patient", "doctor"):
        response = api.get(path, headers=auth(token))
        assert response.status_code == 200
        assert response.json()["meeting_link"] == link
        assert response.headers["cache-control"] == "no-store"
    assert api.get(path).status_code == 401
    for token in ("stranger", "other-doctor", "admin"):
        assert api.get(path, headers=auth(token)).status_code == 403
    # Administrative appointment listing remains available without exposing join secrets.
    assert api.get("/api/v1/appointments", headers=auth("admin")).json()[0]["meeting_link"] is None


def test_every_appointment_has_its_own_room_and_reapproval_cannot_rotate_it():
    visit("first")
    visit("second")
    first = approve("first").json()["appointment"]["meeting_link"]
    second = approve("second").json()["appointment"]["meeting_link"]
    assert first != second
    assert approve("first").status_code == 409
    assert state.appointments_db["first"]["meeting_link"] == first


def test_calendar_handles_timezone_aware_virtual_visits_without_os_timezone_data():
    record = visit(status="CONFIRMED", link="https://meet.jit.si/example-room")
    record["appointment_date"] = (datetime.now(timezone(timedelta(hours=2))) + timedelta(days=1)).isoformat()
    response = api.get("/api/v1/appointments/calendar", headers=auth("doctor"))
    assert response.status_code == 200
    assert response.json()[0]["meeting_link"] == record["meeting_link"]
    assert response.json()[0]["client_name"] == "Synthetic Patient"


def test_link_backfill_is_idempotent_even_for_simultaneous_retries():
    visit(status="CONFIRMED")
    path = "/api/v1/appointments/visit/meeting"
    def create(_):
        response = api.post(path, headers=auth("doctor"))
        assert response.status_code == 200
        return response.json()["meeting_link"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        links = list(pool.map(create, range(8)))
    assert len(set(links)) == 1
    assert state.appointments_db["visit"]["meeting_link"] == links[0]


def test_supplied_provider_link_is_preserved_by_approval_and_backfill():
    visit()
    link = "https://meet.google.com/abc-defg-hij"
    assert approve(meeting_link=link).json()["appointment"]["meeting_link"] == link
    assert api.post("/api/v1/appointments/visit/meeting", headers=auth("doctor")).json()["meeting_link"] == link


def test_cancellation_clears_app_link_and_blocks_further_access():
    visit()
    approve()
    cancelled = api.patch("/api/v1/appointments/visit", json={"action": "CANCELLED"}, headers=auth("patient"))
    assert cancelled.status_code == 200
    assert cancelled.json()["appointment"]["meeting_link"] is None
    assert state.appointments_db["visit"]["meeting_link"] is None
    assert api.get("/api/v1/appointments/visit/meeting", headers=auth("patient")).status_code == 409
    assert api.post("/api/v1/appointments/visit/meeting", headers=auth("doctor")).status_code == 409


@pytest.mark.parametrize("status", ["PENDING", "CANCELLED", "REJECTED", "COMPLETED"])
def test_inactive_appointments_cannot_create_or_expose_meeting_links(status):
    visit(status=status, link="https://meet.jit.si/old-room")
    path = "/api/v1/appointments/visit/meeting"
    assert api.post(path, headers=auth("doctor")).status_code == 409
    assert api.get(path, headers=auth("patient")).status_code == 409
    assert api.get("/api/v1/appointments", headers=auth("patient")).json()[0]["meeting_link"] is None


@pytest.mark.parametrize("token", ["patient", "stranger", "other-doctor", "admin"])
def test_only_appointment_dietitian_can_create_a_missing_link(token):
    visit(status="CONFIRMED")
    assert api.post("/api/v1/appointments/visit/meeting", headers=auth(token)).status_code == 403
    assert state.appointments_db["visit"]["meeting_link"] is None


def test_in_person_approval_does_not_create_a_video_room():
    visit(format="IN_PERSON")
    result = approve()
    assert result.status_code == 200
    assert result.json()["appointment"]["meeting_link"] is None
    assert api.post("/api/v1/appointments/visit/meeting", headers=auth("doctor")).status_code == 409


@pytest.mark.parametrize("link", ["javascript:alert(1)", "http://meet.jit.si/example", "https://name:password@example.com/room"])
def test_invalid_manual_links_do_not_approve_appointment(link):
    visit()
    assert approve(meeting_link=link).status_code == 422
    assert state.appointments_db["visit"]["status"] == "PENDING"


def test_postgres_link_backfill_locks_existing_row_and_reuses_its_link(monkeypatch):
    row = visit(status="CONFIRMED")
    statements = []
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            statements.append((sql, params))
            if sql.startswith("UPDATE appointment SET meeting_link"):
                row["meeting_link"] = params[0]
        def fetchone(self):
            if "FROM dietitian WHERE dietitian_id" in self.sql:
                return {"status": "APPROVED"}
            return dict(row)
    @contextmanager
    def cursor():
        yield Cursor()
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(appointments.database, "cursor", cursor)
    first = api.post("/api/v1/appointments/visit/meeting", headers=auth("doctor"))
    second = api.post("/api/v1/appointments/visit/meeting", headers=auth("doctor"))
    assert first.status_code == second.status_code == 200
    assert first.json()["meeting_link"] == second.json()["meeting_link"] == row["meeting_link"]
    assert any("FOR UPDATE" in sql for sql, _ in statements)


def test_postgres_approval_stores_generated_link_with_status_change(monkeypatch):
    row = visit()
    row["is_future"] = True
    statements = []
    class Cursor:
        def execute(self, sql, params):
            self.sql = sql
            statements.append((sql, params))
            if "SET status = %s, meeting_link = %s" in sql:
                row["status"], row["meeting_link"] = params[:2]
        def fetchone(self):
            if "FROM dietitian WHERE dietitian_id" in self.sql:
                return {"status": "APPROVED"}
            return {**row, "appointment_date": datetime.now() + timedelta(days=1)}
    @contextmanager
    def cursor():
        yield Cursor()
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(appointments.database, "cursor", cursor)
    result = approve()
    assert result.status_code == 200
    assert result.json()["appointment"]["meeting_link"] == row["meeting_link"]
    assert row["status"] == "CONFIRMED"
    assert row["meeting_link"].startswith("https://meet.jit.si/NutriCare-")
