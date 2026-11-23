import database
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path
import pytest
import uuid


MIGRATION_PATH = Path(__file__).parents[1] / "migrations" / "migrate_postgres_to_sqlite.py"
SPEC = importlib.util.spec_from_file_location("migrate_postgres_to_sqlite", MIGRATION_PATH)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def test_sqlite_cursor_returns_mapping_rows_and_commits(tmp_path, monkeypatch):
    database_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(database_file))

    with database.cursor() as cursor:
        cursor.execute("CREATE TABLE sample (item_id INTEGER PRIMARY KEY, label TEXT NOT NULL)")
        cursor.execute("INSERT INTO sample (label) VALUES (%s)", ("saved",))

    with database.cursor() as cursor:
        cursor.execute("SELECT item_id, label FROM sample")
        row = cursor.fetchone()

    assert dict(row) == {"item_id": 1, "label": "saved"}
    assert row.get("label") == "saved"

    with database.cursor() as cursor:
        cursor.execute("SELECT item_id, label FROM sample")
        rows = cursor.fetchall()

    assert rows[0].get("item_id") == 1

    with database.cursor() as cursor:
        cursor.execute("SELECT item_id, label FROM sample")
        assert cursor.fetchmany()[0].get("label") == "saved"


def test_sqlite_connections_use_wal_and_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))

    connection = database.open_connection()
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 8000
    finally:
        connection.close()


def test_sqlite_schema_inspection_supports_tables_and_columns(tmp_path, monkeypatch):
    import config
    from routers.auth_admin import _find_password_reset_account

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)

    with database.cursor() as cursor:
        assert database.table_exists(cursor, "nutrition_goal")
        assert database.column_exists(cursor, "nutrition_goal", "status")
        assert not database.column_exists(cursor, "nutrition_goal", "missing_column")
        assert not database.table_exists(cursor, "missing_table")

    assert _find_password_reset_account("missing@example.test") is None


def test_sqlite_appointment_queries_support_cutover(tmp_path, monkeypatch):
    import config
    from consultations import completed_consultation
    from routers.appointments import _has_overlapping_appointment, get_appointment_calendar
    from routers.onboarding import require_checkin_appointment
    from state import dietitian_sessions_db

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)

    future_visit = (datetime.now() + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    past_visit = future_visit - timedelta(days=3)
    with database.cursor() as cursor:
        cursor.execute(
            "INSERT INTO business (business_id, name, registration_number) "
            "VALUES (%s, %s, %s)",
            ("business-1", "Practice", "REG-1"),
        )
        cursor.execute(
            "INSERT INTO branch (branch_id, business_id, name) VALUES (%s, %s, %s)",
            ("branch-1", "business-1", "Main"),
        )
        cursor.execute(
            "INSERT INTO dietitian "
            "(dietitian_id, branch_id, first_name, last_name, email, password, registration_number) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            ("dietitian-1", "branch-1", "Dee", "Tician", "diet@example.test", "hash", "LIC-1"),
        )
        cursor.execute(
            "INSERT INTO client "
            "(client_id, name, email, password, id_number, date_of_birth, gender) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            ("client-1", "Patient", "patient@example.test", "hash", "ID-1", "1990-01-01", "other"),
        )
        cursor.execute(
            "INSERT INTO appointment "
            "(appointment_id, client_id, dietitian_id, date_time, duration, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("appointment-future", "client-1", "dietitian-1", future_visit, 50, "CONFIRMED"),
        )
        cursor.execute(
            "INSERT INTO appointment "
            "(appointment_id, client_id, dietitian_id, date_time, duration, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            ("appointment-past", "client-1", "dietitian-1", past_visit, 50, "COMPLETED"),
        )

        assert _has_overlapping_appointment(
            cursor, "dietitian-1", future_visit
        )
        assert not _has_overlapping_appointment(
            cursor, "dietitian-1", future_visit + timedelta(hours=2)
        )
        assert require_checkin_appointment(
            "client-1", cursor, appointment_id="appointment-future"
        ) == "appointment-future"

    assert completed_consultation("client-1", "dietitian-1") == "appointment-past"

    token = "sqlite-calendar-token"
    dietitian_sessions_db[token] = "dietitian-1"
    try:
        calendar = get_appointment_calendar(f"Bearer {token}")
    finally:
        dietitian_sessions_db.pop(token, None)

    assert {row["appointment_id"] for row in calendar} == {
        "appointment-future",
        "appointment-past",
    }
    assert all(row["checked_in_at"] is None for row in calendar)


def test_sqlite_initializes_current_feature_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))

    with database.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        columns = {
            table: {
                row["name"]
                for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for table in (
                "appointment",
                "nutrition_goal",
                "client_checkin_credential",
                "client_checkin_event",
                "approval_log",
            )
        }
        cursor.execute("INSERT INTO diet_type (name) VALUES (%s)", ("TEST_DIET",))
        cursor.execute("SELECT diet_type_id FROM diet_type WHERE name=%s", ("TEST_DIET",))
        generated_id = cursor.fetchone()["diet_type_id"]

    assert {"client", "appointment", "staff_account", "meal_plan_review",
            "registration_welcome_outbox", "client_checkin_credential"} <= tables
    assert {
        "appointment_type",
        "meeting_link",
        "branch_id",
        "consultation_type",
    } <= columns["appointment"]
    assert "appointment_id" in columns["nutrition_goal"]
    assert "appointment_id" in columns["client_checkin_credential"]
    assert {"actor_id", "actor_role", "appointment_id"} <= columns["client_checkin_event"]
    assert "staff_id" in columns["approval_log"]
    assert len(generated_id) == 36


def test_sqlite_initializes_cms_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))

    with database.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}

    assert {
        "ehr_note",
        "nutrition_plan_version",
        "client_attachment",
        "client_access_audit",
    } <= tables


