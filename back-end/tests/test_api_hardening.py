"""Isolated regression tests for food/recipe API safety and compatibility.

Run against the local FastAPI router and in-memory data only. No real DB or AI.
"""

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Allows this focused test to run in lightweight environments; the real
# application continues to import psycopg2 through database.py normally.
try:
    import database  # noqa: F401
except ImportError:
    sys.modules["database"] = types.ModuleType("database")

import config
import state
from audit import audit_sensitive_requests
from routers.food_recipes import router as catalogue_router

API = FastAPI()
API.middleware("http")(audit_sensitive_requests)
API.include_router(catalogue_router)
client = TestClient(API)

RECIPE = {"title": "Oat bowl", "ingredients": ["oats", "fruit"], "instructions": "Mix and serve"}
FOOD = {"name": "Sample oats", "calories": 75, "protein_g": 2.0, "carbs_g": 15.0, "fat_g": 1.0}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    original_foods = list(state.foods_db)
    monkeypatch.setattr(config, "DATABASE_ENABLED", False)
    for store in (
        state.recipes_db,
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.staff_sessions_db,
        state.staff_accounts_db,
    ):
        store.clear()
    state.foods_db.clear()
    state.access_audit_events_db.clear()
    state.admin_sessions_db["admin-token"] = "admin-1"
    state.dietitian_sessions_db["diet-token"] = "diet-1"
    state.client_sessions_db["client-token"] = "client-1"
    yield
    for store in (
        state.recipes_db,
        state.admin_sessions_db,
        state.dietitian_sessions_db,
        state.client_sessions_db,
        state.staff_sessions_db,
        state.staff_accounts_db,
    ):
        store.clear()
    state.foods_db[:] = original_foods
    state.access_audit_events_db.clear()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_recipe_creation_requires_a_dietitian():
    assert client.post("/api/v1/recipes", json=RECIPE).status_code == 401
    assert (
        client.post("/api/v1/recipes", json=RECIPE, headers=auth("not-a-token")).status_code == 401
    )
    assert (
        client.post("/api/v1/recipes", json=RECIPE, headers=auth("client-token")).status_code == 401
    )
    assert (
        client.post("/api/v1/recipes", json=RECIPE, headers=auth("admin-token")).status_code == 401
    )
    assert not state.recipes_db
    response = client.post("/api/v1/recipes", json=RECIPE, headers=auth("diet-token"))
    assert response.status_code == 200, response.text  # preserve existing client contract
    assert response.json()["details"] == RECIPE
    saved = client.get("/api/v1/recipes")
    assert saved.status_code == 200 and saved.json()[0]["recipe_id"] == response.json()["recipe_id"]


def test_readonly_catalogue_and_admin_food_creation_still_work():
    assert client.get("/api/v1/recipes").status_code == 200
    assert client.get("/api/v1/foods").status_code == 200
    assert client.post("/api/v1/foods", json=FOOD).status_code == 401
    assert client.post("/api/v1/foods", json=FOOD, headers=auth("diet-token")).status_code == 401
    result = client.post("/api/v1/foods", json=FOOD, headers=auth("admin-token"))
    assert result.status_code == 201, result.text
    assert result.json()["name"] == "Sample oats"


def test_recipe_and_food_writes_are_audited_without_bearer_tokens():
    client.post("/api/v1/recipes", json=RECIPE)
    client.post("/api/v1/recipes", json=RECIPE, headers=auth("diet-token"))
    client.post("/api/v1/foods", json=FOOD, headers=auth("admin-token"))
    events = state.access_audit_events_db
    assert [
        (event["http_method"], event["resource_path"], event["status_code"]) for event in events
    ] == [
        ("POST", "/api/v1/recipes", 401),
        ("POST", "/api/v1/recipes", 200),
        ("POST", "/api/v1/foods", 201),
    ]
    assert not any("diet-token" in str(event) or "admin-token" in str(event) for event in events)
    before = len(events)
    client.get("/api/v1/recipes")
    client.get("/api/v1/foods")
    assert len(events) == before


def test_route_paths_and_documented_response_models():
    schema = API.openapi()
    paths = schema["paths"]
    for method, path in (
        ("POST", "/api/v1/recipes"),
        ("GET", "/api/v1/recipes"),
        ("POST", "/api/v1/foods"),
        ("GET", "/api/v1/foods"),
    ):
        assert path in paths and method.lower() in paths[path]
    assert schema["paths"]["/api/v1/recipes"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["paths"]["/api/v1/recipes"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
