import json
from datetime import date, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import app
import config
import state
from state import client_sessions_db
from routers import ai
from security import hash_password

client = TestClient(app.app)


@pytest.fixture(autouse=True)
def clear_in_memory_data(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    client_sessions_db.clear()
    state.ai_recommendations_db.clear()
    state.ai_conversations_db.clear()
    state.admins_db.clear()
    state.businesses_db.clear()
    state.branches_db.clear()
    state.admin_sessions_db.clear()
    state.dietitian_sessions_db.clear()
    state.dietitian_documents_db.clear()
    state.approval_log_db.clear()
    state.clients_db.clear()
    state.appointments_db.clear()
    state.goals_db.clear()
    state.recipes_db.clear()
    state.users_db.clear()
    yield
    client_sessions_db.clear()
    state.ai_recommendations_db.clear()
    state.ai_conversations_db.clear()
    state.admins_db.clear()
    state.businesses_db.clear()
    state.branches_db.clear()
    state.admin_sessions_db.clear()
    state.dietitian_sessions_db.clear()
    state.dietitian_documents_db.clear()
    state.approval_log_db.clear()
    state.clients_db.clear()
    state.appointments_db.clear()
    state.goals_db.clear()
    state.recipes_db.clear()
    state.users_db.clear()


def authenticated_client_headers(client_id):
    token = f"test_client_token_{client_id}"
    client_sessions_db[token] = client_id
    return {"Authorization": f"Bearer {token}"}


def authenticated_dietitian_headers(dietitian_id):
    token = f"test_dietitian_token_{dietitian_id}"
    state.dietitian_sessions_db[token] = dietitian_id
    return {"Authorization": f"Bearer {token}"}


def test_signup_and_login_use_saved_credentials():
    response = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    )

    assert response.status_code == 200
    registered_user = response.json()["user"]
    assert registered_user["type"] == "dietitian"
    assert registered_user["first_name"] == "Avery"
    assert registered_user["last_name"] == "Chen"
    assert registered_user["full_name"] == "Avery Chen"
    assert "password" not in registered_user
    assert "password_hash" not in registered_user

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "avery@example.com", "password": "nutrition-safe-pass"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["id"] == registered_user["id"]


def test_database_client_login_includes_date_of_birth(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", True)
    database_row = {
        "id": "client-1",
        "type": "client",
        "full_name": "Jordan Lee",
        "email": "jordan@example.com",
        "dietitian_id": "dietitian-1",
        "date_of_birth": date(1990, 5, 14),
        "password_hash": hash_password("client-safe-pass"),
    }

    with patch("routers.auth_admin.database.cursor") as cursor_context:
        cursor = cursor_context.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [None, database_row]

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "jordan@example.com", "password": "client-safe-pass"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["date_of_birth"] == "1990-05-14"
    client_query = cursor.execute.call_args_list[1].args[0]
    assert "date_of_birth" in client_query


def test_login_rejects_invalid_credentials():
    client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "dietitian_id": "dietitian-1",
            "id_number": "9005140012345",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "nutrition-safe-pass",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jordan@example.com", "password": "incorrect-password"},
    )

    assert response.status_code == 401


def test_signup_rejects_duplicate_email():
    payload = {
        "first_name": "Avery",
        "last_name": "Chen",
        "email": "avery@example.com",
        "license_number": "RD-2048",
        "password": "nutrition-safe-pass",
    }
    client.post("/api/v1/auth/register/dietitian", json=payload)

    response = client.post("/api/v1/auth/register/dietitian", json=payload)

    assert response.status_code == 409


def test_client_signup_requires_an_existing_dietitian():
    response = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "dietitian_id": "missing-dietitian",
            "id_number": "9005140012345",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "nutrition-safe-pass",
        },
    )

    assert response.status_code == 404


def test_patient_signup_can_skip_dietitian_selection():
    response = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "id_number": "9005140012345",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "nutrition-safe-pass",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["type"] == "client"
    assert response.json()["user"]["dietitian_id"] is None


def test_patient_without_assigned_dietitian_can_book_with_directory_dietitian():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    state.users_db[dietitian["id"]]["status"] = "APPROVED"
    patient = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "id_number": "9005140012345",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    directory = client.get("/api/v1/dietitians")

    appointment = client.post(
        "/api/v1/appointments",
        json={
            "client_id": patient["id"],
            "dietitian_id": directory.json()[0]["id"],
            "appointment_date": (datetime.now() + timedelta(days=5))
            .replace(microsecond=0)
            .isoformat(),
        },
        headers=authenticated_client_headers(patient["id"]),
    )

    assert patient["dietitian_id"] is None
    assert directory.status_code == 200
    assert appointment.status_code == 200
    assert appointment.json()["appointment"]["status"] == "PENDING"


def test_approved_appointment_links_patient_to_dietitian_for_dashboard():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    patient = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "id_number": "9005140012345",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "client_id": patient["id"],
            "dietitian_id": dietitian["id"],
            "appointment_date": (datetime.now() + timedelta(days=5))
            .replace(microsecond=0)
            .isoformat(),
        },
        headers=authenticated_client_headers(patient["id"]),
    ).json()["appointment"]

    response = client.patch(
        f"/api/v1/appointments/{appointment['appointment_id']}",
        json={"action": "APPROVED"},
        headers=authenticated_dietitian_headers(dietitian["id"]),
    )

    assert response.status_code == 200
    assert response.json()["appointment"]["status"] == "CONFIRMED"
    my_patients = client.get(
        f"/api/v1/clients?dietitian_id={dietitian['id']}",
        headers=authenticated_dietitian_headers(dietitian["id"]),
    )
    assert my_patients.status_code == 200
    assert any(item["id"] == patient["id"] for item in my_patients.json())


