"""Appointment lifecycle, post-consultation care, and immutable QR visit binding."""
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
import app
import config
import state
from routers import meal_planning as meals

api = TestClient(app.app)


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    stores = [state.users_db, state.clients_db, state.appointments_db, state.goals_db,
              state.client_sessions_db, state.dietitian_sessions_db, state.staff_accounts_db,
              state.staff_sessions_db, state.checkin_credentials_db, state.checkin_events_db,
              state.ai_recommendations_db, state.recipes_db]
    for store in stores:
        store.clear()
    meals._draft_store.clear()
    state.users_db["c"] = {"id": "c", "type": "client", "dietitian_id": "d"}
    state.clients_db["c"] = {"dietitian_id": "d", "progress": []}
    state.client_sessions_db["patient"] = "c"
    state.dietitian_sessions_db.update({"doctor": "d", "other-doctor": "other"})
    state.staff_sessions_db["reception"] = "r"
    state.staff_accounts_db["r"] = {"role": "reception", "is_active": True, "branch_id": "b"}
    yield
    for store in stores:
        store.clear()
    meals._draft_store.clear()


def visit(key="a", status="CONFIRMED", days=-1, client="c", doctor="d"):
    state.appointments_db[key] = {"appointment_id": key, "client_id": client, "dietitian_id": doctor,
        "appointment_date": (datetime.now() + timedelta(days=days)).isoformat(), "status": status, "branch_id": "b"}


def test_completion_requires_appointment_dietitian_and_started_confirmed_visit():
    visit()
    url = "/api/v1/appointments/a/complete"
    assert api.post(url, headers=auth("patient")).status_code == 403
    assert api.post(url, headers=auth("other-doctor")).status_code == 403
    for status in ("PENDING", "REJECTED", "CANCELLED"):
        state.appointments_db["a"]["status"] = status
        assert api.post(url, headers=auth("doctor")).status_code == 409
    visit(days=1)
    assert api.post(url, headers=auth("doctor")).status_code == 409
    visit()
    assert api.post(url, headers=auth("doctor")).status_code == 200
    assert state.appointments_db["a"]["status"] == "COMPLETED"
    assert api.post(url, headers=auth("doctor")).status_code == 409


@pytest.mark.parametrize("status", [None, "PENDING", "CONFIRMED", "CANCELLED", "REJECTED"])
def test_care_creation_is_blocked_before_completed_consultation(status):
    if status:
        visit(status=status)
    assert api.post("/api/v1/goals", json={"client_id": "c", "target_metric": "Water", "target_value": 2000}, headers=auth("doctor")).status_code == 409
    assert api.post("/api/v1/clients/c/care/recommendations", json={"content": "Guidance"}, headers=auth("doctor")).status_code == 409
    with patch("routers.ai._create_plan_workflow") as workflow:
        assert api.post("/api/v1/ai/generate-plan", json={"client_id": "c", "dietary_goal": "Balanced"}, headers=auth("doctor")).status_code == 409
        workflow.assert_not_called()
    with patch("routers.meal_planning.preview_meal_plan_draft") as preview:
        response = api.post("/api/v1/meal-plans/drafts", json={"client_id": "c", "diet_type": "Balanced", "recipe_ids": ["r"]}, headers=auth("doctor"))
        assert response.status_code == 409
        preview.assert_not_called()
    assert not state.goals_db
    assert not state.clients_db["c"].get("care_events")
    assert api.post("/api/v1/meal-plans/draft", json={"client_id": "c", "diet_type": "Balanced", "recipe_ids": ["r"]}, headers=auth("doctor")).status_code == 409


def test_care_is_bound_to_selected_completed_appointment():
    visit("first", status="COMPLETED", days=-3)
    visit("second", status="COMPLETED", days=-1)
    goal = api.post("/api/v1/goals", json={"client_id": "c", "appointment_id": "first", "target_metric": "Water", "target_value": 2000}, headers=auth("doctor"))
    assert goal.status_code == 200
    assert goal.json()["goal"]["appointment_id"] == "first"
    rec = api.post("/api/v1/clients/c/care/recommendations", json={"appointment_id": "first", "content": "Reviewed guidance"}, headers=auth("doctor"))
    assert rec.json()["payload"]["appointment_id"] == "first"
    # Omitted ID is bound explicitly to the latest completed consultation for compatibility.
    latest = api.post("/api/v1/goals", json={"client_id": "c", "target_metric": "Steps", "target_value": 1000}, headers=auth("doctor"))
    assert latest.json()["goal"]["appointment_id"] == "second"
    visit("wrong", status="COMPLETED", client="someone-else")
    bad = api.post("/api/v1/goals", json={"client_id": "c", "appointment_id": "wrong", "target_metric": "Water", "target_value": 2000}, headers=auth("doctor"))
    assert bad.status_code == 409


def test_meal_plan_draft_and_approval_retain_consultation_link():
    visit(status="COMPLETED")
    state.recipes_db["r"] = {"recipe_id": "r", "title": "Rice meal", "ingredients": ["rice"], "instructions": "Cook rice"}
    saved = api.post("/api/v1/meal-plans/drafts", json={"client_id": "c", "appointment_id": "a", "diet_type": "Balanced", "recipe_ids": ["r"], "allergies": [], "conditions": [], "life_stage": "adult"}, headers=auth("doctor"))
    assert saved.status_code == 201
    plan_id = saved.json()["plan_id"]
    assert meals._draft_store[plan_id]["draft_json"]["appointment_id"] == "a"
    assert api.post(f"/api/v1/meal-plans/drafts/{plan_id}/decision", json={"decision": "APPROVED", "review_note": "Reviewed"}, headers=auth("doctor")).status_code == 200
    published = api.get("/api/v1/meal-plans/approved", headers=auth("patient")).json()
    assert published[0]["plan"]["appointment_id"] == "a"


def test_qr_is_bound_to_one_visit_and_cannot_fall_back_to_another():
    visit("first", days=1)
    visit("second", days=2)
    url = "/api/v1/clients/c/checkin-code"
    qr = api.post(url, json={"appointment_id": "first"}, headers=auth("patient"))
    assert qr.status_code == 200
    assert qr.json()["appointment_id"] == "first"
    state.appointments_db["first"]["status"] = "CANCELLED"
    body = {"checkin_code": qr.json()["checkin_code"]}
    assert api.post("/api/v1/check-in/scan", json=body, headers=auth("doctor")).status_code == 409
    assert not state.checkin_events_db
    qr = api.post(url, json={"appointment_id": "second"}, headers=auth("patient"))
    scan = api.post("/api/v1/check-in/scan", json={"checkin_code": qr.json()["checkin_code"]}, headers=auth("doctor"))
    assert scan.status_code == 201
    assert scan.json()["appointment_id"] == "second"
    assert state.checkin_events_db[0]["appointment_id"] == "second"
