"""Nonproduction API acceptance tests for FR-1.4 through FR-1.9.

Never opens PostgreSQL, SMTP, or a live URL. Uses isolated in-memory FastAPI.
"""

import os
import sys
import types
import base64
import io
from pathlib import Path
from PIL import Image

os.environ["APP_USE_IN_MEMORY_DB"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back-end"))
try:
    import database  # noqa: F401 - check whether the real database module can load
except ImportError:
    sys.modules["database"] = types.ModuleType("database")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import config
import state
from routers.auth_admin import router as auth_router
from routers.onboarding import router as onboarding_router
from routers.clients import router as clients_router

config.DATABASE_ENABLED = False
app = FastAPI()
for router in (auth_router, onboarding_router, clients_router):
    app.include_router(router)
api = TestClient(app)

for store in (
    state.users_db,
    state.admins_db,
    state.staff_accounts_db,
    state.client_sessions_db,
    state.staff_sessions_db,
    state.welcome_outbox_db,
    state.client_registration_consents_db,
    state.profile_photos_db,
    state.client_documents_db,
    state.checkin_credentials_db,
):
    store.clear()
state.checkin_events_db.clear()

buf = io.BytesIO()
Image.new("RGB", (24, 24), "white").save(buf, format="PNG")
photo_bytes = buf.getvalue()
pdf_bytes = b"%PDF-1.4\n1 0 obj\n<</Type/Catalog>>\nendobj\n%%EOF"
photo = {
    "filename": "portrait.png",
    "content_type": "image/png",
    "data_base64": base64.b64encode(photo_bytes).decode(),
}
document = {
    "filename": "clinic-note.pdf",
    "content_type": "application/pdf",
    "data_base64": base64.b64encode(pdf_bytes).decode(),
}
BASE = {
    "first_name": "Jordan",
    "last_name": "Sample",
    "email": "jordan@example.test",
    "id_number": "9005140012345",
    "phone": "0821234567",
    "date_of_birth": "1990-05-14",
    "gender": "other",
    "password": "ExamplePass123!",
    "privacy_notice_version": "2026-10-28-v1",
    "consent_to_care": True,
}
# FR-1.6: malformed or mismatched content must be rejected BEFORE account creation.
for bad in (
    {**photo, "content_type": "image/jpeg"},
    {**photo, "data_base64": "invalid++"},
    {**photo, "filename": "../../bad.png"},
):
    r = api.post("/api/v1/auth/register/client", json={**BASE, "profile_photo": bad})
    assert r.status_code == 422, r.text
assert not state.users_db

r = api.post(
    "/api/v1/auth/register/client",
    json={**BASE, "profile_photo": photo, "initial_document": document},
)
assert r.status_code == 200, r.text
user = r.json()["user"]
client_id = user["id"]
assert len(client_id) == 36 and client_id in state.users_db  # FR-1.4 full UUID
assert client_id in state.client_registration_consents_db
assert (
    client_id in state.welcome_outbox_db
    and state.welcome_outbox_db[client_id]["status"] == "PENDING"
)
assert client_id in state.profile_photos_db
assert any(d["client_id"] == client_id for d in state.client_documents_db.values())
assert "data_base64" not in r.text and BASE["password"] not in r.text

login = api.post("/api/v1/auth/login", json={"email": BASE["email"], "password": BASE["password"]})
assert login.status_code == 200, login.text
headers = {"Authorization": "Bearer " + login.json()["access_token"]}
assert api.get(f"/api/v1/clients?client_id={client_id}", headers=headers).status_code == 200
r = api.get(f"/api/v1/clients/{client_id}/profile-photo", headers=headers)
assert (
    r.status_code == 200
    and r.content == photo_bytes
    and r.headers["cache-control"] == "private, no-store"
)
assert api.get(f"/api/v1/clients/{client_id}/profile-photo").status_code == 401

# FR-1.9: another email with same SA ID fails without creating a patient.
r = api.post("/api/v1/auth/register/client", json={**BASE, "email": "different@example.test"})
assert (
    r.status_code == 409
    and len([u for u in state.users_db.values() if u.get("type") == "client"]) == 1
)
r = api.post("/api/v1/auth/register/client", json={**BASE, "id_number": "9005140012352"})
assert r.status_code == 409

# FR-1.7: only patient owner can request QR; reception can scan and record.
assert api.post(f"/api/v1/clients/{client_id}/checkin-code").status_code == 401
qr = api.post(f"/api/v1/clients/{client_id}/checkin-code", headers=headers)
assert qr.status_code == 200, qr.text
code = qr.json()["checkin_code"]
assert code.startswith("NC1:") and "<svg" in qr.json()["qr_svg"]
assert qr.headers["cache-control"] == "no-store"
assert BASE["id_number"] not in qr.text
staff_id = "reception-sample"
state.staff_accounts_db[staff_id] = {
    "staff_id": staff_id,
    "role": "reception",
    "branch_id": "branch-test",
    "is_active": True,
    "full_name": "Test Reception",
    "email": "frontdesk@example.test",
}
state.staff_sessions_db["staff-test-token"] = staff_id
staff_headers = {"Authorization": "Bearer staff-test-token"}
assert api.post("/api/v1/reception/check-in", json={"checkin_code": code}).status_code == 401
result = api.post("/api/v1/reception/check-in", json={"checkin_code": code}, headers=staff_headers)
assert result.status_code == 201, result.text
assert len(state.checkin_events_db) == 1
assert (
    api.post(
        "/api/v1/reception/check-in", json={"checkin_code": code}, headers=staff_headers
    ).status_code
    == 404
)
qr2 = api.post(f"/api/v1/clients/{client_id}/checkin-code", headers=headers)
assert qr2.status_code == 200
assert (
    api.post(
        "/api/v1/reception/check-in", json={"checkin_code": code}, headers=staff_headers
    ).status_code
    == 404
)
# Explicit expiry prevents stale/photographed QR codes from remaining useful.
expired = api.post(f"/api/v1/clients/{client_id}/checkin-code", headers=headers)
state.checkin_credentials_db[client_id]["expires_at"] = 0
assert (
    api.post(
        "/api/v1/reception/check-in",
        json={"checkin_code": expired.json()["checkin_code"]},
        headers=staff_headers,
    ).status_code
    == 404
)

# FR-1.8: receptionist may assist only with explicit consent; patient creates password.
ASSISTED = {**BASE, "email": "assisted@example.test", "id_number": "9005140012352"}
assert api.post("/api/v1/auth/register/client/assisted", json=ASSISTED).status_code == 401
assert (
    api.post(
        "/api/v1/auth/register/client/assisted",
        json={**ASSISTED, "consent_to_care": False},
        headers=staff_headers,
    ).status_code
    == 422
)
registered = api.post("/api/v1/auth/register/client/assisted", json=ASSISTED, headers=staff_headers)
assert registered.status_code == 200, registered.text
assisted_id = registered.json()["user"]["id"]
consent = state.client_registration_consents_db[assisted_id]
assert consent["registration_mode"] == "ASSISTED" and consent["registered_by_staff_id"] == staff_id
assert (
    api.post(
        "/api/v1/auth/login", json={"email": ASSISTED["email"], "password": ASSISTED["password"]}
    ).status_code
    == 200
)
print(
    "PASS: FR-1.4 unique profiles, FR-1.5 queued emails, FR-1.6 protected uploads, FR-1.7 private QR, FR-1.8 assisted registration, FR-1.9 duplicate IDs"
)
