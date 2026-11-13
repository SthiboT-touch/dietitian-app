from copy import deepcopy
from types import SimpleNamespace

import pytest
import config
from ai_cache import ResponseCache
from routers import ai


def test_cache_expires_evicts_and_copies_values(monkeypatch):
    monkeypatch.setattr(config, "AI_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(config, "AI_CACHE_MAX_ENTRIES", 2)
    now = [0]
    cache = ResponseCache(clock=lambda: now[0])
    cache.put("one", {"plan": ["original"]})
    cached = cache.get("one")
    cached["plan"].append("changed")
    assert cache.get("one") == {"plan": ["original"]}
    cache.put("two", {})
    cache.get("one")
    cache.put("three", {})
    assert cache.get("two") is None
    now[0] = 10
    assert cache.get("one") is None
    assert cache.get("three") is None


def test_cache_can_be_disabled_and_skips_large_responses(monkeypatch):
    cache = ResponseCache()
    monkeypatch.setattr(config, "AI_CACHE_TTL_SECONDS", 0)
    cache.put("one", {"reply": "answer"})
    assert cache.get("one") is None
    monkeypatch.setattr(config, "AI_CACHE_TTL_SECONDS", 300)
    cache.put("large", {"reply": "x" * 64001})
    assert cache.get("large") is None


@pytest.mark.parametrize("change", ["scope", "history", "patient", "guidance", "model", "references"])
def test_chat_cache_hits_and_invalidates_when_context_changes(monkeypatch, change):
    calls = []
    references = []

    class Agent:
        def invoke(self, payload, **kwargs):
            calls.append(payload)
            return {"messages": [SimpleNamespace(content="Draft answer", tool_calls=[])]}

    monkeypatch.setattr(ai, "_create_chat_agent", lambda role: Agent())
    monkeypatch.setattr(ai, "retrieve_context", lambda query: references)
    state = {"user_id": "dietitian:d1:patient:c1", "role": "patient_dietitian",
             "message": "Suggest priorities", "conversation": [],
             "patient_context": {"conditions": ["hypertension"], "clinician_guidance": "Less salt"}}
    # Reference invalidation is exercised on general chat, which performs retrieval.
    if change == "references":
        state.pop("patient_context")
    ai._reply_with_chat_agent(state)
    ai._reply_with_chat_agent(state)
    assert len(calls) == 1
    changed = deepcopy(state)
    if change == "scope":
        changed["user_id"] = "dietitian:d2:patient:c2"
    elif change == "history":
        changed["conversation"] = [{"role": "user", "content": "Previous question"}]
    elif change == "patient":
        changed["patient_context"]["conditions"] = ["diabetes"]
    elif change == "guidance":
        changed["patient_context"]["clinician_guidance"] = "New guidance"
    elif change == "model":
        monkeypatch.setenv("OLLAMA_MODEL", "another-model")
    else:
        references.append({"source": "new.txt", "paragraph": 1, "excerpt": "Updated reference"})
    ai._reply_with_chat_agent(changed)
    assert len(calls) == 2


def test_failures_and_tool_results_are_not_cached(monkeypatch):
    calls = []

    class Agent:
        def invoke(self, payload, **kwargs):
            calls.append(payload)
            if len(calls) == 1:
                raise TimeoutError()
            return {"messages": [SimpleNamespace(type="tool", content="catalog"),
                                 SimpleNamespace(content="Found food", tool_calls=[])]}

    monkeypatch.setattr(ai, "_create_chat_agent", lambda role: Agent())
    monkeypatch.setattr(ai, "retrieve_context", lambda query: [])
    state = {"user_id": "dietitian:d1", "role": "dietitian", "message": "Catalog question"}
    for _ in range(3):
        ai._reply_with_chat_agent(state)
    assert len(calls) == 3


def test_plan_cache_preserves_patient_scope_and_updates(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, "retrieve_context", lambda query: [])
    monkeypatch.setattr(ai, "generate_llama_plan", lambda goal, profile: calls.append(goal) or ["Draft plan"])
    state = {"client_id": "c1", "dietitian_id": "d1", "dietary_goal": "Balanced meals",
             "client_profile": {"allergies": []}}
    ai._generate_plan_node(state)
    ai._generate_plan_node(state)
    assert len(calls) == 1
    ai._generate_plan_node({**state, "client_id": "c2"})
    ai._generate_plan_node({**state, "client_profile": {"allergies": ["peanut"]}})
    assert len(calls) == 3
