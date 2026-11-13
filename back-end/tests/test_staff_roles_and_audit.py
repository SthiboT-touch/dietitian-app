"""Security milestone 02 tests: only in-memory stores, never external databases."""

from contextlib import contextmanager

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
        state.users_db,
        state.dietitian_documents_db,
        state.approval_log_db,
        state.admins_db,
        state.admin_sessions_db,
        state.client_sessions_db,
        state.dietitian_sessions_db,
        state.staff_accounts_db,
        state.staff_sessions_db,
        state.branches_db,
        state.clients_db,
        state.appointments_db,
        state.goals_db,
    )
    for store in stores:
        store.clear()
    state.access_audit_events_db.clear()
    state.admins_db["admin-one"] = {
        "id": "admin-one",
        "type": "admin",
        "email": "admin@example.test",
        "full_name": "System Administrator",
        "password_hash": hash_password("local-admin-password"),
    }
    state.admin_sessions_db["admin-token"] = "admin-one"
    state.branches_db["branch-1"] = {"branch_id": "branch-1", "name": "Main Branch"}
    state.users_db["client-1"] = {
        "id": "client-1",
        "type": "client",
        "email": "patient@example.test",
        "dietitian_id": "diet-1",
    }
    state.clients_db["client-1"] = {
        "allergies": [],
        "conditions": [],
        "progress": [],
        "metrics": [],
    }
    yield
    for store in stores:
        store.clear()
    state.access_audit_events_db.clear()


def bearer(token):
    return {"Authorization": "Bearer " + token}


def new_staff(role="reception", branch_id="branch-1", email="reception@example.test"):
    return {
        "full_name": "Reception User",
        "email": email,
        "password": "local-staff-password-123",
        "role": role,
        "branch_id": branch_id,
    }


def create_staff(payload=None):
    return api.post(
        "/api/v1/admin/staff", headers=bearer("admin-token"), json=payload or new_staff()
    )


def login_staff(email="reception@example.test"):
    return api.post(
        "/api/v1/auth/login", json={"email": email, "password": "local-staff-password-123"}
    )


def test_staff_creation_requires_system_admin():
    assert api.post("/api/v1/admin/staff", json=new_staff()).status_code == 401
    state.client_sessions_db["patient-token"] = "client-1"
    assert (
        api.post(
            "/api/v1/admin/staff", headers=bearer("patient-token"), json=new_staff()
        ).status_code
        == 403
    )
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


@pytest.mark.parametrize(
    "role", ["reception", "branch_manager", "compliance_officer", "executive", "content_manager"]
)
def test_all_new_roles_can_login_without_extra_permissions(role):
    payload = new_staff(
        role=role, branch_id="branch-1" if role in {"reception", "branch_manager"} else None
    )
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
    disabled = api.put(
        f"/api/v1/admin/staff/{staff_id}",
        json={
            "role": "reception",
            "branch_id": "branch-1",
            "is_active": False,
        },
        headers=bearer("admin-token"),
    )
    assert disabled.status_code == 200
    assert api.get("/api/v1/staff/me", headers=bearer(token)).status_code == 401
    assert login_staff().status_code == 401


def test_role_update_revokes_old_token():
    staff_id = create_staff().json()["staff_id"]
    token = login_staff().json()["access_token"]
    result = api.put(
        f"/api/v1/admin/staff/{staff_id}",
        json={
            "role": "compliance_officer",
            "branch_id": None,
            "is_active": True,
        },
        headers=bearer("admin-token"),
    )
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
    assert (
        api.post("/api/v1/admin/staff", headers=bearer(token), json=new_staff()).status_code == 403
    )
    assert (
        api.get("/api/v1/admin/audit-logs", headers=bearer(token)).status_code == 401
    )  # Legacy approval-only endpoint