def test_client_signup_joins_registered_dietitian():
    dietitian_response = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    )
    dietitian_id = dietitian_response.json()["user"]["id"]

    response = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "dietitian_id": dietitian_id,
            "id_number": "9005140012352",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "client-safe-pass",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["dietitian_id"] == dietitian_id
    assert response.json()["user"]["full_name"] == "Jordan Lee"


def test_client_list_is_scoped_to_dietitian():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    client_user = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "dietitian_id": dietitian["id"],
            "id_number": "9005140012352",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "client-safe-pass",
        },
    ).json()["user"]

    response = client.get(
        "/api/v1/clients",
        params={"dietitian_id": dietitian["id"]},
        headers=authenticated_dietitian_headers(dietitian["id"]),
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": client_user["id"],
            "name": "Jordan Lee",
            "dietitian_id": dietitian["id"],
            "status": "ACTIVE",
        }
    ]


def test_admin_workspace_data_routes_require_admin_and_return_practice_data():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Avery",
            "last_name": "Chen",
            "email": "avery@example.com",
            "license_number": "RD-2048",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    client_user = client.post(
        "/api/v1/auth/register/client",
        json={
            "first_name": "Jordan",
            "last_name": "Lee",
            "email": "jordan@example.com",
            "dietitian_id": dietitian["id"],
            "id_number": "9005140012352",
            "phone": "082 123 4567",
            "consent_to_care": True,
            "privacy_notice_version": "2026-10-28-v1",
            "date_of_birth": "1990-05-14",
            "gender": "female",
            "password": "client-safe-pass",
        },
    ).json()["user"]
    assert client.get("/api/v1/admin/dashboard").status_code == 401
    state.admin_sessions_db["test-admin-token"] = "admin-test"
    headers = {"Authorization": "Bearer test-admin-token"}

    dashboard = client.get("/api/v1/admin/dashboard", headers=headers)
    dietitians = client.get("/api/v1/admin/dietitians", headers=headers)
    businesses = client.get("/api/v1/admin/businesses", headers=headers)
    branches = client.get("/api/v1/admin/branches", headers=headers)
    clients = client.get("/api/v1/admin/clients", headers=headers)

    assert dashboard.status_code == 200
    assert dashboard.json()["dietitians"] == 1
    assert dashboard.json()["clients"] == 1
    assert dietitians.json()[0]["dietitian_id"] == dietitian["id"]
    assert "password" not in dietitians.json()[0]
    assert businesses.json()[0]["branch_count"] == 1
    assert branches.json()[0]["business_id"] == dietitian["business_id"]
    assert clients.json()[0]["client_id"] == client_user["id"]

    created_branch = client.post(
        "/api/v1/branches",
        headers=headers,
        json={
            "name": "North Clinic",
            "address": "10 Main Street",
            "business_id": dietitian["business_id"],
        },
    )
    assert created_branch.status_code == 200
    assert client.get("/api/v1/admin/branches", headers=headers).json()[1]["name"] == "North Clinic"

    state.approval_log_db.append(
        {
            "admin_id": "admin-test",
            "entity_type": "DIETITIAN",
            "entity_id": dietitian["id"],
            "action": "REJECTED",
            "comments": "Test audit event",
        }
    )
    audit_logs = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audit_logs.status_code == 200
    assert audit_logs.json()[0]["entity_id"] == dietitian["id"]


def test_dietitian_directory_lists_registered_dietitians():
    dietitian_ids = []
    for full_name, email in [
        ("Morgan Avery", "morgan@example.com"),
        ("Casey Brooks", "casey@example.com"),
    ]:
        response = client.post(
            "/api/v1/auth/register/dietitian",
            json={
                "first_name": full_name.split(" ", 1)[0],
                "last_name": full_name.split(" ", 1)[1],
                "email": email,
                "license_number": f"RD-{email.split('@')[0]}",
                "password": "nutrition-safe-pass",
            },
        )
        dietitian_id = response.json()["user"]["id"]
        state.users_db[dietitian_id]["status"] = "APPROVED"
        dietitian_ids.append(dietitian_id)

    response = client.get("/api/v1/dietitians")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == set(dietitian_ids)
    assert [item["full_name"] for item in response.json()] == ["Casey Brooks", "Morgan Avery"]


