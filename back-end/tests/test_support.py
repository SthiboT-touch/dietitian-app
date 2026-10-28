"""Ticket privacy, administrator access and credential-recovery regressions."""

import pytest
from fastapi.testclient import TestClient

import app
import config
import state
from security import hash_password, verify_password

api = TestClient(app.app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    monkeypatch.setattr(config, "STYTCH_ENABLED", False)
    stores = [
        state.users_db,
        state.admins_db,
        state.staff_accounts_db,
        state.admin_sessions_db,
        state.client_sessions_db,
        state.dietitian_sessions_db,
        state.staff_sessions_db,
        state.support_tickets_db,
        state.support_messages_db,
    ]
    for store in stores:
        store.clear()
    state.admins_db["admin"] = {
        "id": "admin",
        "type": "admin",
        "email": "admin@example.test",
        "full_name": "Administrator",
    }
    state.admin_sessions_db["admin-token"] = "admin"
    for name in ("alice", "bob"):
        state.users_db[name] = {
            "id": name,
            "type": "client",
            "email": f"{name}@example.test",
            "full_name": name,
            "password_hash": hash_password("old-password-123"),
        }
        state.client_sessions_db[f"{name}-token"] = name
    yield
    for store in stores:
        store.clear()


def ticket():
    response = api.post(
        "/api/v1/support/tickets",
        headers=auth("alice-token"),
        json={"subject": "Cannot sign in", "body": "Please help with my account."},
    )
    assert response.status_code == 201
    return response.json()["ticket_id"]


def test_ticket_conversation_and_status():
    key = ticket()
    assert len(api.get("/api/v1/support/tickets", headers=auth("admin-token")).json()) == 1
    assert (
        api.post(
            f"/api/v1/support/tickets/{key}/messages",
            headers=auth("admin-token"),
            json={"body": "We can help."},
        ).status_code
        == 201
    )
    path = f"/api/v1/admin/support/tickets/{key}"
    assert (
        api.patch(path, headers=auth("admin-token"), json={"status": "RESOLVED"}).status_code == 200
    )
    detail = api.get(f"/api/v1/support/tickets/{key}", headers=auth("alice-token")).json()
    assert [message["body"] for message in detail["messages"]] == [
        "Please help with my account.",
        "We can help.",
    ]
    assert detail["status"] == "RESOLVED"
    api.post(
        f"/api/v1/support/tickets/{key}/messages",
        headers=auth("alice-token"),
        json={"body": "Still need help."},
    )
    assert (
        api.get(f"/api/v1/support/tickets/{key}", headers=auth("admin-token")).json()["status"]
        == "OPEN"
    )


def test_other_user_cannot_read_reply_or_change_status():
    key = ticket()
    assert api.get("/api/v1/support/tickets", headers=auth("bob-token")).json() == []
    assert api.get(f"/api/v1/support/tickets/{key}", headers=auth("bob-token")).status_code == 404
    assert (
        api.post(
            f"/api/v1/support/tickets/{key}/messages",
            headers=auth("bob-token"),
            json={"body": "Intrusion"},
        ).status_code
        == 404
    )
    assert (
        api.patch(
            f"/api/v1/admin/support/tickets/{key}",
            headers=auth("alice-token"),
            json={"status": "RESOLVED"},
        ).status_code
        == 403
    )
    assert api.get("/api/v1/support/tickets").status_code == 401
    assert (
        api.post("/api/v1/support/tickets", json={"subject": "Test", "body": "Test"}).status_code
        == 401
    )


@pytest.mark.parametrize("kind", ["client", "dietitian", "admin", "staff"])
def test_password_reset_hashes_password_and_revokes_sessions(kind):
    stores = {
        "client": (state.users_db, state.client_sessions_db),
        "dietitian": (state.users_db, state.dietitian_sessions_db),
        "admin": (state.admins_db, state.admin_sessions_db),
        "staff": (state.staff_accounts_db, state.staff_sessions_db),
    }
    accounts, sessions = stores[kind]
    account = {
        "id": "target",
        "type": kind,
        "full_name": "Target User",
        "email": "target@example.test",
        "password_hash": hash_password("old-password-123"),
    }
    if kind == "staff":
        account.update(staff_id="target", role="reception", is_active=True)
    accounts["target"] = account
    sessions["target-session"] = "target"
    path = f"/api/v1/admin/accounts/{kind}/target/password"
    result = api.post(path, headers=auth("admin-token"), json={"password": "new-password-456"})
    assert result.status_code == 200
    assert verify_password("new-password-456", account["password_hash"])
    assert not verify_password("old-password-123", account["password_hash"])
    assert "target-session" not in sessions
    assert "new-password-456" not in result.text
    assert (
        api.post(
            "/api/v1/auth/login",
            json={"email": "target@example.test", "password": "old-password-123"},
        ).status_code
        == 401
    )
    assert (
        api.post(
            "/api/v1/auth/login",
            json={"email": "target@example.test", "password": "new-password-456"},
        ).status_code
        == 200
    )


def test_search_and_password_reset_are_admin_only_and_validate_input():
    path = "/api/v1/admin/accounts/client/alice/password"
    assert (
        api.post(path, headers=auth("bob-token"), json={"password": "new-password-456"}).status_code
        == 403
    )
    assert api.get("/api/v1/admin/accounts?q=alice", headers=auth("bob-token")).status_code == 403
    assert (
        api.post(path, headers=auth("admin-token"), json={"password": "short"}).status_code == 422
    )
    assert (
        api.post(
            "/api/v1/admin/accounts/client/missing/password",
            headers=auth("admin-token"),
            json={"password": "new-password-456"},
        ).status_code
        == 404
    )
    results = api.get("/api/v1/admin/accounts?q=alice", headers=auth("admin-token")).json()
    assert results[0]["id"] == "alice"
    assert "password_hash" not in results[0]
    assert (
        api.post(
            "/api/v1/support/tickets",
            headers=auth("alice-token"),
            json={"subject": "  ", "body": "Hello"},
        ).status_code
        == 422
    )


def test_legacy_organization_account_does_not_gain_system_admin_access():
    state.admins_db["executive"] = {"type": "executive"}
    state.admin_sessions_db["executive-token"] = "executive"
    assert (
        api.get("/api/v1/admin/accounts?q=alice", headers=auth("executive-token")).status_code
        == 403
    )


def test_guest_can_submit_but_cannot_read_tickets_or_claim_an_account():
    payload = {
        "contact_email": "alice@example.test",
        "subject": "Locked out",
        "body": "Please help me sign in.",
    }
    response = api.post("/api/v1/support/guest-tickets", json=payload)
    assert response.status_code == 201
    key = response.json()["ticket_id"]
    assert api.get(f"/api/v1/support/tickets/{key}").status_code == 401
    assert api.get(f"/api/v1/support/tickets/{key}", headers=auth("alice-token")).status_code == 404
    detail = api.get(f"/api/v1/support/tickets/{key}", headers=auth("admin-token")).json()
    assert detail["contact_email"] == "alice@example.test"
    assert detail["messages"][0]["body"] == payload["body"]
    assert detail["owner_role"] == "guest"
    assert detail["owner_id"] != "alice"
    assert "contact_email" not in response.json()


def test_guest_support_validates_email_and_limits_repeated_submissions():
    payload = {"contact_email": "invalid", "subject": "Help", "body": "Cannot sign in"}
    assert api.post("/api/v1/support/guest-tickets", json=payload).status_code == 422
    payload["contact_email"] = "guest@example.test"
    for _ in range(5):
        assert api.post("/api/v1/support/guest-tickets", json=payload).status_code == 201
    assert api.post("/api/v1/support/guest-tickets", json=payload).status_code == 429
