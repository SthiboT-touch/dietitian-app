# NutriCare — Patient Care Journey Workflow

Updated: 29 October 2026. Based on the provided handwritten workflow.

## What is included

**Patient dashboard:** Six connected stages: (1) Review medical history → (2) Book in-person or virtual appointment → (3) Attend consultation → (4) View dietitian-approved meal plans and goals → (5) Record progress → (6) View the clinician's follow-up review and monitoring plan.

**Patient navigation:** Dashboard → Appointments → Progress → Goals → AI Coach → Settings. Approved meal plans are still available on Dashboard, in Settings, and through My Profile. The patient cannot alter dietitian-approved plans.

The stages summarize **real stored data**; they do not assume a consultation was attended just because the appointment was confirmed. Healthy patients are not required to invent diagnoses or allergies to book.

**Appointments:** Existing in-person QR check-in and virtual meeting features remain unchanged. The booking screen reminds patients to review their medical history before visiting.

**Dietitian:** Under **My Patients → Follow-up review / Review progress**, the assigned dietitian can view a patient's records and, after the scheduled time of a confirmed appointment, record a care review, clinical next action and monitoring plan. Patients cannot create clinical review records.

**Progress:** Patients can continue recording progress and meals. Their latest clinician review appears at the top of their Progress page and on the Dashboard. Dietitian-set goals and approved meal plans remain read-only for patients.

**Important:** Saving a clinical review does not change a prescribed goal or publish a meal plan. Those must go through the existing dietitian-only workflows. This change does not add telehealth attendance verification, clinician signature, clinical compliance certification, or video-provider authorization.

## New API

- `GET /api/v1/care-reviews?client_id=<client_id>` — patient (own record) or assigned dietitian (authorized client) can view follow-up reviews.
- `POST /api/v1/care-reviews` — assigned dietitian only, using a confirmed appointment whose scheduled time has passed. Requires `client_id`, `appointment_id`, `review_summary`, `monitoring_plan`; accepts `decision` (FOLLOW_UP, CONTINUE_PLAN, ADJUST_PLAN) and optional `next_review_date`.

## In-memory local testing (no migration)

Open PowerShell from the extracted `dietitian-app` directory:

```powershell
docker compose -f docker-compose.memory.yml up --build -d
```

Visit http://127.0.0.1:8088 and use fictional accounts. Patient dashboard shows the six stages. For a dietitian follow-up review, the appointment must be **confirmed and its scheduled start time must have passed**. A future confirmed appointment cannot be marked reviewed early. The local memory store resets when the API container stops.

Stop with:

```powershell
docker compose -f docker-compose.memory.yml down
```

## Local PostgreSQL (not Oracle Cloud)

The additive `019_care_reviews.sql` migration adds the `care_review` table without modifying existing patient or appointment records. After confirming previous migrations are applied, use your **local development** database only:

```powershell
docker compose exec api python migrations/apply_019_care_reviews.py
```

Do not apply migrations to production or push to `main` until a separate release review and rollback plan are approved. No production credentials or files are included in this ZIP.

## Verification performed

- Care review API: 14 tests passed in isolated in-memory FastAPI test harness (authentication, authorization, appointment ownership, statuses, past vs future, validation, read-back).
- Care journey browser: desktop 1440px and mobile 390px passed (patient status/links, clinician review submission and patient monitoring view) with mocked API.
- Existing virtual appointment, appointment QR, patient navigation, registration, and clinician-goal browser/API regressions passed.
- Python compilation and JavaScript syntax checks passed.
- **Not verified:** real Docker startup, real PostgreSQL migration, actual clinical video call, production deployment.