def test_approved_dietitian_can_add_practice_branch_as_current_base():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Riley",
            "last_name": "Parker",
            "email": "riley@example.com",
            "license_number": "RD-BRANCH",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    state.users_db[dietitian["id"]]["status"] = "APPROVED"
    state.dietitian_sessions_db["branch-dietitian-token"] = dietitian["id"]
    state.admin_sessions_db["branch-admin-token"] = "admin-branch-test"
    dietitian_headers = {"Authorization": "Bearer branch-dietitian-token"}
    admin_headers = {"Authorization": "Bearer branch-admin-token"}

    branches = client.get("/api/v1/dietitians/me/branches", headers=dietitian_headers)
    assert branches.status_code == 200
    initial_branch_id = branches.json()["current_branch_id"]
    assert len(branches.json()["branches"]) == 1

    created = client.post(
        "/api/v1/dietitians/me/branches",
        headers=dietitian_headers,
        json={"name": "Riverside Clinic", "address": "42 River Road"},
    )
    assert created.status_code == 201
    new_branch = created.json()["branch"]
    assert new_branch["business_id"] == dietitian["business_id"]
    assert state.users_db[dietitian["id"]]["branch_id"] == new_branch["branch_id"]
    assert state.branches_db[initial_branch_id]["business_id"] == new_branch["business_id"]

    directory_entry = next(
        item for item in client.get("/api/v1/dietitians").json() if item["id"] == dietitian["id"]
    )
    assert directory_entry["branch_name"] == "Riverside Clinic"
    assert directory_entry["branch_address"] == "42 River Road"

    admin_entry = next(
        item
        for item in client.get("/api/v1/admin/dietitians", headers=admin_headers).json()
        if item["dietitian_id"] == dietitian["id"]
    )
    assert admin_entry["branch_address"] == "42 River Road"


def test_pending_dietitian_can_add_branch_before_registration_approval():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Pending",
            "last_name": "Practitioner",
            "email": "pending-branch@example.com",
            "license_number": "RD-PENDING-BRANCH",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    state.dietitian_sessions_db["pending-branch-token"] = dietitian["id"]

    response = client.post(
        "/api/v1/dietitians/me/branches",
        headers={"Authorization": "Bearer pending-branch-token"},
        json={"name": "New Branch", "address": "42 River Road"},
    )

    assert response.status_code == 201
    directory = client.get("/api/v1/dietitians").json()
    assert all(item["id"] != dietitian["id"] for item in directory)


def test_verification_documents_require_branch_name_and_location():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "New",
            "last_name": "Applicant",
            "email": "new-applicant@example.com",
            "license_number": "RD-NEW-APPLICANT",
            "password": "nutrition-safe-pass",
        },
    ).json()["user"]
    state.dietitian_sessions_db["applicant-token"] = dietitian["id"]

    response = client.post(
        "/api/v1/dietitians/me/documents",
        headers={"Authorization": "Bearer applicant-token"},
        files={"file": ("license.pdf", b"%PDF-1.4\nverification document", "application/pdf")},
    )

    assert response.status_code == 409
    assert "branch name and location" in response.json()["detail"]


def test_dietitian_rejection_requires_reason_and_allows_resubmission():
    dietitian = client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Taylor",
            "last_name": "Morgan",
            "email": "taylor@example.com",
            "license_number": "RD-REJECTED",
            "password": "dietitian-safe-password",
        },
    ).json()["user"]
    state.admin_sessions_db["admin-token"] = "admin-1"
    state.dietitian_sessions_db["dietitian-token"] = dietitian["id"]
    admin_headers = {"Authorization": "Bearer admin-token"}
    dietitian_headers = {"Authorization": "Bearer dietitian-token"}

    missing_reason = client.post(
        "/api/v1/admin/approvals",
        headers=admin_headers,
        json={"dietitian_id": dietitian["id"], "status": "REJECTED", "notes": "  "},
    )
    assert missing_reason.status_code == 422

    rejection = client.post(
        "/api/v1/admin/approvals",
        headers=admin_headers,
        json={
            "dietitian_id": dietitian["id"],
            "status": "REJECTED",
            "notes": "Please upload a current license.",
        },
    )
    assert rejection.status_code == 200
    approval = client.get("/api/v1/dietitians/me/approval", headers=dietitian_headers)
    assert approval.status_code == 200
    assert approval.json() == {
        "status": "REJECTED",
        "rejection_reason": "Please upload a current license.",
    }

    resubmission = client.post(
        "/api/v1/dietitians/me/approval/resubmit",
        headers=dietitian_headers,
    )
    assert resubmission.status_code == 200
    assert resubmission.json()["status"] == "PENDING"
    assert (
        client.get(
            "/api/v1/dietitians/me/approval",
            headers=dietitian_headers,
        ).json()["rejection_reason"]
        == "Please upload a current license."
    )
    assert any(
        item["dietitian_id"] == dietitian["id"]
        for item in client.get(
            "/api/v1/admin/approvals/pending",
            headers=admin_headers,
        ).json()
    )


def test_pending_dietitian_is_not_in_client_directory():
    client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Waiting",
            "last_name": "Dietitian",
            "email": "waiting@example.com",
            "license_number": "RD-WAITING",
            "password": "nutrition-safe-pass",
        },
    )

    response = client.get("/api/v1/dietitians")

    assert response.status_code == 200
    assert response.json() == []


