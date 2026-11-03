"""QR issue and reception scan require an eligible confirmed appointment."""
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
    stores = [state.users_db, state.appointments_db, state.checkin_credentials_db,
              state.checkin_events_db, state.staff_accounts_db, state.staff_sessions_db,
              state.client_sessions_db]
    for store in stores:
        store.clear()
    state.client_sessions_db.update({"patient": "c", "other": "x"})
    state.staff_sessions_db["reception"] = "staff"
    state.staff_accounts_db["staff"] = {"role": "reception", "is_active": True, "branch_id": "b"}
    yield
    for store in stores:
        store.clear()


def appointment(status="CONFIRMED", days=1, branch="b"):
    state.appointments_db["a"] = {"appointment_id": "a", "client_id": "c", "dietitian_id": "d",
        "branch_id": branch, "status": status, "appointment_date": (datetime.now() + timedelta(days=days)).isoformat()}


def issue():
    return api.post("/api/v1/clients/c/checkin-code", headers=auth("patient"))


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


def test_owner_only_and_confirmed_appointment_enables_single_use_qr():
    appointment()
    assert api.post("/api/v1/clients/c/checkin-code").status_code == 401
    assert api.post("/api/v1/clients/c/checkin-code", headers=auth("other")).status_code == 403
    response = issue()
    assert response.status_code == 200
    body = {"checkin_code": response.json()["checkin_code"]}
    assert api.post("/api/v1/reception/check-in", json=body, headers=auth("reception")).status_code == 201
    assert api.post("/api/v1/reception/check-in", json=body, headers=auth("reception")).status_code == 404


def test_cancelled_after_generation_cannot_be_scanned():
    appointment()
    code = issue().json()["checkin_code"]
    state.appointments_db["a"]["status"] = "CANCELLED"
    assert api.post("/api/v1/reception/check-in", json={"checkin_code": code}, headers=auth("reception")).status_code == 409
    assert not state.checkin_events_db


def test_wrong_branch_cannot_scan():
    appointment(branch="different")
    code = issue().json()["checkin_code"]
    assert api.post("/api/v1/reception/check-in", json={"checkin_code": code}, headers=auth("reception")).status_code == 409
    assert not state.checkin_events_db