def test_sqlite_patient_registration_succeeds(tmp_path, monkeypatch):
    import config
    import time
    import state
    from fastapi.testclient import TestClient
    from app import app

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    payload = {
        "first_name": "Jordan",
        "last_name": "Lee",
        "email": "jordan@example.test",
        "id_number": "9005140012345",
        "phone": "082 123 4567",
        "date_of_birth": "1990-05-14",
        "gender": "female",
        "password": "nutrition-safe-pass",
        "consent_to_care": True,
        "privacy_notice_version": "2026-10-28-v1",
    }
    monkeypatch.setitem(
        state.verified_email_db,
        payload["email"].casefold(),
        {"stytch_user_id": None, "expires_at": time.time() + 600},
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/register/client", json=payload)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": payload["password"]},
        )
        unknown_login = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.test", "password": payload["password"]},
        )

    assert response.status_code == 200
    assert response.json()["user"]["type"] == "client"
    assert response.json()["welcome_email"] == "queued"
    assert login.status_code == 200
    assert login.json()["user"]["type"] == "client"
    assert unknown_login.status_code == 401


def test_sqlite_admin_setup_and_login_work(tmp_path, monkeypatch):
    import config
    from fastapi import Request
    from routers.auth_admin import login, setup_first_admin
    from schemas import AdminSetup, LoginRequest
    from state import admin_sessions_db

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    payload = {
        "first_name": "Avery",
        "last_name": "Admin",
        "email": "avery@example.test",
        "password": "nutrition-safe-pass",
    }
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/setup",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8001),
            "scheme": "http",
            "query_string": b"",
        }
    )

    setup = setup_first_admin(AdminSetup(**payload), request)
    result = login(LoginRequest(email=payload["email"], password=payload["password"]))

    assert setup["user"]["type"] == "admin"
    assert result["user"]["type"] == "admin"
    admin_sessions_db.pop(result["access_token"], None)


def test_sqlite_admin_account_search_works(tmp_path, monkeypatch):
    import config
    from routers.support import find_accounts

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    with database.cursor() as cursor:
        cursor.execute(
            "INSERT INTO client "
            "(client_id, name, email, password, id_number, date_of_birth, gender) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                "client-1",
                "Jordan Lee",
                "jordan@example.test",
                "password-hash",
                "9005140012345",
                "1990-05-14",
                "female",
            ),
        )

    assert find_accounts("jordan", actor=("admin", "admin-1")) == [
        {
            "id": "client-1",
            "full_name": "Jordan Lee",
            "email": "jordan@example.test",
            "account_type": "client",
        }
    ]


def test_sqlite_guest_ticket_rate_limit(tmp_path, monkeypatch):
    import config
    from fastapi import HTTPException
    from routers.support import GuestTicket, guest_ticket

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    ticket_data = GuestTicket(
        contact_email="guest@example.test",
        subject="Support request",
        body="I need help.",
    )

    for _ in range(5):
        guest_ticket(ticket_data)

    with pytest.raises(HTTPException) as error:
        guest_ticket(ticket_data)

    assert error.value.status_code == 429


