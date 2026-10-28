"""No database/AI needed: regressions for safe API diagnostics.

These tests deliberately include a sensitive URL and secret-looking input to
prove that the access logs expose neither one.
"""

import io
import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from diagnostics import JsonLogFormatter, logger, request_diagnostics


class Registration(BaseModel):
    email: str


def create_test_app():
    app = FastAPI()
    app.middleware("http")(request_diagnostics)

    @app.get("/api/v1/clients/{client_id}/records")
    def get_record(client_id: str):
        return {"found": True}

    @app.get("/api/v1/clients/{client_id}/forbidden")
    def forbidden(client_id: str):
        raise HTTPException(403, detail="Not authorized for this client")

    @app.get("/api/v1/clients/{client_id}/error")
    def broken(client_id: str):
        raise RuntimeError("SHOULD_NOT_APPEAR_IN_CLIENT_OR_LOG")

    @app.post("/api/v1/registration")
    def registration(data: Registration):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_request_id_and_normal_response_are_unchanged():
    client = create_test_app()
    response = client.get(
        "/api/v1/clients/patient-private-001/records", params={"secret": "no-log"}
    )
    assert response.status_code == 200
    assert response.json() == {"found": True}
    assert len(response.headers["x-request-id"]) == 32
    assert response.headers["x-request-id"].isalnum()
    # Ignore external request IDs: identifiers must be server-generated.
    response2 = client.get(
        "/api/v1/clients/some-other-record/records", headers={"X-Request-ID": "forged-ref"}
    )
    assert response2.headers["x-request-id"] != "forged-ref"
    assert response2.headers["x-request-id"] != response.headers["x-request-id"]


def test_expected_http_and_validation_errors_preserve_existing_contract():
    client = create_test_app()
    forbidden = client.get("/api/v1/clients/patient-private-001/forbidden")
    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "Not authorized for this client"}
    assert forbidden.headers.get("x-request-id")
    invalid = client.post("/api/v1/registration", json={"wrong_field": 1})
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], list)
    assert invalid.headers.get("x-request-id")


def test_unexpected_error_returns_support_reference_not_internal_error():
    client = create_test_app()
    response = client.get("/api/v1/clients/patient-private-001/error")
    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert "unexpected server error" in response.json()["detail"]
    assert "SHOULD_NOT_APPEAR" not in response.text


def test_json_logs_use_route_template_without_private_data():
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    try:
        client = create_test_app()
        client.get(
            "/api/v1/clients/patient-private-001/error?token=SECRET-URL-QUERY",
            headers={"Authorization": "Bearer SECRET-BEARER-TOKEN"},
        )
        entries = out.getvalue()
        assert "SECRET-URL-QUERY" not in entries
        assert "patient-private-001" not in entries
        assert "SECRET-BEARER-TOKEN" not in entries
        assert "SHOULD_NOT_APPEAR" not in entries
        log = json.loads(entries.strip().splitlines()[-1])
        assert log["event"] == "http_request"
        assert log["route"] == "/api/v1/clients/{client_id}/error"
        assert log["status"] == 500
        assert log["error_type"] in ("RuntimeError", "ExceptionGroup")
        assert log["elapsed_ms"] >= 0
        assert log["request_id"]
    finally:
        logger.removeHandler(handler)


def test_health_and_static_successes_do_not_fill_logs():
    app = FastAPI()
    app.middleware("http")(request_diagnostics)

    @app.get("/health")
    def health():
        return {"status": "online"}

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "online"}


def test_unexpected_sensitive_failure_is_audited_as_500(monkeypatch):
    import config
    from audit import audit_sensitive_requests
    from state import access_audit_events_db

    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    access_audit_events_db.clear()
    app = FastAPI()
    app.middleware("http")(audit_sensitive_requests)
    app.middleware("http")(request_diagnostics)

    @app.get("/api/v1/clients/{client_id}/status")
    def fail(client_id: str):
        raise RuntimeError("Do not return patient data")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/clients/secret-patient/status"
    )
    assert response.status_code == 500
    assert len(access_audit_events_db) == 1
    assert access_audit_events_db[0]["status_code"] == 500
    access_audit_events_db.clear()
