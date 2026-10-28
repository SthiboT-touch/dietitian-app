"""Regression tests for POST /api/v1/clients/{client_id}/lactation.

A second, duplicate ``LactationLog`` schema (field ``is_lactating``) used to
shadow the real one (field ``is_active``). The front-end and the router both use
``is_active``, so every "Save lactation details" request was rejected with 422.
"""
import pytest
from fastapi.testclient import TestClient

import app
import config
import state
from schemas import LactationLog

client = TestClient(app.app)


@pytest.fixture(autouse=True)
def in_memory_mode(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    state.clients_db.clear()
    state.client_sessions_db["lactation-client-token"] = "C1"
    yield
    state.clients_db.clear()
    state.client_sessions_db.pop("lactation-client-token", None)


def test_lactation_schema_uses_is_active_field():
    assert set(LactationLog.model_fields) == {"is_active", "notes"}


def test_lactation_active_payload_from_frontend_is_accepted():
    response = client.post(
        "/api/v1/clients/C1/lactation",
        json={"is_active": True, "notes": "Exclusively breastfeeding"},
        headers={"Authorization": "Bearer lactation-client-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"is_active": True, "notes": "Exclusively breastfeeding"}


def test_lactation_inactive_payload_is_accepted_without_notes():
    response = client.post("/api/v1/clients/C1/lactation", json={"is_active": False}, headers={"Authorization": "Bearer lactation-client-token"})

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False


def test_lactation_payload_missing_is_active_is_rejected():
    response = client.post("/api/v1/clients/C1/lactation", json={"notes": "no status given"}, headers={"Authorization": "Bearer lactation-client-token"})

    assert response.status_code == 422