def test_meal_planning_recipe_query_works_with_sqlite(tmp_path, monkeypatch):
    import config
    from routers.meal_planning import _load_candidate_recipes

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    with database.cursor() as cursor:
        cursor.execute(
            "INSERT INTO recipe (recipe_id, name, instructions) VALUES (%s, %s, %s)",
            ("recipe-1", "Oat bowl", '{"ingredients":["oats"],"instructions":"Mix"}'),
        )

    assert _load_candidate_recipes(["recipe-1"]) == [
        {"recipe_id": "recipe-1", "title": "Oat bowl", "ingredients": ["oats"], "instructions": "Mix"}
    ]


def test_sqlite_appointment_decision_compares_migrated_timestamp(tmp_path, monkeypatch):
    import config
    from routers.appointments import decide_appointment
    from schemas import AppointmentDecision
    from state import dietitian_sessions_db

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    dietitian_sessions_db["sqlite-dietitian-token"] = "diet-1"
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    try:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO business (business_id, name, registration_number) VALUES (%s, %s, %s)",
                ("business-1", "Practice", "REG-1"),
            )
            cursor.execute(
                "INSERT INTO branch (branch_id, business_id, name) VALUES (%s, %s, %s)",
                ("branch-1", "business-1", "Main"),
            )
            cursor.execute(
                "INSERT INTO dietitian (dietitian_id, branch_id, first_name, last_name, email, password, registration_number) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("diet-1", "branch-1", "Dee", "Tician", "diet@example.test", "hash", "LICENSE-1"),
            )
            cursor.execute(
                "INSERT INTO client (client_id, name, email, password, id_number, date_of_birth, gender) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("client-1", "Patient", "patient@example.test", "hash", "ID-1", "1990-01-01", "other"),
            )
            cursor.execute(
                "INSERT INTO appointment (appointment_id, client_id, dietitian_id, date_time, duration) "
                "VALUES (%s, %s, %s, %s, %s)",
                ("appointment-1", "client-1", "diet-1", past_time, 30),
            )

        with pytest.raises(Exception) as error:
            decide_appointment(
                "appointment-1",
                AppointmentDecision(action="CANCELLED"),
                authorization="Bearer sqlite-dietitian-token",
            )
        assert getattr(error.value, "status_code", None) == 409
    finally:
        dietitian_sessions_db.pop("sqlite-dietitian-token", None)


def test_sqlite_cursor_rolls_back_on_error(tmp_path, monkeypatch):
    database_file = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(database_file))

    with database.cursor() as cursor:
        cursor.execute("CREATE TABLE sample (label TEXT NOT NULL)")

    try:
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO sample (label) VALUES (%s)", ("not saved",))
            raise ValueError("force rollback")
    except ValueError:
        pass

    with database.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM sample")
        assert cursor.fetchone()["count"] == 0


def test_sqlite_cursor_translates_postgresql_query_fragments(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./app.db")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))

    with database.cursor() as cursor:
        cursor.execute("SELECT %s AS value, NOW() AS created_at FOR UPDATE", (7,))
        row = cursor.fetchone()

    assert row["value"] == 7
    assert row["created_at"]


def test_postgres_values_convert_to_sqlite_values():
    assert migration.sqlite_value(date(2026, 10, 28)) == "2026-10-28"
    assert migration.sqlite_value(datetime(2026, 10, 28, tzinfo=timezone.utc)) == "2026-10-28 00:00:00+00:00"
    assert migration.sqlite_value(Decimal("12.50")) == "12.50"
    assert migration.sqlite_value(uuid.UUID("d9f40ac5-3676-4dca-b5f1-d4c58cd09e8a")) == "d9f40ac5-3676-4dca-b5f1-d4c58cd09e8a"


def test_migration_copies_rows_by_column_name(tmp_path):
    import sqlite3

    class SourceCursor:
        description = [type("Column", (), {"name": name}) for name in ("label", "item_id")]

        def execute(self, query):
            assert query == 'SELECT * FROM public."sample"'

        def fetchmany(self, size):
            self.rows = getattr(self, "rows", [("kept", 9)])
            rows, self.rows = self.rows[:size], self.rows[size:]
            return rows

    destination = sqlite3.connect(tmp_path / "copy.db")
    destination.execute("CREATE TABLE sample (item_id INTEGER PRIMARY KEY, label TEXT NOT NULL)")

    assert migration.copy_table(SourceCursor(), destination, "sample") == 1
    assert destination.execute("SELECT item_id, label FROM sample").fetchone() == (9, "kept")
    destination.close()