def test_ai_chat_supports_food_and_exercise_questions():
    with patch(
        "routers.ai._create_chat_agent",
        return_value=RunnableLambda(
            lambda state: {
                "messages": [
                    *state["messages"],
                    AIMessage(
                        content="Try a meal with protein and carbohydrates after your workout."
                    ),
                ]
            }
        ),
    ):
        response = client.post(
            "/api/v1/ai/chat",
            json={
                "user_id": "client-42",
                "role": "client",
                "message": "What should I eat after a workout for muscle recovery?",
            },
            headers=authenticated_client_headers("client-42"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert "reply" in payload
    assert "workout" in payload["reply"].lower() or "food" in payload["reply"].lower()
    assert "messages" in payload
    assert payload["messages"][-1]["role"] == "assistant"


def test_chat_model_uses_bounded_context_and_response_length():
    with patch("routers.ai.ChatOllama") as model_factory:
        ai._create_chat_model()

    options = model_factory.call_args.kwargs
    assert options["num_ctx"] == 4096
    assert options["num_predict"] == 256


def test_chat_agent_is_reused_between_requests():
    ai._create_chat_agent.cache_clear()
    try:
        with (
            patch("routers.ai.create_agent", return_value=object()) as create_agent,
            patch("routers.ai._create_chat_model") as create_model,
        ):
            first_agent = ai._create_chat_agent("client")
            second_agent = ai._create_chat_agent("client")

        assert first_agent is second_agent
        create_agent.assert_called_once()
        create_model.assert_called_once_with()
    finally:
        ai._create_chat_agent.cache_clear()


@pytest.mark.parametrize("message", ["hey", "hey,how are you", "Hello!", "Good morning"])
def test_ai_chat_answers_greetings_without_reusing_old_nutrition_context(message):
    state.ai_conversations_db["client-greeting"] = [
        {"role": "user", "content": "How much protein is in grilled chicken?"},
        {"role": "assistant", "content": "It has about 31 grams of protein per 100 grams."},
    ]

    with patch("routers.ai._create_chat_agent") as mock_agent:
        response = client.post(
            "/api/v1/ai/chat",
            json={
                "user_id": "client-greeting",
                "role": "client",
                "message": message,
            },
            headers=authenticated_client_headers("client-greeting"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert "hi!" in payload["reply"].lower()
    assert "protein" not in payload["reply"].lower()
    assert "chicken" not in payload["reply"].lower()
    assert payload["messages"][-2]["content"] == message
    assert payload["messages"][-1]["content"] == payload["reply"]
    mock_agent.assert_not_called()


def test_ai_chat_sends_plain_turns_and_recent_conversation_to_ollama():
    state.ai_conversations_db["client:client-history"] = [
        {"role": "user", "content": "I avoid dairy."},
        {"role": "assistant", "content": "I will keep that in mind."},
    ]
    prompt_messages = []

    def capture_agent_state(state):
        prompt_messages.extend(
            {
                "role": {"ai": "assistant", "human": "user"}.get(message.type, message.type),
                "content": message.content,
            }
            for message in state["messages"]
        )
        return {
            "messages": [
                *state["messages"],
                AIMessage(content="Try eggs, beans, or tofu for protein."),
            ]
        }

    with patch(
        "routers.ai._create_chat_agent",
        return_value=RunnableLambda(capture_agent_state),
    ):
        response = client.post(
            "/api/v1/ai/chat",
            json={
                "user_id": "client-history",
                "role": "client",
                "message": "What can I eat after training?",
            },
            headers=authenticated_client_headers("client-history"),
        )

    assert response.status_code == 200
    assert response.json()["reply"] == "Try eggs, beans, or tofu for protein."

    assert prompt_messages[-3:-1] == [
        {"role": "user", "content": "I avoid dairy."},
        {"role": "assistant", "content": "I will keep that in mind."},
    ]

    assert prompt_messages[-1]["role"] == "user"
    assert prompt_messages[-1]["content"].startswith("What can I eat after training?")
    assert "Local reference excerpts" in prompt_messages[-1]["content"]


def test_ai_chat_returns_clear_fallback_when_ollama_is_unavailable(caplog):
    def fail_model(_):
        raise httpx.ConnectError("Ollama is offline")

    with patch("routers.ai._create_chat_agent", return_value=RunnableLambda(fail_model)):
        reply = ai.generate_llama_chat_reply("What should I eat after a workout?", "client")

    assert "can't reach the ai model" in reply.lower()
    assert "LangChain AI chat request failed" in caplog.text


def test_food_catalog_tool_returns_matching_foods():
    result = json.loads(ai.search_food_catalog.invoke({"query": "oat"}))

    assert result[0]["name"] == "Oatmeal"
    assert result[0]["calories"] == 150


def ollama_response(plan):
    return RunnableLambda(lambda _: AIMessage(content=json.dumps({"plan": plan})))


def test_generate_plan_returns_pending_recommendation():
    state.clients_db["client-1"] = {
        "id": "client-1",
        "dietitian_id": "dietitian-1",
    }

    with patch(
        "routers.ai._create_chat_model",
        return_value=ollama_response(["Breakfast: oatmeal"]),
    ):
        response = client.post(
            "/api/v1/ai/generate-plan",
            json={
                "client_id": "client-1",
                "dietary_goal": "More fiber",
            },
            headers=authenticated_dietitian_headers("dietitian-1"),
        )

    assert response.status_code == 200
    recommendation = response.json()["recommendation"]
    assert recommendation["generated_plan"] == ["Breakfast: oatmeal"]
    assert recommendation["status"] == "PENDING_REVIEW"


def test_generate_plan_forwards_allergies_and_conditions():
    state.clients_db["client-2"] = {
        "id": "client-2",
        "dietitian_id": "dietitian-1",
        "allergies": [{"allergen": "peanuts", "severity": "severe"}],
        "conditions": [{"condition_name": "diabetes"}],
    }

    prompt_messages = []

    def capture_prompt(prompt_value):
        prompt_messages.extend(prompt_value.to_messages())
        return AIMessage(content=json.dumps({"plan": ["Balanced meals"]}))

    with patch(
        "routers.ai._create_chat_model",
        return_value=RunnableLambda(capture_prompt),
    ):
        response = client.post(
            "/api/v1/ai/generate-plan",
            json={
                "client_id": "client-2",
                "dietary_goal": "Balanced meals",
            },
            headers=authenticated_dietitian_headers("dietitian-1"),
        )

    assert response.status_code == 200, response.text
    assert len(prompt_messages) >= 2

    context = json.loads(prompt_messages[1].content)

    assert "peanuts" in json.dumps(context).lower()
    assert "severe" in json.dumps(context).lower()
    assert "diabetes" in json.dumps(context).lower()


def test_generate_plan_returns_503_when_ollama_is_unreachable():
    state.clients_db["client-3"] = {
        "id": "client-3",
        "dietitian_id": "dietitian-1",
    }

    def fail_model(_):
        raise httpx.ConnectError("Ollama unavailable")

    with patch(
        "routers.ai._create_chat_model",
        return_value=RunnableLambda(fail_model),
    ):
        response = client.post(
            "/api/v1/ai/generate-plan",
            json={
                "client_id": "client-3",
                "dietary_goal": "More vegetables",
            },
            headers=authenticated_dietitian_headers("dietitian-1"),
        )

    assert response.status_code == 503


def test_generate_plan_returns_503_for_malformed_model_response():
    state.clients_db["client-4"] = {
        "id": "client-4",
        "dietitian_id": "dietitian-1",
    }

    with patch(
        "routers.ai._create_chat_model",
        return_value=RunnableLambda(lambda _: AIMessage(content="not json")),
    ):
        response = client.post(
            "/api/v1/ai/generate-plan",
            json={
                "client_id": "client-4",
                "dietary_goal": "More vegetables",
            },
            headers=authenticated_dietitian_headers("dietitian-1"),
        )

    assert response.status_code == 503, response.text


def test_health_endpoint_reports_online():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_root_serves_frontend():
    response = client.get("/")

    assert response.status_code == 200
    assert "Welcome back." in response.text


def test_foods_endpoint_returns_food_items():
    response = client.get("/api/v1/foods")

    assert response.status_code == 200
    assert any(food["name"] == "Oatmeal" for food in response.json())


def test_only_admin_can_add_food_to_library():
    payload = {
        "name": "Roasted chickpeas",
        "calories": 164,
        "protein_g": 8.9,
        "carbs_g": 27.4,
        "fat_g": 2.6,
        "glycemic_index": 28,
    }
    assert client.post("/api/v1/foods", json=payload).status_code == 401

    state.admin_sessions_db["food-admin-token"] = "admin-food-test"
    headers = {"Authorization": "Bearer food-admin-token"}
    response = client.post("/api/v1/foods", headers=headers, json=payload)

    assert response.status_code == 201
    assert response.json()["name"] == payload["name"]
    assert any(
        food["food_id"] == response.json()["food_id"] for food in client.get("/api/v1/foods").json()
    )
    duplicate = client.post("/api/v1/foods", headers=headers, json=payload)
    assert duplicate.status_code == 409


def test_recipe_create_and_list():
    recipe = {
        "title": "Berry oats",
        "ingredients": ["oats", "berries"],
        "instructions": "Cook oats, then add berries.",
    }

    # Read-only recipe catalogue is public, but modifications require a dietitian.
    assert client.post("/api/v1/recipes", json=recipe).status_code == 401
    headers = authenticated_dietitian_headers("recipe-dietitian")
    created = client.post("/api/v1/recipes", json=recipe, headers=headers)
    listing = client.get("/api/v1/recipes")

    assert created.status_code == 200
    saved = next(
        item for item in listing.json() if item["recipe_id"] == created.json()["recipe_id"]
    )
    assert saved["title"] == recipe["title"]
    assert saved["ingredients"] == recipe["ingredients"]


def test_meal_plan_create_and_list():
    state.users_db["client-plan-test"] = {
        "id": "client-plan-test",
        "type": "client",
        "dietitian_id": "dietitian-1",
    }

    headers = authenticated_dietitian_headers("dietitian-1")

    plan = client.post(
        "/api/v1/meal-plans",
        json={
            "client_id": "client-plan-test",
            "diet_type": "Balanced",
            "days": 3,
        },
        headers=headers,
    )

    assert plan.status_code == 409, plan.text
    assert "Sample-meal generation is disabled" in plan.json()["detail"]

    listing = client.get(
        "/api/v1/meal-plans",
        params={"client_id": "client-plan-test"},
        headers=headers,
    )

    assert listing.status_code == 200, listing.text
    assert listing.json() == []


def test_appointments_can_be_filtered_by_client():
    appointment_date = (datetime.now() + timedelta(days=8)).replace(microsecond=0).isoformat()
    for client_id in ("client-a", "client-b"):
        response = client.post(
            "/api/v1/appointments",
            json={
                "client_id": client_id,
                "dietitian_id": "dietitian-1",
                "appointment_date": appointment_date,
            },
            headers=authenticated_client_headers(client_id),
        )
        assert response.status_code == 200

    response = client.get(
        "/api/v1/appointments",
        params={"client_id": "client-a"},
        headers=authenticated_client_headers("client-a"),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["client_id"] == "client-a"


def test_goals_can_be_created_by_dietitian_and_viewed_by_client():
    state.users_db["client-goal-test"] = {
        "id": "client-goal-test", "type": "client", "dietitian_id": "diet-goal-test"
    }
    created = client.post(
        "/api/v1/goals",
        json={
            "client_id": "client-goal-test",
            "target_metric": "Weight",
            "target_value": 72.5,
        },
        headers=authenticated_dietitian_headers("diet-goal-test"),
    )

    assert created.status_code == 200, created.text

    listing = client.get(
        "/api/v1/goals",
        params={"client_id": "client-goal-test"},
        headers=authenticated_client_headers("client-goal-test"),
    )

    assert listing.status_code == 200, listing.text
    assert listing.json() == [created.json()["goal"]]


def test_patient_progress_saves_and_preserves_partial_metric_updates():
    first_entry = client.post(
        "/api/v1/clients/patient-progress-test/progress",
        json={
            "weight_kg": 72.5,
            "body_fat_pct": 21.4,
            "waist_cm": 82,
            "calories": 2100,
            "water_ml": 2000,
            "steps": 8500,
            "sleep_hours": 7.33,
        },
        headers=authenticated_client_headers("patient-progress-test"),
    )
    assert first_entry.status_code == 200

    partial_update = client.post(
        "/api/v1/clients/patient-progress-test/progress",
        json={"weight_kg": 72.2},
        headers=authenticated_client_headers("patient-progress-test"),
    )
    history = client.get(
        "/api/v1/clients/patient-progress-test/progress",
        headers=authenticated_client_headers("patient-progress-test"),
    )

    assert partial_update.status_code == 200
    assert len(history.json()) == 1
    saved = history.json()[0]
    assert saved["weight_kg"] == 72.2
    assert saved["body_fat_pct"] == 21.4
    assert saved["waist_cm"] == 82
    assert saved["calories"] == 2100
    assert saved["water_ml"] == 2000
    assert saved["steps"] == 8500
    assert saved["sleep_hours"] == 7.33


def test_appointment_lifecycle_supports_approval_rejection_and_cancellation():
    appointment_date = (datetime.now() + timedelta(days=5)).replace(microsecond=0).isoformat()
    created = client.post(
        "/api/v1/appointments",
        json={
            "client_id": "client-a",
            "dietitian_id": "dietitian-1",
            "appointment_date": appointment_date,
        },
        headers=authenticated_client_headers("client-a"),
    )
    appointment = created.json()["appointment"]
    assert created.status_code == 200
    assert appointment["status"] == "PENDING"

    approved = client.patch(
        f"/api/v1/appointments/{appointment['appointment_id']}",
        json={"action": "APPROVED"},
        headers=authenticated_dietitian_headers("dietitian-1"),
    )
    assert approved.status_code == 200
    assert approved.json()["appointment"]["status"] == "CONFIRMED"
    patient_appointments = client.get(
        "/api/v1/appointments",
        params={"client_id": "client-a"},
        headers=authenticated_client_headers("client-a"),
    )
    assert patient_appointments.json()[0]["status"] == "CONFIRMED"

    cancelled = client.patch(
        f"/api/v1/appointments/{appointment['appointment_id']}",
        json={"action": "CANCELLED"},
        headers=authenticated_client_headers("client-a"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["appointment"]["status"] == "CANCELLED"

    rejected_request = client.post(
        "/api/v1/appointments",
        json={
            "client_id": "client-b",
            "dietitian_id": "dietitian-1",
            "appointment_date": appointment_date,
        },
        headers=authenticated_client_headers("client-b"),
    ).json()["appointment"]
    rejected = client.patch(
        f"/api/v1/appointments/{rejected_request['appointment_id']}",
        json={"action": "REJECTED"},
        headers=authenticated_dietitian_headers("dietitian-1"),
    )
    assert rejected.status_code == 200
    assert rejected.json()["appointment"]["status"] == "REJECTED"


def test_appointment_decisions_only_apply_to_pending_requests():
    appointment = client.post(
        "/api/v1/appointments",
        json={
            "client_id": "client-a",
            "dietitian_id": "dietitian-1",
            "appointment_date": (datetime.now() + timedelta(days=3))
            .replace(microsecond=0)
            .isoformat(),
        },
        headers=authenticated_client_headers("client-a"),
    ).json()["appointment"]
    client.patch(
        f"/api/v1/appointments/{appointment['appointment_id']}",
        json={"action": "REJECTED"},
        headers=authenticated_dietitian_headers("dietitian-1"),
    )

    response = client.patch(
        f"/api/v1/appointments/{appointment['appointment_id']}",
        json={"action": "APPROVED"},
        headers=authenticated_dietitian_headers("dietitian-1"),
    )

    assert response.status_code == 409


def test_client_recommendations_only_lists_reviewed_items_for_client():
    state.ai_recommendations_db.update(
        {
            "rec-client-approved": {
                "recommendation_id": "rec-client-approved",
                "client_id": "client-a",
                "status": "APPROVED",
            },
            "rec-client-pending": {
                "recommendation_id": "rec-client-pending",
                "client_id": "client-a",
                "status": "PENDING_REVIEW",
            },
            "rec-other-approved": {
                "recommendation_id": "rec-other-approved",
                "client_id": "client-b",
                "status": "APPROVED",
            },
        }
    )

    response = client.get(
        "/api/v1/ai/recommendations",
        params={"client_id": "client-a"},
        headers=authenticated_client_headers("client-a"),
    )

    assert response.status_code == 200, response.text
    assert [item["recommendation_id"] for item in response.json()] == ["rec-client-approved"]


def test_pending_recommendations_only_returns_pending_items():
    state.clients_db["client-a"] = {
        "id": "client-a",
        "dietitian_id": "dietitian-1",
    }

    state.ai_recommendations_db.update(
        {
            "rec-pending": {
                "recommendation_id": "rec-pending",
                "client_id": "client-a",
                "dietitian_id": "dietitian-1",
                "status": "PENDING_REVIEW",
            },
            "rec-approved": {
                "recommendation_id": "rec-approved",
                "client_id": "client-a",
                "dietitian_id": "dietitian-1",
                "status": "APPROVED",
            },
        }
    )

    response = client.get(
        "/api/v1/ai/recommendations/pending",
        headers=authenticated_dietitian_headers("dietitian-1"),
    )

    assert response.status_code == 200, response.text
    assert [item["recommendation_id"] for item in response.json()] == ["rec-pending"]


def test_client_health_profile_loads_conditions_allergies_and_pregnancy():
    state.clients_db["client-health"] = {
        "allergies": [{"allergen": "Peanuts", "severity": "severe"}],
        "conditions": [{"condition_name": "Asthma"}],
        "pregnancy": {"trimester": 2, "due_date": "2027-03-01"},
        "metrics": [],
        "progress": [],
    }

    response = client.get(
        "/api/v1/clients/client-health/profile",
        headers=authenticated_client_headers("client-health"),
    )

    assert response.status_code == 200
    assert response.json()["allergies"] == state.clients_db["client-health"]["allergies"]
    assert response.json()["conditions"] == state.clients_db["client-health"]["conditions"]
    assert response.json()["pregnancy"] == state.clients_db["client-health"]["pregnancy"]


def test_health_history_entries_save_for_a_client():
    state.clients_db["client-health"] = {
        "allergies": [],
        "conditions": [],
        "metrics": [],
        "progress": [],
    }

    allergy = client.post(
        "/api/v1/clients/client-health/allergies",
        json={"allergen": "Peanuts", "severity": "severe"},
        headers=authenticated_client_headers("client-health"),
    )
    condition = client.post(
        "/api/v1/clients/client-health/medical-conditions",
        json={"condition_name": "Asthma"},
        headers=authenticated_client_headers("client-health"),
    )
    pregnancy = client.post(
        "/api/v1/clients/client-health/pregnancy",
        json={"trimester": 2, "due_date": "2027-03-01"},
        headers=authenticated_client_headers("client-health"),
    )

    assert allergy.status_code == 200
    assert condition.status_code == 200
    assert pregnancy.status_code == 200
    profile = client.get(
        "/api/v1/clients/client-health/profile",
        headers=authenticated_client_headers("client-health"),
    ).json()
    assert profile["allergies"] == [{"allergen": "Peanuts", "severity": "severe"}]
    assert profile["conditions"] == [{"condition_name": "Asthma", "icd_code": None}]
    assert profile["pregnancy"] == {"trimester": 2, "due_date": "2027-03-01"}


def test_review_recommendation_updates_status_and_notes():
    state.clients_db["client-review"] = {
        "id": "client-review",
        "dietitian_id": "dietitian-1",
    }

    state.ai_recommendations_db["rec-review"] = {
        "recommendation_id": "rec-review",
        "client_id": "client-review",
        "dietitian_id": "dietitian-1",
        "status": "PENDING_REVIEW",
    }

    response = client.patch(
        "/api/v1/ai/recommendations/rec-review",
        json={
            "action": "APPROVED",
            "notes": "Reviewed by dietitian",
        },
        headers=authenticated_dietitian_headers("dietitian-1"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["recommendation"]["status"] == "APPROVED"
    assert response.json()["recommendation"]["review_notes"] == "Reviewed by dietitian"


def test_admin_setup_login_and_audited_dietitian_approval():
    local_client = TestClient(app.app, client=("127.0.0.1", 8765))
    remote_client = TestClient(app.app, client=("192.0.2.25", 8765))
    assert local_client.get("/api/v1/admin/setup-status").json() == {"available": True}
    assert remote_client.get("/api/v1/admin/setup-status").json() == {"available": False}
    assert (
        remote_client.post(
            "/api/v1/admin/setup",
            json={
                "first_name": "Admin",
                "last_name": "Reviewer",
                "email": "admin@example.com",
                "password": "admin-safe-password",
            },
        ).status_code
        == 403
    )

    setup = local_client.post(
        "/api/v1/admin/setup",
        json={
            "first_name": "Admin",
            "last_name": "Reviewer",
            "email": "admin@example.com",
            "password": "admin-safe-password",
        },
    )
    assert setup.status_code == 201
    assert setup.json()["user"]["full_name"] == "Admin Reviewer"
    assert local_client.get("/api/v1/admin/setup-status").json() == {"available": False}
    assert (
        local_client.post(
            "/api/v1/admin/setup",
            json={
                "first_name": "Second",
                "last_name": "Admin",
                "email": "second-admin@example.com",
                "password": "admin-safe-password",
            },
        ).status_code
        == 409
    )
    assert local_client.get("/api/v1/admin/approvals/pending").status_code == 401

    login = local_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "admin-safe-password"},
    )
    authorization = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert login.status_code == 200
    assert login.json()["user"]["type"] == "admin"

    dietitian = local_client.post(
        "/api/v1/auth/register/dietitian",
        json={
            "first_name": "Pending",
            "last_name": "Dietitian",
            "email": "pending@example.com",
            "license_number": "RD-PENDING",
            "password": "dietitian-safe-password",
        },
    ).json()["user"]
    assert local_client.get("/api/v1/dietitians/me/documents").status_code == 401
    dietitian_login = local_client.post(
        "/api/v1/auth/login",
        json={"email": "pending@example.com", "password": "dietitian-safe-password"},
    )
    dietitian_authorization = {"Authorization": f"Bearer {dietitian_login.json()['access_token']}"}
    branch_response = local_client.post(
        "/api/v1/dietitians/me/branches",
        headers=dietitian_authorization,
        json={"name": "Registration Clinic", "address": "12 Health Street"},
    )
    assert branch_response.status_code == 201
    blocked_approval = local_client.post(
        "/api/v1/admin/approvals",
        headers=authorization,
        json={"dietitian_id": dietitian["id"], "status": "APPROVED"},
    )
    assert blocked_approval.status_code == 409
    invalid_upload = local_client.post(
        "/api/v1/dietitians/me/documents",
        headers=dietitian_authorization,
        files={"file": ("license.txt", b"not a supported document", "text/plain")},
    )
    assert invalid_upload.status_code == 415
    upload = local_client.post(
        "/api/v1/dietitians/me/documents",
        headers=dietitian_authorization,
        files={"file": ("license.pdf", b"%PDF-1.4\nverification document", "application/pdf")},
    )
    assert upload.status_code == 201
    submitted_branch = upload.json()["branch"]
    registered_branch = branch_response.json()["branch"]
    assert submitted_branch["branch_id"] == registered_branch["branch_id"]
    assert submitted_branch["business_id"] == registered_branch["business_id"]
    assert submitted_branch["name"] == "Registration Clinic"
    assert submitted_branch["address"] == "12 Health Street"
    later_branch = local_client.post(
        "/api/v1/dietitians/me/branches",
        headers=dietitian_authorization,
        json={"name": "Later Clinic", "address": "99 New Street"},
    )
    assert later_branch.status_code == 201
    listed_document = local_client.get(
        "/api/v1/dietitians/me/documents",
        headers=dietitian_authorization,
    ).json()[0]
    assert listed_document["branch_id"] == submitted_branch["branch_id"]
    assert listed_document["branch_name"] == "Registration Clinic"
    assert (
        local_client.get(
            f"/api/v1/admin/dietitian-documents/{upload.json()['document_id']}"
        ).status_code
        == 401
    )
    document = local_client.get(
        f"/api/v1/admin/dietitian-documents/{upload.json()['document_id']}",
        headers=authorization,
    )
    assert document.status_code == 200
    assert document.content.startswith(b"%PDF-")
    pending = local_client.get("/api/v1/admin/approvals/pending", headers=authorization)
    assert pending.status_code == 200
    assert pending.json()[0]["dietitian_id"] == dietitian["id"]
    assert pending.json()[0]["documents"][0]["file_name"] == "license.pdf"
    submitted_document = pending.json()[0]["documents"][0]
    assert submitted_document["branch_id"] == submitted_branch["branch_id"]
    assert submitted_document["business_id"] == submitted_branch["business_id"]
    assert submitted_document["branch_name"] == submitted_branch["name"]
    assert submitted_document["branch_address"] == submitted_branch["address"]
    assert pending.json()[0]["branch_name"] == "Later Clinic"
    assert pending.json()[0]["branch_address"] == "99 New Street"

    approval = local_client.post(
        "/api/v1/admin/approvals",
        headers=authorization,
        json={
            "dietitian_id": dietitian["id"],
            "status": "APPROVED",
            "notes": "Credentials verified",
        },
    )

    assert approval.status_code == 200
    assert state.users_db[dietitian["id"]]["status"] == "APPROVED"
    assert state.approval_log_db[0]["admin_id"] == login.json()["user"]["id"]
    assert state.approval_log_db[0]["comments"] == "Credentials verified"
    approved_directory_entry = next(
        item
        for item in local_client.get("/api/v1/dietitians").json()
        if item["id"] == dietitian["id"]
    )
    assert approved_directory_entry["branch_name"] == "Later Clinic"
    assert approved_directory_entry["branch_address"] == "99 New Street"
