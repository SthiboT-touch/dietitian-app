# Patient care workflow

Patients submit medical history and supporting documents, then request an
appointment by branch, dietitian, date/time, consultation type and appointment
format. Requests remain pending until the selected dietitian confirms them.

QR check-in is available for confirmed appointments today or on a future date.
Each short-lived, single-use code belongs to one appointment. Reception must
belong to that appointment's branch. Cancelled or rejected visits cannot use
their old codes.

Only the assigned dietitian records medical conditions and sets nutrition goals.
Once a confirmed consultation's scheduled time arrives, its dietitian can mark it
completed from the patient's care record. Goals, meal plans, recommendations and
progress reviews are then linked to a selected completed consultation.

Patients record progress and read their dietitian's recommendations, goals and
published meal plans. Dietitians approve measurements or request changes with
feedback. Decisions retain a snapshot: edited measurements return to pending
review while the original review remains in the history.

## Existing PostgreSQL installations

The deployment pipeline applies migrations 017 and 020 before restarting the
API. Migration 020 expects the check-in tables from migration 013, which the
deployment pipeline applies earlier. For a manual deployment, back up the
database, ensure migration 013 has run, then run:

```bash
docker compose build api
docker compose run --rm --no-deps api python migrations/apply_017_virtual_appointments.py
docker compose run --rm --no-deps api python migrations/apply_020_care_workflow.py
```

Run these commands from the server's project directory with the existing
database running and its normal server environment configured. Do not run an
in-memory configuration for these migrations. Both migrations are safe to
rerun, preserve existing records, and retain compatibility with manually
supplied meeting links.
Fresh databases include the same schema in `back-end/dietitainDB.sql`.

## Validation

```bash
python -m pytest -q back-end/tests
python qa/verify_care_browser.py
```

Backend tests use isolated in-memory records. Browser checks use synthetic API
responses in desktop and mobile Chrome sessions. Real PostgreSQL and deployment
checks must be verified separately; these commands do not modify production.
