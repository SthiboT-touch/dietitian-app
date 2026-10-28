# Phase 3 — Client meal-plan delivery

- Added authenticated `GET /api/v1/meal-plans/approved` endpoint.
- Client meal-plan page reads only approved or modified review records, never legacy unreviewed plans.
- Client bearer token is saved for the browser session and cleared on sign-out.
- **Development only:** existing in-memory client sessions do not expire or persist across backend restarts.
- **Not tested in Docker:** database migration 007 must be applied to the local test database before integration testing.
- Clinical safety and full end-to-end authorization tests remain pending.
- Do not deploy to production.
