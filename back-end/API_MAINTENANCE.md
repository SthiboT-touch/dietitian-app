# NutriCare API: maintenance notes

## Scope of this safety-focused refactor

- `routers/food_recipes.py` owns food and recipe routes. `routers/meal_planning.py` remains responsible for meal-plan workflows. The existing `/api/v1/...` URLs and existing request/response JSON formats are preserved.
- `POST /api/v1/recipes` requires a signed-in dietitian. Unauthorized calls return HTTP 401. Clients, receptionists, and other roles cannot create recipes using this route. Public `GET /api/v1/recipes` remains read-only; `POST /api/v1/foods` remains admin-only.
- Audit middleware now captures recipe/food write attempts and reception operations. Event recording remains *best-effort*, not a complete POPIA audit solution.
- FastAPI documentation stays **disabled by default**. To enable local Swagger documentation, set `NUTRICARE_ENABLE_API_DOCS=1` **only in an isolated local developer environment** and restart the API. Swagger: `/api/docs`; OpenAPI: `/api/openapi.json`. Do not set this variable on public Oracle Cloud production. Turn it off when finished testing.

## Verification

From the project root in a local environment with required dependencies:

```powershell
python -m pytest -q back-end/tests/test_api_hardening.py back-end/tests/test_meal_access.py
python qa/verify_fr14_fr110.py
```

Do not run against production. No new database tables or migrations are required for this refactor.

## Still to do

- Convert remaining routers gradually to smaller, testable modules.
- Add response contracts to other routes after integration tests establish their existing response shapes.
- Migrate in-memory bearer sessions to expiring durable sessions in a dedicated, reviewed security milestone.
- Complete audit retention, integrity and error-handling guarantees.
