"""Patient-grounded chat uses authorized records and isolated histories, never real AI."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
import app
import config
import state
from routers import ai

api = TestClient(app.app)
headers = {"Authorization": "Bearer clinician"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    stores = [state.users_db, state.clients_db, state.dietitian_sessions_db,
              state.client_sessions_db, state.goals_db, ai.patient_agent_sessions]
    for store in stores:
        store.clear()
    state.users_db.update({
        "d1": {"id": "d1", "type": "dietitian", "status": "APPROVED", "specialisation": "Diabetes care"},
        "d2": {"id": "d2", "type": "dietitian", "status": "APPROVED"},
        "c1": {"id": "c1", "type": "client", "dietitian_id": "d1", "full_name": "Patient One", "dietary_preferences": "vegetarian"},
        "c2": {"id": "c2", "type": "client", "dietitian_id": "d1", "full_name": "Patient Two"},
        "c3": {"id": "c3", "type": "client", "dietitian_id": "d2", "full_name": "Patient Three"},
    })
    for client_id in ("c1", "c2", "c3"):
        state.clients_db[client_id] = {"allergies": [], "conditions": [], "metrics": [], "progress": []}
    state.dietitian_sessions_db["clinician"] = "d1"
    state.client_sessions_db["patient"] = "c1"
    yield
    for store in stores:
        store.clear()


def activate(client_id="c1", guidance="Avoid added salt"):
    return api.post(f"/api/v1/ai/patients/{client_id}/activate", headers=headers,
                    json={"guidance": guidance})


def chat(client_id="c1", message="Suggest nutrition priorities"):
    return api.post(f"/api/v1/ai/patients/{client_id}/chat", headers=headers, json={"message": message})


def test_activation_and_chat_require_assigned_clinician():
    for action, body in (("activate", {}), ("chat", {"message": "Help"})):
        url = f"/api/v1/ai/patients/c1/{action}"
        assert api.post(url, json=body).status_code == 401
        assert api.post(url, headers={"Authorization": "Bearer patient"}, json=body).status_code == 401
    assert activate("c3").status_code == 403
    assert chat("c3").status_code == 403
    assert chat().status_code == 409
    assert not ai.patient_agent_sessions


def test_patient_selection_returns_ids_used_for_activation():
    response = api.get("/api/v1/clients?dietitian_id=d1", headers=headers)
    assert response.status_code == 200
    assert {patient["id"] for patient in response.json()} == {"c1", "c2"}


def test_grounding_refreshes_records_without_library_lookup_and_isolates_patients(monkeypatch):
    calls, trace_states = [], []

    class Agent:
        def invoke(self, payload, **kwargs):
            calls.append((payload["messages"], kwargs))
            return {"messages": [SimpleNamespace(content="Draft nutrition priorities", tool_calls=[])]}

    @contextmanager
    def tracing(enabled=None, **kwargs):
        trace_states.append(enabled)
        yield

    monkeypatch.setattr(ai, "_create_chat_agent", lambda role: Agent())
    monkeypatch.setattr(
        ai, "retrieve_context",
        lambda query: pytest.fail("Patient assistant must not query the reference library"),
    )
    monkeypatch.setattr(ai, "tracing_context", tracing)
    state.clients_db["c1"]["allergies"] = [{"allergen": "peanut", "severity": "severe"}]
    state.clients_db["c1"]["conditions"] = [{"condition_name": "hypertension"}]
    state.clients_db["c1"]["pregnancy"] = {"due_date": "2027-01-01"}
    state.clients_db["c1"]["lactation"] = {"is_active": True}
    state.goals_db["c1"] = [{"target_metric": "sodium", "target_value": 1500}]
    state.clients_db["c1"]["care_events"] = [{"kind": "RECOMMENDATION", "author_id": "d1", "payload": {"content": "Limit sodium"}}]
    result = activate()
    assert result.status_code == 200, result.text
    assert result.json()["context"]["clinician_guidance"] == "Avoid added salt"
    assert result.json()["context"]["clinician_profile"]["specialisation"] == "Diabetes care"
    assert "pregnancy" not in result.json()["context"]
    assert "lactation" not in result.json()["context"]
    # A change after activation must reach the model on its next invocation.
    state.clients_db["c1"]["progress"] = [{"weight_kg": 75}]
    response = chat()
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DRAFT_FOR_REVIEW"
    assert response.json()["retrieved_references"] == []
    prompt = calls[-1][0][-1].content
    for fact in ("peanut", "hypertension", "vegetarian", "Avoid added salt", "Diabetes care", "Limit sodium", '"weight_kg": 75', '1500'):
        assert fact in prompt
    assert "Local reference excerpts" not in prompt
    assert trace_states == [False, False]
    assert calls[-1][1] == {}
    assert activate("c2").status_code == 200
    assert chat("c2", "Patient two question").status_code == 200
    assert len(calls[-1][0]) == 1
    assert "peanut" not in calls[-1][0][-1].content
    assert chat().status_code == 200
    assert len(calls[-1][0]) == 3
    assert "Patient two question" not in str(calls[-1][0])
    # Reassignment immediately revokes an existing activation.
    state.users_db["c1"]["dietitian_id"] = "d2"
    assert chat().status_code == 403


def test_reactivation_resets_history_and_replaces_guidance():
    assert activate().status_code == 200
    ai.patient_agent_sessions[("d1", "c1")]["messages"] = [{"role": "user", "content": "Old question"}]
    result = activate(guidance="New clinical priorities")
    assert result.status_code == 200
    assert result.json()["messages"] == []
    assert ai.patient_agent_sessions[("d1", "c1")]["guidance"] == "New clinical priorities"
    assert chat(message="   ").status_code == 422


def test_oversized_record_is_not_silently_truncated():
    state.clients_db["c1"]["allergies"] = [{"allergen": "x" * 31000}]
    response = activate()
    assert response.status_code == 409
    assert not ai.patient_agent_sessions


def test_enabled_maternal_context_is_available_to_the_assistant():
    state.users_db["c1"]["maternal_care_enabled"] = True
    state.clients_db["c1"].update(
        maternal_care_enabled=True,
        pregnancy={"due_date": "2027-01-01"},
        lactation={"is_active": True},
    )

    response = activate()

    assert response.status_code == 200
    assert response.json()["context"]["pregnancy"] == {"due_date": "2027-01-01"}
    assert response.json()["context"]["lactation"] == {"is_active": True}


def test_patient_prompt_excludes_account_secrets(monkeypatch):
    state.users_db["c1"].update(password_hash="private-hash", email="private@example.test", id_number="private-id")
    state.clients_db["c1"]["password"] = "private-password"
    response = activate()
    assert response.status_code == 200
    for secret in ("private-hash", "private@example.test", "private-id", "private-password"):
        assert secret not in response.text
