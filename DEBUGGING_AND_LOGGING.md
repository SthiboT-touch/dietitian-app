# NutriCare — Local Debugging and Request Diagnostics

This guide applies to the **API diagnostics and frontend reliability update** (28 October 2026). It is intended for the team's **local development environment**. Do **not** execute deployment commands on the Oracle Cloud server or push directly to `main`.

## What changed

- Every HTTP response from FastAPI includes `X-Request-ID` with a new opaque identifier.
- The `nutricare.api` logger writes one structured JSON line for API requests, with **request ID, HTTP method, route template, status code and duration**.
- An unexpected exception returns a safe HTTP 500 response: `{"detail":"An unexpected server error occurred. Please try again.","request_id":"..."}`.
- Expected 401/403/404/409/422 errors retain their **existing response bodies** and also carry the request ID in the header.
- Logs do **not** contain raw request URLs, query strings, body content, passwords, bearer tokens, patient IDs extracted from paths, or exception messages. Exceptions are recorded by **type only**.
- Sensitive API failures (including unexpected HTTP 500s) are added to the existing access-audit trail on a best-effort basis.
- The client shows the request ID next to **server errors (5xx)** and a clearer message for network failures.
- The sidebar health indicator reflects `/health` rather than displaying "Workspace connected" unconditionally.
- Nginx has a sanitized access log format; Uvicorn's raw-URL access log is disabled in the API container.

**Caution:** Other third-party processes and existing libraries can have their own log behavior. This change is not a guarantee that every log from every dependency is free of sensitive data. The access-audit database itself intentionally records a resource path, which may contain a patient identifier; restrict access to it.

## Local verification

1. Use a **separate local copy** of the project and your existing local environment settings. Never replace the production `.env` or volumes.
2. From the copied project root, run:

```powershell
docker compose build api
docker compose up -d --no-deps api
docker compose ps
docker compose logs --tail=60 api
```

3. Visit `http://localhost/health`. If PostgreSQL is healthy, you should see `"database":"online"`. If it is unavailable, the response has `"status":"degraded"` and `"database":"offline"`.
4. Log in to the local app with a **test account**. Confirm the sidebar reads **Workspace connected**. If the database fails, it should read **Database unavailable** when the health check runs.
5. Test a known authorized and unauthorized request. The response headers should include `X-Request-ID`. On unexpected HTTP 500 failures, the UI will show **Reference: {request ID}**. Copy the ID and search for it in the API logs; do not share credentials or health records in bug reports.
6. Confirm registrations, dietitian approvals, client records, appointments, AI Coach and recipes still work. Test at desktop and phone widths.

### Tests

Install project dependencies in your **local** test environment, then:

```powershell
python -m pytest -q back-end/tests/test_diagnostics.py back-end/tests/test_api_hardening.py back-end/tests/test_clinical_screening.py back-end/tests/test_meal_access.py
node qa/verify_diagnostics_frontend.cjs
```

Run the full suite separately once LangChain, Ollama and PostgreSQL dependencies are available. No database migrations are introduced in this update.

### Example server log

```json
{"timestamp":"2026-10-28T08:00:00+00:00","level":"ERROR","event":"http_request","request_id":"f8a7f73d2bcf4e4490854ef23056d771","method":"GET","route":"/api/v1/clients/{client_id}/profile","status":500,"elapsed_ms":13.6,"error_type":"OperationalError"}
```

This is an **illustrative** log record. It is not evidence of a real production incident. No clinical or user data belongs in diagnostic reports.

### Team workflow

- Start development on a feature branch. Open a PR into the development branch for review.
- Keep `.env`, database dumps, admin credentials, and real client records out of commits and shared ZIP files.
- For failures, collect only: time, route template, status, request ID, steps to reproduce with **synthetic data**, and the smallest relevant test output.
- Do not use `docker compose down -v`, reset the database, or apply production migrations as part of debugging.
- `NUTRICARE_LOG_LEVEL` may be set to `WARNING`, `INFO` (default) or `ERROR` on the local API process. The diagnostics logger is intentionally isolated from third-party logging.
- Optional Swagger docs remain disabled by default and should only be enabled in a private local development environment using `NUTRICARE_ENABLE_API_DOCS=1`.

## Still outstanding

- Expiring, durable login sessions and staff MFA.
- Consistent response schemas and finer-grained service-layer splits across the large legacy routers.
- Transactional, tamper-resistant audit logging and retention management.
- End-to-end tests against your real local PostgreSQL/Ollama containers.
- Production observability and alerting configuration, subject to stakeholder approval.
