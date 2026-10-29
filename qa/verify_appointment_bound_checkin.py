"""Nonproduction QR eligibility tests. Never touches PostgreSQL or SMTP."""
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

os.environ["APP_USE_IN_MEMORY_DB"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back-end"))
if "database" not in sys.modules:
    sys.modules["database"] = types.ModuleType("database")

from fastapi import FastAPI
from fastapi.testclient import TestClient
import config
import state
from routers.onboarding import router as onboarding_router
from routers.appointments import router as appointment_router

config.DATABASE_ENABLED = False
app = FastAPI()
app.include_router(onboarding_router)
app.include_router(appointment_router)
api = TestClient(app)
for store in (
    state.appointments_db,
    state.client_sessions_db,
    state.staff_sessions_db,
    state.staff_accounts_db,
    state.checkin_credentials_db,
    state.users_db,
):
    store.clear()
state.checkin_events_db.clear()

client = "client-qr-test"
other = "another-client"
dietitian = "dietitian-qr-test"
branch = "branch-qr-test"
state.client_sessions_db["client-qr-token"] = client
state.client_sessions_db["other-qr-token"] = other
headers = {"Authorization": "Bearer client-qr-token"}
other_headers = {"Authorization": "Bearer other-qr-token"}
state.users_db[client] = {"id": client, "type": "client", "dietitian_id": dietitian}
state.users_db[dietitian] = {"id": dietitian, "type": "dietitian", "branch_id": branch}
state.staff_accounts_db["reception-qr-test"] = {
    "staff_id": "reception-qr-test", "role": "reception", "branch_id": branch, "is_active": True
}
state.staff_accounts_db["wrong-branch"] = {
    "staff_id": "wrong-branch", "role": "reception", "branch_id": "other-branch", "is_active": True
}
state.staff_sessions_db.update({"reception-qr-token": "reception-qr-test", "wrong-qr-token": "wrong-branch"})
staff_headers = {"Authorization": "Bearer reception-qr-token"}
wrong_branch_headers = {"Authorization": "Bearer wrong-qr-token"}

qr_url = f"/api/v1/clients/{client}/checkin-code"
appointments_url = f"/api/v1/clients/{client}/checkin-appointments"
# No appointment = no QR, even when authenticated.
assert api.get(appointments_url).status_code == 401
assert api.get(appointments_url, headers=headers).json() == []
assert api.post(qr_url, json={"appointment_id":"unknown"}, headers=headers).status_code == 409
assert api.post(qr_url, json={"appointment_id":"unknown"}).status_code == 401
assert api.post(qr_url, json={"appointment_id":"unknown"}, headers=other_headers).status_code == 403

when = (datetime.now() + timedelta(days=3)).isoformat()
book = api.post("/api/v1/appointments", json={"client_id":client,"dietitian_id":dietitian,"appointment_date":when}, headers=headers)
assert book.status_code == 200, book.text
appointment_id = book.json()["appointment"]["appointment_id"]
assert book.json()["appointment"]["status"] == "PENDING"
assert api.get(appointments_url, headers=headers).json() == []
assert api.post(qr_url, json={"appointment_id":appointment_id}, headers=headers).status_code == 409
# Only after dietitian approval.
state.appointments_db[appointment_id]["status"] = "CONFIRMED"
eligible = api.get(appointments_url, headers=headers)
assert eligible.status_code == 200 and len(eligible.json()) == 1
assert eligible.json()[0]["appointment_id"] == appointment_id
assert api.get(appointments_url, headers=other_headers).status_code == 403
issued = api.post(qr_url, json={"appointment_id":appointment_id}, headers=headers)
assert issued.status_code == 200, issued.text
assert issued.headers["cache-control"] == "no-store"
assert issued.json()["appointment_id"] == appointment_id
code = issued.json()["checkin_code"]
assert code.startswith("NC1:") and client not in code and "<svg" in issued.json()["qr_svg"]
# Staff at the wrong branch may not scan; proper branch can.
scan_url = "/api/v1/reception/check-in"
assert api.post(scan_url, json={"checkin_code":code},headers=wrong_branch_headers).status_code == 403
assert api.post(scan_url, json={"checkin_code":code},headers=staff_headers).status_code == 201
assert state.checkin_events_db[0]["appointment_id"] == appointment_id
assert api.post(scan_url, json={"checkin_code":code},headers=staff_headers).status_code == 404
assert api.post(qr_url, json={"appointment_id":appointment_id}, headers=headers).status_code == 409
# Cancellation invalidates an already issued QR, even if no one scanned it.
state.checkin_events_db.clear()
issued = api.post(qr_url, json={"appointment_id":appointment_id}, headers=headers)
code = issued.json()["checkin_code"]
state.appointments_db[appointment_id]["status"] = "CANCELLED"
assert api.post(scan_url, json={"checkin_code":code},headers=staff_headers).status_code == 409
assert api.post(qr_url, json={"appointment_id":appointment_id},headers=headers).status_code == 409
# Past appointments do not qualify.
state.appointments_db[appointment_id]["status"] = "CONFIRMED"
state.appointments_db[appointment_id]["appointment_date"] = (datetime.now()-timedelta(days=1)).isoformat()
assert api.get(appointments_url, headers=headers).json() == []
assert api.post(qr_url, json={"appointment_id":appointment_id}, headers=headers).status_code == 409
print("Appointment-bound QR API: booking, approval, branch matching, cancellation, expiry of appointment, reuse PASSED")