def test_access_events_are_paginated_and_filterable():
    api.get("/api/v1/clients/client-1/profile")
    api.get("/api/v1/clients/client-1/profile", headers=bearer("admin-token"))
    resp = api.get(
        "/api/v1/admin/access-events?limit=1&actor_role=anonymous", headers=bearer("admin-token")
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["actor_role"] == "anonymous"
    assert (
        api.get(
            "/api/v1/admin/access-events?limit=10000", headers=bearer("admin-token")
        ).status_code
        == 422
    )


def test_branch_manager_overview_is_branch_scoped_and_restricted():
    manager = new_staff(role="branch_manager", email="manager@example.test")
    assert create_staff(manager).status_code == 201
    token = login_staff("manager@example.test").json()["access_token"]
    assert create_staff(new_staff(email="frontdesk@example.test")).status_code == 201
    state.branches_db["branch-2"] = {"branch_id": "branch-2", "name": "Second Branch"}
    assert create_staff(new_staff(email="other@example.test", branch_id="branch-2")).status_code == 201
    result = api.get("/api/v1/branch-manager/overview", headers=bearer(token))
    assert result.status_code == 200, result.text
    assert result.json() == {
        "branch_id": "branch-1", "branch_name": "Main Branch",
        "active_staff": 2, "reception_staff": 1, "branch_managers": 1,
        "dietitians": 0,
    }
    assert api.get("/api/v1/branch-manager/overview").status_code == 401
    assert api.get("/api/v1/branch-manager/overview", headers=bearer("admin-token")).status_code == 403
    assert api.get("/api/v1/admin/staff", headers=bearer(token)).status_code == 403


def test_branch_manager_can_inspect_only_own_branch_dietitians():
    assert create_staff(new_staff(role="branch_manager", email="manager@example.test")).status_code == 201
    token = login_staff("manager@example.test").json()["access_token"]
    state.branches_db["branch-2"] = {"branch_id": "branch-2", "name": "Other Branch"}
    state.users_db.update(
        {
            "diet-1": {
                "id": "diet-1", "type": "dietitian", "full_name": "Branch Dietitian",
                "first_name": "Branch", "last_name": "Dietitian", "email": "branch@example.test",
                "license_number": "DT0012345", "status": "PENDING", "branch_id": "branch-1",
            },
            "diet-2": {
                "id": "diet-2", "type": "dietitian", "full_name": "Other Dietitian",
                "first_name": "Other", "last_name": "Dietitian", "email": "other@example.test",
                "license_number": "DT0012346", "status": "PENDING", "branch_id": "branch-2",
            },
        }
    )
    state.dietitian_documents_db.update(
        {
            "branch-card": {
                "document_id": "branch-card", "dietitian_id": "diet-1",
                "file_name": "card.pdf", "content_type": "application/pdf",
                "file_data": b"%PDF-1.4 branch",
            },
            "other-card": {
                "document_id": "other-card", "dietitian_id": "diet-2",
                "file_name": "other.pdf", "content_type": "application/pdf",
                "file_data": b"%PDF-1.4 other",
            },
        }
    )

    headers = bearer(token)
    listed = api.get("/api/v1/admin/dietitians", headers=headers)
    assert listed.status_code == 200
    assert [item["dietitian_id"] for item in listed.json()] == ["diet-1"]
    assert api.get("/api/v1/admin/dietitians/diet-1", headers=headers).status_code == 200
    assert api.get("/api/v1/admin/dietitians/diet-2", headers=headers).status_code == 404
    assert api.get(
        "/api/v1/admin/dietitian-documents/branch-card", headers=headers
    ).status_code == 200
    assert api.get(
        "/api/v1/admin/dietitian-documents/other-card", headers=headers
    ).status_code == 404
    pending = api.get("/api/v1/admin/approvals/pending", headers=headers)
    assert pending.status_code == 200
    assert [item["dietitian_id"] for item in pending.json()] == ["diet-1"]
    assert api.get("/api/v1/admin/branches", headers=headers).status_code == 401
    assert api.get("/api/v1/branch-manager/overview", headers=headers).json()["dietitians"] == 1

    for decision in ("APPROVED", "REJECTED"):
        blocked = api.post("/api/v1/admin/approvals", headers=headers, json={
            "dietitian_id": "diet-2", "status": decision, "notes": "Reviewed",
        })
        assert blocked.status_code == 404
    assert state.users_db["diet-2"]["status"] == "PENDING"
    assert not state.approval_log_db
    # Existing approval safeguards apply to managers too.
    assert api.post("/api/v1/admin/approvals", headers=headers, json={
        "dietitian_id": "diet-1", "status": "REJECTED",
    }).status_code == 422
    assert api.post("/api/v1/admin/approvals", headers=headers, json={
        "dietitian_id": "diet-1", "status": "APPROVED",
    }).status_code == 409
    state.branches_db["branch-1"]["address"] = "123 Main Street"
    for decision in ("APPROVED", "REJECTED"):
        result = api.post("/api/v1/admin/approvals", headers=headers, json={
            "dietitian_id": "diet-1", "status": decision, "notes": "Reviewed evidence",
        })
        assert result.status_code == 200, result.text
        assert state.users_db["diet-1"]["status"] == decision
    assert state.approval_log_db[-1]["staff_id"]
    assert state.approval_log_db[-1]["admin_id"] is None


def test_branch_manager_can_suspend_and_restore_only_own_approved_dietitians():
    assert create_staff(new_staff(role="branch_manager", email="manager@example.test")).status_code == 201
    token = login_staff("manager@example.test").json()["access_token"]
    state.branches_db["branch-2"] = {"branch_id": "branch-2", "name": "Other Branch"}
    state.users_db.update(
        {
            "diet-1": {
                "id": "diet-1", "type": "dietitian", "full_name": "Branch Dietitian",
                "email": "branch@example.test", "password_hash": hash_password("dietitian-password"),
                "status": "APPROVED", "branch_id": "branch-1", "email_verified": True,
            },
            "diet-2": {
                "id": "diet-2", "type": "dietitian", "full_name": "Other Dietitian",
                "email": "other@example.test", "password_hash": hash_password("dietitian-password"),
                "status": "APPROVED", "branch_id": "branch-2", "email_verified": True,
            },
        }
    )
    state.dietitian_sessions_db["active-dietitian-session"] = "diet-1"
    headers = bearer(token)

    url = "/api/v1/admin/dietitians/diet-1/status"
    assert api.patch(url, headers=headers, json={"status": "SUSPENDED"}).status_code == 422
    assert api.patch(
        "/api/v1/admin/dietitians/diet-2/status",
        headers=headers,
        json={"status": "SUSPENDED", "notes": "Outside branch"},
    ).status_code == 404

    suspended = api.patch(
        url, headers=headers,
        json={"status": "SUSPENDED", "notes": "No longer practising at this branch"},
    )
    assert suspended.status_code == 200, suspended.text
    assert state.users_db["diet-1"]["status"] == "SUSPENDED"
    assert "active-dietitian-session" not in state.dietitian_sessions_db
    assert api.post(
        "/api/v1/auth/login",
        json={"email": "branch@example.test", "password": "dietitian-password"},
    ).status_code == 401

    restored = api.patch(url, headers=headers, json={"status": "APPROVED"})
    assert restored.status_code == 200, restored.text
    assert state.users_db["diet-1"]["status"] == "APPROVED"
    assert api.post(
        "/api/v1/auth/login",
        json={"email": "branch@example.test", "password": "dietitian-password"},
    ).status_code == 200
    assert api.patch(url, headers=headers, json={"status": "SUSPENDED", "notes": "Second attempt"}).status_code == 200
    assert state.approval_log_db[-2]["staff_id"]
    assert state.approval_log_db[-2]["action"] == "APPROVED"
    assert state.approval_log_db[-1]["action"] == "SUSPENDED"


@pytest.mark.parametrize("same_branch", [True, False])
def test_postgres_manager_review_checks_branch_before_writing(monkeypatch, same_branch):
    from routers import auth_admin
    from schemas import AdminApproval
    from fastapi import HTTPException

    statements = []

    class Cursor:
        def execute(self, query, params):
            statements.append((query, params))

        def fetchone(self):
            return {"dietitian_id": "diet-1"} if same_branch else None

    @contextmanager
    def cursor():
        yield Cursor()

    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(auth_admin, "branch_id_for_manager", lambda _: "branch-1")
    monkeypatch.setattr(auth_admin.database, "cursor", cursor)
    data = AdminApproval(dietitian_id="diet-1", status="REJECTED", notes="Evidence missing")
    if same_branch:
        auth_admin.review_dietitian(data, ("branch_manager", "manager-1"))
        assert statements[-1][1] == (None, "manager-1", "diet-1", "REJECTED", "Evidence missing")
    else:
        with pytest.raises(HTTPException) as error:
            auth_admin.review_dietitian(data, ("branch_manager", "manager-1"))
        assert error.value.status_code == 404
        assert len(statements) == 1
    assert "AND branch_id = %s FOR UPDATE" in statements[0][0]
    assert statements[0][1] == ("diet-1", "branch-1")


def test_postgres_branch_manager_dietitian_query_is_branch_scoped(monkeypatch):
    from routers import auth_admin

    statements = []

    class Cursor:
        def execute(self, query, params):
            statements.append((query, params))

        def fetchone(self):
            return {"branch_id": "branch-1"}

        def fetchall(self):
            return []

    @contextmanager
    def cursor():
        yield Cursor()

    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    monkeypatch.setattr(auth_admin.database, "cursor", cursor)

    assert auth_admin.list_admin_dietitians(("branch_manager", "manager-1")) == []
    assert "WHERE d.branch_id = %s" in statements[1][0]
    assert statements[1][1] == ("branch-1",)
