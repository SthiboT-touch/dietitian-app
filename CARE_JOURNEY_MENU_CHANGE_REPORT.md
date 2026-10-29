# NutriCare — Patient Care Journey and Navigation

Date: 29 October 2026

## Baseline and scope
Based on the appointment/virtual-consultation local-memory application and the new six-stage patient care journey. The final patient sidebar follows the requested order:

1. Dashboard
2. Appointments
3. Progress
4. Goals
5. AI Coach
6. Settings

**My Meal Plan is not deleted.** It remains reachable from the Dashboard's care journey and quick links, the new Patient Settings page, and the top-right avatar's My Profile page. Patients can see only dietitian-approved plans. Clinical goals and reviews remain clinician-controlled.

## Care journey features
- Six-stage dashboard: medical history, appointment booking, consultation, dietitian-approved meal plan and goals, progress, dietitian follow-up and monitoring.
- Dietitian follow-up review after a confirmed appointment's scheduled time, with clinical summary, next action and monitoring instructions.
- Patient sees follow-up monitoring instructions read-only on the Progress and dashboard views.
- Both contact/in-person appointments and virtual consultations remain supported; existing appointment QR check-in continues for confirmed in-person appointments only.

## Technical changes for this request
- `front-end/index.html`: remove only the **sidebar** entry for My Meal Plan and add Settings (patient-only).
- `front-end/vibrant-theme.css`: enforce requested six-menu visual order.
- `front-end/app.js`: create a functional Settings hub with links to Profile, conditions, allergies, approved Meal Plan, recommendations and support; keep existing account dropdown and other clinical routes.
- `qa/verify_patient_navigation_browser.py`: adapt tests to the new six-menu structure.
- `CARE_WORKFLOW_README.md`: document the final sidebar and preserved meal-plan entry points.

## Verification run here
- Patient sidebar + profile + care navigation, desktop and mobile: passed.
- Dietitian navigation regression: passed.
- Patient care journey, clinician review and monitoring browser test, desktop and mobile: passed.
- Care journey API: 14 tests passed.
- Virtual/in-person booking and meeting-link API tests: passed.
- Appointment-linked QR authorization regressions: passed.
- Python/JavaScript syntax: passed.

## Still pending
- Local Docker/database integration with the user's configuration.
- Real PostgreSQL migration 019 in a development database, if not using in-memory mode.
- Real approved clinical video provider integration and deployment review.

No live Oracle Cloud deployment, credentials or database was changed. The ZIP omits `.env`, Git history, and secrets. Keep existing private local configuration when testing separately. The local-memory launch command from inside the unzipped `dietitian-app` directory is:

```powershell
docker compose -f docker-compose.memory.yml up --build -d
```

Open `http://127.0.0.1:8088` for local testing.
