"""FR-1.2 API verification (in-memory, no real PostgreSQL or Ollama).

Run from project root: python qa/verify_fr12_api.py
"""
import os
import sys
import types
from pathlib import Path

os.environ["APP_USE_IN_MEMORY_DB"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back-end"))
try:
    import database  # noqa
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
client = TestClient(app)

VALID = {
    "first_name": "Taylor", "last_name": "Example",
    "email": " Taylor@Example.Test ",
    "id_number": "9005140012345",
    "phone": "082 123 4567",
        "consent_to_care": True, "privacy_notice_version": "2026-10-28-v1",
    "date_of_birth": "1990-05-14", "gender": "other",
    "password": "testpassword123",
}


def must_reject(changes, field):
    data = {**VALID, **changes}
    response = client.post("/api/v1/auth/register/client", json=data)
    assert response.status_code == 422, (field, response.status_code, response.text)
    assert response.json().get("detail"), (field, response.json())


def main():
    state.users_db.clear()
    state.admins_db.clear()
    state.client_sessions_db.clear()
    must_reject({"email": "not-an-email"}, "email")
    must_reject({"email": "invalid@domain"}, "email")
    must_reject({"id_number": "1234"}, "id_number")
    must_reject({"id_number": "9005140012346"}, "id_number")
    must_reject({"date_of_birth": "2000-05-14"}, "id_number")
    must_reject({"date_of_birth": "2090-05-14"}, "id_number")
    must_reject({"phone": "123"}, "phone")
    must_reject({"phone": "002 123 4567"}, "phone")
    must_reject({"phone": "082 123 45ab"}, "phone")
    must_reject({"phone": None}, "phone")
    must_reject({"phone": ""}, "phone")
    result = client.post("/api/v1/auth/register/client", json=VALID)
    assert result.status_code == 200, result.text
    user = result.json()["user"]
    assert user["email"] == "taylor@example.test", user
    assert user["phone"] == "+27821234567", user
    assert "password" not in user
    assert client.post("/api/v1/auth/login", json={"email": "taylor@example.test", "password": VALID["password"]}).status_code == 200
    duplicate = client.post("/api/v1/auth/register/client", json={**VALID, "phone": "+27 82 123 4567"})
    assert duplicate.status_code == 409, duplicate.text
    dietitian = client.post("/api/v1/auth/register/dietitian", json={
        "first_name": "Alex", "last_name": "Example", "email": "alex@example.test",
        "license_number": "RD-TEST-12", "password": "testpassword123",
    })
    assert dietitian.status_code == 200, dietitian.text
    bad_dietitian = client.post("/api/v1/auth/register/dietitian", json={
        "first_name": "Alex", "last_name": "Example", "email": "bad-email",
        "license_number": "RD-TEST-12", "password": "testpassword123",
    })
    assert bad_dietitian.status_code == 422
    print("PASS: FR-1.2 rejects invalid fields, stores normalized email/phone, retains login and dietitian signup")


if __name__ == "__main__":
    main()
