"""Entry point: one FastAPI application that serves the web app and every API area.

Run with:  uvicorn app:app --app-dir back-end
"""
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
    }


# Same order as the original single file, so Swagger tags and route matching are unchanged.
for _router in (auth_admin.router, clients.router, appointments.router, meal_planning.router, ai.router):
    app.include_router(_router)
