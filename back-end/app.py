"""NutriCare API entry point.

Run locally with ``uvicorn app:app --app-dir back-end`` or through Docker.
"""

import os
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import config
import database
from routers import (
    ai,
    appointments,
    auth_admin,
    clients,
    meal_planning,
    food_recipes,
    staff,
    access_audit,
    onboarding,
    cms,
    support,
)
from audit import audit_sensitive_requests
from diagnostics import request_diagnostics

# Documentation is opt-in and disabled by default. Enable only in a private
# local development environment; never expose the setting on a public server.
API_DOCS_ENABLED = os.getenv("NUTRICARE_ENABLE_API_DOCS", "0") == "1"

app = FastAPI(
    title="NutriCare — Dietitian & Nutrition Management API",
    description="Nutrition management, appointments, meal planning, and AI support.",
    version="1.0.0",
    docs_url="/api/docs" if API_DOCS_ENABLED else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if API_DOCS_ENABLED else None,
)

# The diagnostics layer is outermost: it also adds a request ID to audit and
# route errors while preserving existing response JSON for expected failures.
app.middleware("http")(audit_sensitive_requests)
app.middleware("http")(request_diagnostics)


@app.middleware("http")
async def redirect_old_frontend_pages(request, call_next):
    """Keep saved links working after moving all screens into index.html."""
    path = request.url.path.removeprefix("/static")
    if path.startswith("/traditional/") and path.endswith(".html"):
        page = path.rsplit("/", 1)[1].removesuffix(".html")
        destination = "/#traditional/" + page
        if request.url.query:
            destination += "?" + request.url.query
        return RedirectResponse(destination, status_code=302)
    if path.startswith("/student/") and path.endswith(".html"):
        page = path.rsplit("/", 1)[1].removesuffix(".html")
        if page == "index":
            page = "login"
        return RedirectResponse("/#student/" + page, status_code=302)
    return await call_next(request)


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# Serve the web app at the root. API documentation is opt-in, disabled by default.
@app.get("/", include_in_schema=False)
def root_redirect():
    return FileResponse(config.STATIC_DIR / "index.html")


# A readable health summary for local debugging. An online API does not
# necessarily mean that its database connection is healthy.
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
        "status": "degraded" if database_status == "offline" else "online",
        "message": "NutriCare API is running",
        "database": database_status,
    }


# Keep the existing router order to preserve current endpoint behavior.
for _router in (
    auth_admin.router,
    clients.router,
    appointments.router,
    meal_planning.router,
    food_recipes.router,
    ai.router,
    staff.router,
    access_audit.router,
    onboarding.router,
    cms.router,
    support.router,
):
    app.include_router(_router)
