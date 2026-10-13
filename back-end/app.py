"""Entry point: one FastAPI application that serves the web app and every API area.

Run with:  uvicorn app:app --app-dir back-end
"""
import os

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import database
from routers import ai, appointments, auth_admin, clients, meal_planning

app = FastAPI(
    title="Dietitian & Nutrition Management System",
    description="Full Implementation: Sections 1 through 6 REST API Specification",
    version="1.0.0",
    docs_url="/docs"  # Keeps Swagger UI at /docs
)

HEALTH_TIMEOUT_SECONDS = 3

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# Serve the web app at the root; API documentation remains available at /docs.
@app.get("/", include_in_schema=False)
def root_redirect():
    return FileResponse(config.STATIC_DIR / "index.html")


# Health check route that appears in Swagger UI under "Health Check"
@app.get("/health", tags=["Health Check"])
def read_root():
    database_status = "in_memory"
    if config.DATABASE_ENABLED:
        try:
            with database.cursor() as cursor:
                cursor.execute("SELECT 1")
            database_status = "online"
        except Exception:
            database_status = "offline"
    return {
        "status": "online",
        "message": "Dietitian API Service Running...",
        "database": database_status,
        "llm": _llm_status(),
        "langsmith": _langsmith_status(),
    }


def _llm_status() -> str:
    """online, model_missing (Ollama is up but the configured model is not pulled), or offline."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=HEALTH_TIMEOUT_SECONDS)
        response.raise_for_status()
        names = {item.get("name", "") for item in response.json().get("models", [])}
    except Exception:
        return "offline"
    return "online" if model in names or f"{model}:latest" in names else "model_missing"


def _langsmith_status() -> str:
    """disabled, not_configured, online, unauthorized (bad API key), or offline."""
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        return "disabled"
    api_key = os.getenv("LANGSMITH_API_KEY")
    if not api_key:
        return "not_configured"
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
    try:
        response = httpx.get(
            f"{endpoint}/api/v1/sessions",
            params={"limit": 1},
            headers={"x-api-key": api_key},
            timeout=HEALTH_TIMEOUT_SECONDS,
        )
    except Exception:
        return "offline"
    if response.status_code in (401, 403):
        return "unauthorized"
    return "online" if response.is_success else "offline"


# Same order as the original single file, so Swagger tags and route matching are unchanged.
for _router in (auth_admin.router, clients.router, appointments.router, meal_planning.router, ai.router):
    app.include_router(_router)
