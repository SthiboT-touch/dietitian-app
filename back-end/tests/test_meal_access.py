import sys
from pathlib import Path
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from state import users_db, meal_plans_db
from routers import meal_planning as mp


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    old_users, old_plans = dict(users_db), dict(meal_plans_db)
    users_db.clear()
    meal_plans_db.clear()
    mp._draft_store.clear()
    users_db["a"] = {"id": "c1", "type": "client", "dietitian_id": "d1"}
    users_db["b"] = {"id": "c2", "type": "client", "dietitian_id": "d2"}
    yield
    users_db.clear()
    users_db.update(old_users)
    meal_plans_db.clear()
    meal_plans_db.update(old_plans)
    mp._draft_store.clear()


def _draft(client="c1", dietitian="d1"):
    pid = "p" + client
    mp._draft_store[pid] = dict(
        plan_id=pid,
        client_id=client,
        dietitian_id=dietitian,
        status="PENDING_REVIEW",
        draft_json={"days": 1, "schedule": [{"day": 1, "candidate_recipe": {"recipe_id": "r1"}}]},
        approved_json=None,
        review_note=None,
        reviewed_at=None,
    )
    return pid


def test_pending_and_rejected_are_hidden():
    pid = _draft()
    assert mp.list_client_approved_meal_plans("c1") == []
    with pytest.raises(HTTPException) as e:
        mp.client_approved_meal_plan(pid, "c1")
    assert e.value.status_code == 404
    mp.review_meal_draft(
        pid, mp.DraftDecisionRequest(decision="REJECTED", review_note="Not appropriate"), "d1"
    )
    assert mp.list_client_approved_meal_plans("c1") == []


def test_approved_only_for_owner_and_not_twice():
    pid = _draft()
    mp.review_meal_draft(
        pid, mp.DraftDecisionRequest(decision="APPROVED", review_note="Reviewed"), "d1"
    )
    assert len(mp.list_client_approved_meal_plans("c1")) == 1
    assert mp.list_client_approved_meal_plans("c2") == []
    with pytest.raises(HTTPException) as e:
        mp.client_approved_meal_plan(pid, "c2")
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        mp.review_meal_draft(
            pid, mp.DraftDecisionRequest(decision="APPROVED", review_note="Again"), "d1"
        )
    assert e.value.status_code == 409


def test_modified_plan_delivers_revision():
    pid = _draft()
    revised = [{"day": 1, "candidate_recipe": {"recipe_id": "r2"}}]
    mp.review_meal_draft(
        pid,
        mp.DraftDecisionRequest(
            decision="MODIFIED", revised_schedule=revised, review_note="Changed"
        ),
        "d1",
    )
    assert mp.client_approved_meal_plan(pid, "c1")["plan"]["schedule"] == revised


def test_other_dietitian_cannot_review():
    pid = _draft()
    with pytest.raises(HTTPException) as e:
        mp.review_meal_draft(
            pid, mp.DraftDecisionRequest(decision="APPROVED", review_note="Wrong owner"), "d2"
        )
    assert e.value.status_code == 403


def test_legacy_endpoints_scope_to_dietitian():
    meal_plans_db["m1"] = {
        "meal_plan_id": "m1",
        "client_id": "c1",
        "diet_type": "standard",
        "days": 1,
        "meals": [],
        "status": "GENERATED",
    }
    meal_plans_db["m2"] = {
        "meal_plan_id": "m2",
        "client_id": "c2",
        "diet_type": "standard",
        "days": 1,
        "meals": [],
        "status": "GENERATED",
    }
    assert [x["meal_plan_id"] for x in mp.list_meal_plans("d1")] == ["m1"]
    with pytest.raises(HTTPException) as e:
        mp.get_meal_plan("m2", "d1")
    assert e.value.status_code == 403
