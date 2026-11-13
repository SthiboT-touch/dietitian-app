"""Care workflow integration tests, isolated from production services."""
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
import app
import config
import state

api = TestClient(app.app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    stores = [state.users_db, state.clients_db, state.appointments_db,
              state.client_sessions_db, state.dietitian_sessions_db, state.goals_db]
    for store in stores:
        store.clear()
    state.users_db.update({
        "c": {"id": "c", "type": "client", "dietitian_id": "d"},
        "other": {"id": "other", "type": "client", "dietitian_id": "x"},
        "d": {"id": "d", "type": "dietitian", "status": "APPROVED", "branch_id": "b"},
    })
    state.clients_db["c"] = {"progress": []}
    state.client_sessions_db.update({"patient": "c", "stranger": "other"})
    state.dietitian_sessions_db.update({"clinician": "d", "unassigned": "x"})
    # Clinical sessions represent practitioners with a current reviewed card.
    for clinician_id in state.dietitian_sessions_db.values():
        clinician = state.users_db.setdefault(clinician_id, {"id": clinician_id, "type": "dietitian"})
        clinician.update(status="APPROVED")
    yield
    for store in stores:
        store.clear()


def test_history_versions_and_record_access():
    path = "/api/v1/clients/c/care"
    assert api.get(path).status_code == 401
    assert api.get(path, headers=auth("stranger")).status_code == 403
    assert api.get(path, headers=auth("unassigned")).status_code == 403
    for concern in ["First history", "Updated history"]:
        assert api.post(path + "/history", json={"concerns": concern}, headers=auth("patient")).status_code == 200
    events = api.get(path, headers=auth("clinician")).json()
    assert len(events) == 2
    assert events[0]["payload"]["concerns"] == "First history"
    assert events[1]["payload"]["concerns"] == "Updated history"
    assert api.post(path + "/history", json={}, headers=auth("patient")).status_code == 422


def test_clinician_review_preserves_original_measurements_after_edit():
    state.appointments_db["completed"] = {"appointment_id": "completed", "client_id": "c", "dietitian_id": "d", "status": "COMPLETED", "appointment_date": (datetime.now() - timedelta(days=1)).isoformat()}
    path = "/api/v1/clients/c"
    assert api.post(path + "/progress", json={"weight_kg": 70}, headers=auth("patient")).status_code == 403
    assert api.post(path + "/progress", json={"weight_kg": 70}, headers=auth("clinician")).status_code == 200
    log_date = api.get(path + "/progress", headers=auth("patient")).json()[0]["log_date"]
    review = {"log_date": log_date, "decision": "APPROVED", "notes": "Reviewed measurements"}
    assert api.post(path + "/care/progress-reviews", json=review, headers=auth("patient")).status_code == 403
    assert api.post(path + "/care/progress-reviews", json=review, headers=auth("clinician")).status_code == 200
    api.post(path + "/progress", json={"weight_kg": 71}, headers=auth("clinician"))
    events = api.get(path + "/care", headers=auth("patient")).json()
    assert events[0]["payload"]["snapshot"]["weight_kg"] == 70
    review["decision"] = "CHANGES_REQUESTED"
    assert api.post(path + "/care/progress-reviews", json=review, headers=auth("clinician")).status_code == 200
    review["log_date"] = "1900-01-01"
    assert api.post(path + "/care/progress-reviews", json=review, headers=auth("clinician")).status_code == 404


def test_recommendations_are_clinician_only_and_shared_with_patient():
    state.appointments_db["completed"] = {"appointment_id": "completed", "client_id": "c", "dietitian_id": "d", "status": "COMPLETED", "appointment_date": (datetime.now() - timedelta(days=1)).isoformat()}
    path = "/api/v1/clients/c/care"
    assert api.post(path + "/recommendations", json={"content": "Follow the reviewed plan"}, headers=auth("patient")).status_code == 403
    assert api.post(path + "/recommendations", json={"content": "Follow the reviewed plan"}, headers=auth("clinician")).status_code == 200
    assert api.get(path, headers=auth("patient")).json()[0]["kind"] == "RECOMMENDATION"


def test_booking_branch_consultation_validation_and_roundtrip():
    booking = {"client_id": "c", "dietitian_id": "d", "branch_id": "b", "consultation_type": "FOLLOW_UP",
               "appointment_date": (datetime.now() + timedelta(days=2))
               .replace(hour=8, minute=0, second=0, microsecond=0)
               .isoformat()}
    response = api.post("/api/v1/appointments", json=booking, headers=auth("patient"))
    assert response.status_code == 200
    assert response.json()["appointment"]["branch_id"] == "b"
    stored = api.get("/api/v1/appointments", headers=auth("patient")).json()[0]
    assert stored["consultation_type"] == "FOLLOW_UP"
    assert stored["visit_type"] == "follow_up"
    booking["branch_id"] = "wrong"
    assert api.post("/api/v1/appointments", json=booking, headers=auth("patient")).status_code == 422
    booking["branch_id"] = "b"
    booking["consultation_type"] = "invalid"
    assert api.post("/api/v1/appointments", json=booking, headers=auth("patient")).status_code == 422


def test_existing_appointment_format_and_manual_meeting_link_are_preserved():
    booking = {
        "client_id": "c", "dietitian_id": "d", "branch_id": "b",
        "consultation_type": "FOLLOW_UP", "appointment_type": "VIRTUAL",
        "appointment_date": (datetime.now() + timedelta(days=2))
        .replace(hour=8, minute=0, second=0, microsecond=0)
        .isoformat(),
    }
    created = api.post("/api/v1/appointments", json=booking, headers=auth("patient"))
    assert created.status_code == 200
    appointment_id = created.json()["appointment"]["appointment_id"]
    url = f"/api/v1/appointments/{appointment_id}"
    approved = api.patch(url, json={"action": "APPROVED", "meeting_link": "https://meet.google.com/abc-defg-hij"}, headers=auth("clinician"))
    assert approved.status_code == 200
    stored = api.get("/api/v1/appointments", headers=auth("patient")).json()[0]
    assert stored["status"] == "CONFIRMED"
    assert stored["branch_id"] == "b"
    assert stored["consultation_type"] == "FOLLOW_UP"
    assert stored["appointment_type"] == "VIRTUAL"
    assert stored["meeting_link"] == "https://meet.google.com/abc-defg-hij"


@pytest.mark.parametrize("value", [{}, {"sleep_hours": 25}, {"weight_kg": -1}, {"body_fat_pct": 101}, {"water_ml": -2}])
def test_invalid_progress_rejected(value):
    assert api.post("/api/v1/clients/c/progress", json=value, headers=auth("clinician")).status_code == 422


def test_database_events_encode_decimal_measurements(monkeypatch):
    from contextlib import contextmanager
    from decimal import Decimal
    from routers import care
    statements = []

    class Cursor:
        def execute(self, sql, parameters):
            statements.append((sql, parameters))

    @contextmanager
    def cursor():
        yield Cursor()

    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(care.database, "cursor", cursor)
    care.save("c", "PROGRESS_REVIEW", "d", {"snapshot": {"weight_kg": Decimal("70.1")}})
    import json
    assert json.loads(statements[0][1][-1])["snapshot"]["weight_kg"] == 70.1
