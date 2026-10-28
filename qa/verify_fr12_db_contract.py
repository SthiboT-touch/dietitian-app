"""Mock PostgreSQL call contract for current FR-1.2 / FR-1.9 registration.

A real local PostgreSQL migration+insert must still be tested in Docker.
"""

import os, sys, types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

os.environ["APP_USE_IN_MEMORY_DB"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "back-end"))
try:
    import database  # noqa: F401 - check whether the real database module can load
except ImportError:
    sys.modules["database"] = types.ModuleType("database")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import config
from routers.auth_admin import router

calls = []


class Cursor:
    def execute(self, query, params=None):
        calls.append((query, params))

    def fetchone(self):
        return None


@contextmanager
def fake_cursor():
    yield Cursor()


app = FastAPI()
app.include_router(router)
api = TestClient(app)
with patch("routers.auth_admin.email_is_registered", return_value=False), patch(
    "routers.auth_admin.database.cursor", side_effect=fake_cursor, create=True
):
    config.DATABASE_ENABLED = True
    result = api.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Taylor",
            "last_name": "Example",
            "email": "TAYLOR@EXAMPLE.TEST",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "id_number": "9005140012345",
            "date_of_birth": "1990-05-14",
            "gender": "other",
            "password": "testing123456",
        },
    )
assert result.status_code == 200, result.text
assert any("SELECT 1 FROM client WHERE id_number" in statement for statement, _ in calls), calls
inserts = [(s, p) for s, p in calls if s.startswith("INSERT INTO")]
assert len(inserts) == 3, inserts
statement, params = next((s, p) for s, p in inserts if s.startswith("INSERT INTO client ("))
assert "phone" in statement and params[-1] == "+27821234567" and params[3] == "taylor@example.test"
assert "password" not in result.json()["user"]
assert (
    "ALTER TABLE client ADD COLUMN IF NOT EXISTS phone"
    in (ROOT / "back-end/migrations/009_client_registration_phone.sql").read_text()
)
print("PASS: normalized phone & uniqueness check and queue insert retain schema compatibility")
