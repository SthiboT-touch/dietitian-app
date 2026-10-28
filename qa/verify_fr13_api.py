"""FR-1.3 API checks; isolated in-memory FastAPI, no production traffic."""

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

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
from routers.auth_admin import router

config.DATABASE_ENABLED = False
app = FastAPI()
app.include_router(router)
api = TestClient(app, client=("198.51.100.25", 32123))

VALID = {
    "first_name": "Taylor",
    "last_name": "Example",
    "email": "consent-test@example.test",
    "id_number": "9005140012345",
    "phone": "0821234567",
    "date_of_birth": "1990-05-14",
    "gender": "other",
    "password": "testpassword123",
    "consent_to_care": True,
    "privacy_notice_version": "2026-10-28-v1",
}

state.users_db.clear()
state.client_registration_consents_db.clear()
for invalid in (
    {"consent_to_care": False},
    {"consent_to_care": None},
    {"privacy_notice_version": "outdated-v1"},
    {"privacy_notice_version": None},
):
    response = api.post("/api/v1/auth/register/client", json={**VALID, **invalid})
    assert response.status_code == 422, (invalid, response.text)
for missing in ("consent_to_care", "privacy_notice_version"):
    request_body = {k: v for k, v in VALID.items() if k != missing}
    response = api.post("/api/v1/auth/register/client", json=request_body)
    assert response.status_code == 422, (missing, response.text)
assert len(state.users_db) == 0
response = api.post("/api/v1/auth/register/client", json=VALID)
assert response.status_code == 200, response.text
client_id = response.json()["user"]["id"]
consent = state.client_registration_consents_db[client_id]
assert consent["privacy_notice_version"] == "2026-10-28-v1"
assert consent["consented_at"].tzinfo is not None
assert consent["ip_address"] == "198.51.100.25", consent
assert "password" not in response.json()["user"]
assert "consent_to_care" not in response.json()["user"]
assert (
    api.post(
        "/api/v1/auth/login", json={"email": VALID["email"], "password": VALID["password"]}
    ).status_code
    == 200
)

# The client cannot spoof an IP address via proxy headers unless specifically trusted.
spoofed = api.post(
    "/api/v1/auth/register/client",
    json={**VALID, "email": "other@example.test", "id_number": "9005140012352"},
    headers={"X-Real-IP": "203.0.113.5"},
)
assert spoofed.status_code == 200
second_id = spoofed.json()["user"]["id"]
assert state.client_registration_consents_db[second_id]["ip_address"] == "198.51.100.25"

# Explicitly configured trusted proxies may supply the original address.
with patch.dict(os.environ, {"REGISTRATION_TRUSTED_PROXY_CIDRS": "198.51.100.25/32"}):
    third = api.post(
        "/api/v1/auth/register/client",
        json={**VALID, "email": "third@example.test", "id_number": "9005140012360"},
        headers={"X-Real-IP": "203.0.113.5"},
    )
assert third.status_code == 200
third_id = third.json()["user"]["id"]
assert state.client_registration_consents_db[third_id]["ip_address"] == "203.0.113.5"

# Dietitian registration remains unchanged and does not require patient consent.
dietitian = api.post(
    "/api/v1/auth/register/dietitian",
    json={
        "first_name": "Ari",
        "last_name": "Example",
        "email": "dietitian@example.test",
        "license_number": "RD-TEST-13",
        "password": "testpassword123",
    },
)
assert dietitian.status_code == 200, dietitian.text
print(
    "PASS: mandatory consent, notice version, timestamp, peer IP, login and dietitian compatibility"
)
