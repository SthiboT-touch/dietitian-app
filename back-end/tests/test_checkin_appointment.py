"""QR issue and role-scoped scan require an eligible confirmed appointment."""
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
    stores = [
        state.users_db, state.appointments_db, state.checkin_credentials_db,
        state.checkin_events_db, state.staff_accounts_db, state.staff_sessions_db,
        state.client_sessions_db, state.admin_sessions_db, state.dietitian_sessions_db,
    ]
    for store in stores:
        store.clear()
    state.client_sessions_db.update({"patient": "c", "other": "x"})
    state.admin_sessions_db["admin"] = "admin-account"
    state.dietitian_sessions_db["dietitian"] = "d"
    state.dietitian_sessions_db["other-dietitian"] = "other-dietitian"
    state.users_db["d"] = {"branch_id": "b"}
    state.staff_sessions_db["reception"] = "staff"
    state.staff_accounts_db["staff"] = {"role": "reception", "is_active": True, "branch_id": "b"}
    # Clinical sessions represent practitioners with a current reviewed card.
    for clinician_id in state.dietitian_sessions_db.values():
        clinician = state.users_db.setdefault(clinician_id, {"id": clinician_id, "type": "dietitian"})
        clinician.update(status="APPROVED", hpcsa_verified_until="2099-03-31")
    yield
    for store in stores:
        store.clear()


def appointment(status="CONFIRMED", days=1, branch="b"):
    state.appointments_db["a"] = {"appointment_id": "a", "client_id": "c", "dietitian_id": "d",
        "branch_id": branch, "status": status, "appointment_date": (datetime.now() + timedelta(days=days)).isoformat()}


def issue():
    return api.post("/api/v1/clients/c/checkin-code", headers=auth("patient"))


def scan(token, code):
    return api.post(
        "/api/v1/check-in/scan",
        json={"checkin_code": code},
        headers=auth(token),
    )


def test_no_appointment_cannot_issue_code():
    assert issue().status_code == 409
    assert not state.checkin_credentials_db


@pytest.mark.parametrize("status", ["PENDING", "CANCELLED", "REJECTED"])
def test_unconfirmed_appointment_cannot_issue_code(status):
    appointment(status)
    assert issue().status_code == 409


def test_past_appointment_cannot_issue_code():
    appointment(days=-2)
    assert issue().status_code == 409


def test_only_admin_or_assigned_dietitian_can_scan_single_use_qr():
    appointment()
    assert api.post("/api/v1/clients/c/checkin-code").status_code == 401
    assert api.post("/api/v1/clients/c/checkin-code", headers=auth("other")).status_code == 403
    response = issue()
    assert response.status_code == 200
    body = {"checkin_code": response.json()["checkin_code"]}
    assert scan("reception", body["checkin_code"]).status_code == 403
    checked_in = scan("dietitian", body["checkin_code"])
    assert checked_in.status_code == 201
    assert state.checkin_events_db[0]["actor_role"] == "dietitian"
    assert scan("dietitian", body["checkin_code"]).status_code == 404


def test_admin_can_scan_qr_and_is_recorded_as_actor():
    appointment()
    code = issue().json()["checkin_code"]

    response = scan("admin", code)

    assert response.status_code == 201
    assert state.checkin_events_db[0]["actor_id"] == "admin-account"
    assert state.checkin_events_db[0]["actor_role"] == "admin"


def test_cancelled_after_generation_cannot_be_scanned():
    appointment()
    code = issue().json()["checkin_code"]
    state.appointments_db["a"]["status"] = "CANCELLED"
    assert scan("dietitian", code).status_code == 409
    assert not state.checkin_events_db


def test_dietitian_cannot_scan_another_dietitians_appointment():
    appointment()
    code = issue().json()["checkin_code"]
    assert scan("other-dietitian", code).status_code == 403
    assert not state.checkin_events_db
