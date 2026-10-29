"""RBAC regression tests for client records, appointments, and goals.

Run with `python -m pytest -q back-end/tests/test_authorization.py` inside an
environment with requirements-dev.txt installed (such as the local API image).
These tests use in-memory data only, never production PostgreSQL.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app
import config
import state

api = TestClient(app.app)


@pytest.fixture(autouse=True)
def isolated_in_memory(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    for store in (
        state.users_db,
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.clients_db,
        state.client_documents_db,
        state.appointments_db,
        state.goals_db,
    ):
        store.clear()
    state.users_db.update(
        {
            "c1": {"id": "c1", "type": "client", "full_name": "Client One", "dietitian_id": "d1"},
            "c2": {"id": "c2", "type": "client", "full_name": "Client Two", "dietitian_id": "d2"},
        }
    )
    state.clients_db.update(
        {
            "c1": {"allergies": [], "conditions": [], "metrics": [], "progress": []},
            "c2": {"allergies": [], "conditions": [], "metrics": [], "progress": []},
        }
    )
    state.client_sessions_db.update({"client-1": "c1", "client-2": "c2"})
    state.dietitian_sessions_db.update({"dietitian-1": "d1", "dietitian-2": "d2"})
    state.admin_sessions_db["admin-1"] = "a1"
    yield
    for store in (
        state.users_db,
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.clients_db,
        state.client_documents_db,
        state.appointments_db,
        state.goals_db,
    ):
        store.clear()


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def booking(client_id="c1", dietitian_id="d1"):
    return {
        "client_id": client_id,
        "dietitian_id": dietitian_id,
        "appointment_date": (datetime.now() + timedelta(days=3)).isoformat(),
    }


def test_health_profile_requires_authentication_and_rejects_invalid_token():
    assert api.get("/api/v1/clients/c1/profile").status_code == 401
    assert api.get("/api/v1/clients/c1/profile", headers=headers("bad-token")).status_code == 401


def test_client_can_read_own_profile_but_not_other_records():
    assert api.get("/api/v1/clients/c1/profile", headers=headers("client-1")).status_code == 200
    assert api.get("/api/v1/clients/c2/profile", headers=headers("client-1")).status_code == 403
    assert (
        api.post(
            "/api/v1/clients/c2/allergies",
            json={"allergen": "Nuts", "severity": "severe"},
            headers=headers("client-1"),
        ).status_code
        == 403
    )
    assert (
        api.get("/api/v1/clients/c2/medical-documents", headers=headers("client-1")).status_code
        == 403
    )


def test_dietitian_can_only_access_assigned_patients():
    assert api.get("/api/v1/clients/c1/profile", headers=headers("dietitian-1")).status_code == 200
    assert api.get("/api/v1/clients/c2/profile", headers=headers("dietitian-1")).status_code == 403
    assert (
        api.get(
            "/api/v1/clients", params={"dietitian_id": "d2"}, headers=headers("dietitian-1")
        ).status_code
        == 403
    )
    allowed = api.get(
        "/api/v1/clients", params={"dietitian_id": "d1"}, headers=headers("dietitian-1")
    )
    assert allowed.status_code == 200
    assert [x["id"] for x in allowed.json()] == ["c1"]


def test_client_directory_does_not_leak_to_other_client():
    assert (
        api.get(
            "/api/v1/clients", params={"client_id": "c2"}, headers=headers("client-1")
        ).status_code
        == 403
    )
    assert (
        api.get(
            "/api/v1/clients", params={"dietitian_id": "d1"}, headers=headers("client-1")
        ).status_code
        == 403
    )
    result = api.get("/api/v1/clients", params={"client_id": "c1"}, headers=headers("client-1"))
    assert result.status_code == 200
    assert [user["id"] for user in result.json()] == ["c1"]


def test_admin_access_remains_compatible_with_existing_system_admin():
    assert api.get("/api/v1/clients/c2/profile", headers=headers("admin-1")).status_code == 200


def test_client_meal_and_lactation_routes_are_protected():
    assert api.post("/api/v1/clients/c1/lactation", json={"is_active": True}).status_code == 401
    result = api.post(
        "/api/v1/clients/c1/lactation", json={"is_active": True}, headers=headers("client-1")
    )
    assert result.status_code == 200
    assert (
        api.get("/api/v1/clients/c1/lactation/overview", headers=headers("client-2")).status_code
        == 403
    )
    assert api.get("/api/v1/clients/c1/meals").status_code == 401


def test_appointment_booking_requires_client_ownership():
    assert api.post("/api/v1/appointments", json=booking()).status_code == 401
    assert (
        api.post(
            "/api/v1/appointments", json=booking("c2"), headers=headers("client-1")
        ).status_code
        == 403
    )
    result = api.post("/api/v1/appointments", json=booking("c1", "d2"), headers=headers("client-1"))
    assert result.status_code == 200  # clients may book with a different dietitian
    assert result.json()["appointment"]["status"] == "PENDING"


def test_appointment_lists_are_scoped_by_identity():
    state.appointments_db["a1"] = {
        **booking("c1", "d1"),
        "appointment_id": "a1",
        "status": "PENDING",
    }
    state.appointments_db["a2"] = {
        **booking("c2", "d2"),
        "appointment_id": "a2",
        "status": "PENDING",
    }
    assert api.get("/api/v1/appointments").status_code == 401
    assert [
        r["appointment_id"]
        for r in api.get("/api/v1/appointments", headers=headers("client-1")).json()
    ] == ["a1"]
    assert [
        r["appointment_id"]
        for r in api.get("/api/v1/appointments", headers=headers("dietitian-1")).json()
    ] == ["a1"]
    assert (
        api.get(
            "/api/v1/appointments", params={"client_id": "c2"}, headers=headers("client-1")
        ).status_code
        == 403
    )
    assert (
        api.get(
            "/api/v1/appointments", params={"dietitian_id": "d2"}, headers=headers("dietitian-1")
        ).status_code
        == 403
    )
    assert len(api.get("/api/v1/appointments", headers=headers("admin-1")).json()) == 2


def test_appointment_approval_and_cancellation_enforce_participant_roles():
    created = api.post("/api/v1/appointments", json=booking(), headers=headers("client-1")).json()[
        "appointment"
    ]["appointment_id"]
    url = f"/api/v1/appointments/{created}"
    assert api.patch(url, json={"action": "APPROVED"}).status_code == 401
    assert (
        api.patch(url, json={"action": "APPROVED"}, headers=headers("client-1")).status_code == 403
    )
    assert (
        api.patch(url, json={"action": "APPROVED"}, headers=headers("dietitian-2")).status_code
        == 403
    )
    assert (
        api.patch(url, json={"action": "APPROVED"}, headers=headers("dietitian-1")).status_code
        == 200
    )
    assert (
        api.patch(url, json={"action": "CANCELLED"}, headers=headers("client-2")).status_code == 403
    )
    assert (
        api.patch(url, json={"action": "CANCELLED"}, headers=headers("client-1")).status_code == 200
    )


def test_goals_require_authenticated_owner_or_assigned_dietitian():
    payload = {"client_id": "c1", "target_metric": "Water", "target_value": "2"}
    assert api.get("/api/v1/goals", params={"client_id": "c1"}).status_code == 401
    assert api.post("/api/v1/goals", json=payload, headers=headers("client-2")).status_code == 403
    assert api.post("/api/v1/goals", json=payload, headers=headers("client-1")).status_code == 200
    assert (
        api.get(
            "/api/v1/goals", params={"client_id": "c1"}, headers=headers("dietitian-1")
        ).status_code
        == 200
    )
    assert (
        api.get(
            "/api/v1/goals", params={"client_id": "c1"}, headers=headers("dietitian-2")
        ).status_code
        == 403
    )


def test_database_assignment_check_rejects_an_unassigned_dietitian(monkeypatch):
    from security import authorize_client_access
    from fastapi import HTTPException

    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    with patch("database.cursor") as mocked:
        cursor = mocked.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"dietitian_id": "d2"}
        with pytest.raises(HTTPException) as error:
            authorize_client_access("c1", ("dietitian", "d1"))
        assert error.value.status_code == 403
        cursor.execute.assert_called_once_with(
            "SELECT dietitian_id FROM client WHERE client_id = %s", ("c1",)
        )


def test_every_client_record_route_has_the_authorization_dependency():
    """Make newly introduced health endpoints fail tests if left unprotected."""
    from fastapi.routing import APIRoute
    from routers.clients import router as clients_router
    from security import require_client_record_access

    routes = [
        route
        for route in clients_router.routes
        if isinstance(route, APIRoute) and "/api/v1/clients/{client_id}" in route.path
    ]
    assert routes, "Expected to discover clinical client routes"
    for route in routes:
        assert any(
            dependency.call is require_client_record_access
            for dependency in route.dependant.dependencies
        ), route.path


def test_medical_document_download_requires_valid_record_access():
    state.client_documents_db["doc-1"] = {
        "client_id": "c1",
        "document_id": "doc-1",
        "file_data": b"sample document",
        "content_type": "application/pdf",
        "file_name": "health-note.pdf",
    }
    url = "/api/v1/clients/c1/medical-documents/doc-1"
    assert api.get(url).status_code == 401
    assert api.get(url, headers=headers("client-2")).status_code == 403
    permitted = api.get(url, headers=headers("client-1"))
    assert permitted.status_code == 200
    assert permitted.content == b"sample document"
