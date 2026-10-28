"""Security milestone 02 tests: only in-memory stores, never external databases."""
import pytest
from fastapi.testclient import TestClient

import app
import config
import state
from security import hash_password

api = TestClient(app.app)


@pytest.fixture(autouse=True)
def isolated_staff(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    stores = (
        state.users_db, state.admins_db, state.admin_sessions_db,
        state.client_sessions_db, state.dietitian_sessions_db,
        state.staff_accounts_db, state.staff_sessions_db, state.branches_db,
        state.clients_db, state.appointments_db, state.goals_db,
    )
    for store in stores:
        store.clear()
    state.access_audit_events_db.clear()
    state.admins_db["admin-one"] = {
        "id": "admin-one", "type": "admin", "email": "admin@example.test",
        "full_name": "System Administrator", "password_hash": hash_password("local-admin-password")
    }
    state.admin_sessions_db["admin-token"] = "admin-one"
    state.branches_db["branch-1"] = {"branch_id": "branch-1", "name": "Main Branch"}
    state.users_db["client-1"] = {"id": "client-1", "type": "client", "email": "patient@example.test", "dietitian_id": "diet-1"}
    state.clients_db["client-1"] = {"allergies": [], "conditions": [], "progress": [], "metrics": []}
    yield
    for store in stores:
        store.clear()
    state.access_audit_events_db.clear()


def bearer(token):
    return {"Authorization": "Bearer " + token}


def new_staff(role="reception", branch_id="branch-1", email="reception@example.test"):
    return {"full_name": "Reception User", "email": email,
            "password": "local-staff-password-123", "role": role, "branch_id": branch_id}


def create_staff(payload=None):
    return api.post("/api/v1/admin/staff", headers=bearer("admin-token"), json=payload or new_staff())


def login_staff(email="reception@example.test"):
    return api.post("/api/v1/auth/login", json={"email": email, "password": "local-staff-password-123"})


def test_staff_creation_requires_system_admin():
    assert api.post("/api/v1/admin/staff", json=new_staff()).status_code == 401
    state.client_sessions_db["patient-token"] = "client-1"
    assert api.post("/api/v1/admin/staff", headers=bearer("patient-token"), json=new_staff()).status_code == 403
    result = create_staff()
    assert result.status_code == 201, result.text
    assert result.json()["role"] == "reception"
    assert result.json()["branch_id"] == "branch-1"
    assert "password_hash" not in result.json()
    assert "password" not in result.json()


def test_staff_login_and_self_profile_but_no_clinical_record_access():
    create_staff()
    response = login_staff()
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert response.json()["user"]["type"] == "reception"
    assert "password_hash" not in response.json()["user"]
    assert api.get("/api/v1/staff/me", headers=bearer(token)).status_code == 200
    assert api.get("/api/v1/clients/client-1/profile", headers=bearer(token)).status_code == 403
    assert api.get("/api/v1/admin/staff", headers=bearer(token)).status_code == 403
    assert api.get("/api/v1/admin/access-events", headers=bearer(token)).status_code == 403


@pytest.mark.parametrize("role", ["reception", "branch_manager", "compliance_officer", "executive", "content_manager"])
def test_all_new_roles_can_login_without_extra_permissions(role):
    payload = new_staff(role=role, branch_id="branch-1" if role in {"reception", "branch_manager"} else None)
    assert create_staff(payload).status_code == 201
    token = login_staff().json()["access_token"]
    assert api.get("/api/v1/staff/me", headers=bearer(token)).status_code == 200
    assert api.get("/api/v1/clients/client-1/profile", headers=bearer(token)).status_code == 403


def test_branch_required_and_unknown_branch_rejected():
    assert create_staff(new_staff(branch_id=None)).status_code == 422
    assert create_staff(new_staff(branch_id="missing")).status_code == 422
    assert create_staff(new_staff(role="branch_manager", branch_id=None)).status_code == 422
    assert create_staff(new_staff(role="executive", branch_id=None)).status_code == 201


def test_invalid_role_cannot_be_used_to_create_admin():
    assert create_staff(new_staff(role="admin")).status_code == 422
    assert create_staff(new_staff(role="dietitian")).status_code == 422


def test_staff_email_must_be_unique_across_existing_accounts():
    assert create_staff(new_staff(email="patient@example.test")).status_code == 409
    assert create_staff(new_staff(email="admin@example.test")).status_code == 409
    assert create_staff().status_code == 201
    assert create_staff().status_code == 409


def test_deactivate_staff_revokes_token_and_rejects_login():
    staff_id = create_staff().json()["staff_id"]
    token = login_staff().json()["access_token"]
    disabled = api.put(f"/api/v1/admin/staff/{staff_id}", json={
        "role": "reception", "branch_id": "branch-1", "is_active": False,
    }, headers=bearer("admin-token"))
    assert disabled.status_code == 200
    assert api.get("/api/v1/staff/me", headers=bearer(token)).status_code == 401
    assert login_staff().status_code == 401


def test_role_update_revokes_old_token():
    staff_id = create_staff().json()["staff_id"]
    token = login_staff().json()["access_token"]
    result = api.put(f"/api/v1/admin/staff/{staff_id}", json={
        "role": "compliance_officer", "branch_id": None, "is_active": True,
    }, headers=bearer("admin-token"))
    assert result.status_code == 200
    assert api.get("/api/v1/staff/me", headers=bearer(token)).status_code == 401
    new_token = login_staff().json()["access_token"]
    assert api.get("/api/v1/admin/access-events", headers=bearer(new_token)).status_code == 200
    assert api.get("/api/v1/admin/staff", headers=bearer(new_token)).status_code == 403


def test_audit_tracks_authorized_and_denied_access_without_secrets():
    api.get("/api/v1/clients/client-1/profile")
    api.get("/api/v1/clients/client-1/profile", headers=bearer("admin-token"))
    events = api.get("/api/v1/admin/access-events", headers=bearer("admin-token"))
    assert events.status_code == 200
    data = events.json()
    statuses = {item["status_code"] for item in data}
    assert statuses >= {200, 401}
    assert {item["actor_role"] for item in data} >= {"admin", "anonymous"}
    assert all("password" not in str(event) and "admin-token" not in str(event) for event in data)
    assert all(event["resource_path"] == "/api/v1/clients/client-1/profile" for event in data)


def test_compliance_officer_can_read_but_not_modify_audit():
    create_staff(new_staff(role="compliance_officer", branch_id=None))
    token = login_staff().json()["access_token"]
    assert api.get("/api/v1/admin/access-events", headers=bearer(token)).status_code == 200
    assert api.post("/api/v1/admin/staff", headers=bearer(token), json=new_staff()).status_code == 403
    assert api.get("/api/v1/admin/audit-logs", headers=bearer(token)).status_code == 401  # Legacy approval-only endpoint


def test_access_events_are_paginated_and_filterable():
    api.get("/api/v1/clients/client-1/profile")
    api.get("/api/v1/clients/client-1/profile", headers=bearer("admin-token"))
    resp = api.get("/api/v1/admin/access-events?limit=1&actor_role=anonymous", headers=bearer("admin-token"))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["actor_role"] == "anonymous"
    assert api.get("/api/v1/admin/access-events?limit=10000", headers=bearer("admin-token")).status_code == 422
