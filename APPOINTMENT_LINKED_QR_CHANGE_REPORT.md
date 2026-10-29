# NutriCare — Appointment-Linked QR Check-In
**Baseline:** NutriCare Patient Navigation with My Meal Plan restored  
**Scope:** Patient UI and protected check-in API, only  
**Deployment:** Local files only; production Oracle Cloud, passwords and existing PostgreSQL data were not touched.

## Requested behavior
The Patient QR Check-In must not be available before an appointment exists. To prevent check-in for an unaccepted booking request, the check-in button appears only on **confirmed, upcoming** appointments (the existing workflow is PENDING → CONFIRMED when the dietitian approves). No standalone QR shortcut appears in the patient account menu or Settings.

### Actual flow
1. Patient creates a booking request in **Appointments**. Status is **PENDING**, with no QR button.
2. The dietitian approves the booking. Status becomes **CONFIRMED**.
3. The patient's **Appointments → Upcoming** card displays **Check-in QR**.
4. The patient selects the confirmed appointment and generates a short-lived QR credential.
5. At the appointment's branch, reception scans the QR; the backend checks patient ownership, appointment ID/status/date, branch assignment, expiry and single use.
6. Cancelled, past, rejected, unconfirmed or previously checked-in appointments cannot generate/use a QR.

## Code changed
| File | Change |
|---|---|
| `front-end/app.js` | Confirmed-appointment QR button; eligibility-aware check-in page; removed generic Settings/dashboard QR shortcuts; QR POST now includes appointment ID |
| `front-end/index.html` | Removed legacy/hidden standalone QR nav entry and account-menu QR link |
| `front-end/styles.css` | Compact responsive appointment action layout |
| `back-end/routers/onboarding.py` | Added authenticated eligible-appointments GET, confirmed-appointment-only QR POST, and appointment/branch validation in reception scanner |
| `back-end/dietitainDB.sql` | Added appointment links in fresh database's QR credential/event tables |
| `back-end/migrations/017_appointment_bound_checkin.sql` | Adds nullable appointment links to existing records, unique check-in per appointment, and invalidates pre-update unattached credentials |
| `back-end/migrations/apply_017_appointment_bound_checkin.py` | Local-only migration launcher |
| `qa/verify_appointment_bound_checkin.py` | Isolated API test for booking, confirmed status, ownership, branch, cancellation, replay, already checked-in, past bookings |
| `qa/verify_appointment_qr_browser.py` | Offline desktop and mobile browser tests with mocked API |
| `qa/verify_fr14_fr110.py` | Updated prior FR-1.7 regression test for appointment-linked codes |
| `qa/verify_patient_navigation_browser.py` | Updated navigation checks for removed standalone shortcut |

## API contract
- `GET /api/v1/clients/{client_id}/checkin-appointments` returns only the signed-in patient's confirmed upcoming appointments.
- `POST /api/v1/clients/{client_id}/checkin-code` requires JSON `{"appointment_id":"..."}` and returns the QR SVG and short-lived code.
- `POST /api/v1/reception/check-in` keeps the old QR scan payload, but now validates the linked appointment, reception branch and single-use status.
- A pending or cancelled appointment returns HTTP 409 on QR generation. An unauthorized patient returns HTTP 403, missing authentication 401. The frontend never relies on hiding buttons for security.

## Local installation (Windows / PowerShell)
1. **Back up your current working project.** Use the provided complete ZIP in a separate local directory, or apply the changes-only patch to a copy. Keep your existing local `.env` in your copied project; it is intentionally not in these ZIPs.
2. Ensure the existing local PostgreSQL database has migration **013** (client QR) already applied. Then run the new migration **017** once, after the API image has been rebuilt:

```powershell
docker compose build api
docker compose up -d --no-deps api
docker compose exec api python migrations/apply_017_appointment_bound_checkin.py
```

3. The `front-end` folder is bind-mounted into Nginx. Refresh the browser with `Ctrl+F5` after updating it. **Do not recreate or delete Docker volumes**.
4. Sign in as a fictional test patient with no appointments: no QR should be offered. Create a booking request: it should remain **PENDING** without QR.
5. Approve the test booking using the assigned dietitian login. Return to the patient's **Appointments → Upcoming** page; use **Check-in QR** and confirm it appears.
6. With reception staff assigned to the appointment's branch, scan the QR. Check-in should succeed only once. Re-checking or attempting to check in at another branch must fail.

**Important:** Previously issued pre-update QR codes are invalidated by migration 017; historic check-in events remain in place. This migration alters two local QR tables and creates an index. It does *not* change administrator credentials or clinical record tables. No migrations have been run against your databases in this environment.

## Tests performed in the review environment
- Isolated FastAPI in-memory appointment/QR workflow: **passed**.
- Earlier registration/QR/assisted onboarding acceptance checks: **passed**, after updating the QR prerequisites.
- Desktop and mobile Chromium tests: **passed** (pending hidden, confirmed QR offered, cancelled QR unavailable).
- Existing Patient navigation desktop/mobile regression and dietitian navigation: **passed**.
- Existing read-only patient goals/approved meal plans frontend checks: **passed**.
- Python syntax compilation and JavaScript syntax: **passed**.
- Real Docker + PostgreSQL migration, actual browser calling real API, reception physical scanner: **not run here**, require local verification.

## Scope and safeguards
No existing API paths were renamed. The original appointment approval flow remains unchanged. Dietitian-managed Goals and Meal Plans remain intact. The ZIP excludes environment credentials, Git history, cached files and database backups. No production deployment is performed.
