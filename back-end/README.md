# Back End

The FastAPI service, database integration, request schemas, and service modules are maintained here. [`app.py`](app.py) creates the API and includes the route modules in [`routers/`](routers/README.md).

Database definitions and upgrades are in [`dietitainDB.sql`](dietitainDB.sql) and [`migrations/`](migrations/README.md). Backend tests are in [`tests/`](tests/README.md), and curated knowledge data is in [`knowledge/`](knowledge/README.md).

From the repository root, install development dependencies and run the API with:

```powershell
python -m pip install -r back-end/requirements-dev.txt
python -m uvicorn app:app --app-dir back-end --host 127.0.0.1 --port 8001
```

See the root README for environment configuration and full application setup.