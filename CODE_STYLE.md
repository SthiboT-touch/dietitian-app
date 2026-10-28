# NutriCare code style and debugging guide

The app favors straightforward code over clever shortcuts. Names should say what a function does; comments should explain *why* behavior exists, especially around clinical review and security.

## Working with the backend

- API entry point: `back-end/app.py`.
- Database connection helper: `back-end/database.py` (`connection_options`, `open_connection`, and the `cursor` context manager).
- AI workflows: `back-end/routers/ai.py`.
- Foods and meal plans: `back-end/routers/meal_planning.py`.
- Configuration: `back-end/config.py`, Docker Compose, and an untracked local `.env`.

Use consistent function and variable names, narrow error handling, and parameterized SQL. Avoid printing credentials, health records, and patient prompts into logs. Add tests before changing routes or stored-data formats.

## What the health endpoint means

The `/health` response reports the API process independently from the database status. `database: offline` means the API is running but its database check failed. `database: in_memory` means local mock-data mode is active. Neither status means that patient workflows are ready for production.

## Safe local debugging

From the VS Code PowerShell terminal, run these commands one at a time:

```powershell
docker compose config --quiet
docker compose ps
docker compose logs --tail=60 api
```

See `LOCAL_TESTING.md` for the database and AI checks. Do not commit `.env`, push local in-memory settings, reset passwords, remove database volumes, or deploy without reviewing the GitHub Actions workflow.

## Scope of this readability pass

The readability updates focus on the API entry point, shared PostgreSQL connection helper, and AI/meal-plan module documentation. They intentionally leave public routes, data models, database migrations, and the UI behavior unchanged. **The complete application is not certified production-ready by this pass.**
