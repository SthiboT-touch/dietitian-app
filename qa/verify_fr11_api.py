"""Isolated FR-1.1 smoke test of the existing registration contract.

Run: python qa/verify_fr11_api.py
Does not connect to the real database or Oracle Cloud.
"""
import os
import sys
import types
from pathlib import Path

os.environ["APP_USE_IN_MEMORY_DB"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "back-end"))

# The dedicated in-memory registration test never calls database.cursor().
# Permit the test to run in lightweight environments without psycopg2.
try:
    import database  # noqa: F401
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


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    state.users_db.clear()
    state.admins_db.clear()
    state.client_sessions_db.clear()
    state.dietitian_sessions_db.clear()
    state.staff_accounts_db.clear()
    # The 3-step form must send the same payload the API already accepts.
    details = {
        "first_name": "Taylor", "last_name": "Example",
        "email": "taylor@example.test", "id_number": "9005140012345",
        "date_of_birth": "1990-05-14", "gender": "other",
        "phone": "082 123 4567",
        "consent_to_care": True, "privacy_notice_version": "2026-10-28-v1",
        "password": "testpassword123",
    }
    result = client.post("/api/v1/auth/register/client", json=details)
    check(result.status_code == 200, f"Client registration failed: {result.status_code}: {result.text}")
    check(result.json()["user"]["type"] == "client", "Wrong account type")
    check("password" not in result.json()["user"], "Registration leaked a password")
    login = client.post("/api/v1/auth/login", json={"email": details["email"], "password": details["password"]})
    check(login.status_code == 200, "Newly registered client could not log in")
    duplicate = client.post("/api/v1/auth/register/client", json=details)
    check(duplicate.status_code == 409, "Duplicate email registration was not rejected")
    print("PASS: existing client registration, sign-in and duplicate prevention in isolated API test")


if __name__ == "__main__":
    main()
