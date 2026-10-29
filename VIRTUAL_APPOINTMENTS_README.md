# NutriCare: In-person and Virtual Appointments

## What changed

Patient appointment booking now offers two types:

- **In-person consultation** (`IN_PERSON`): existing booking and reception QR workflow.
- **Virtual consultation** (`VIRTUAL`): video meeting link for the patient and selected dietitian **after confirmation**.

The date and dietitian fields, existing booking endpoint, approval/rejection/cancellation flow, and Patient sidebar remain in place. The dietitian Appointment Requests view includes visit type and a separate list of confirmed upcoming appointments so the clinician can join virtual consultations.

## How virtual meetings work

1. Patient signs in, visits **Appointments → Book Appointment**, selects a dietitian/date, and chooses **Virtual consultation**.
2. Booking is `PENDING`. No room link is available yet.
3. Dietitian signs in, opens **Appointment Requests**, and approves the request.
4. NutriCare generates an unpredictable room ID. Only the appointment patient and dietitian can retrieve the link through `GET /api/v1/appointments/{appointment_id}/meeting` after confirmation.
5. Either person presses **Join virtual meeting**, then **Open video room**. The external video provider opens in a separate tab.
6. In-person bookings continue to use appointment-linked QR check-in; virtual bookings are ineligible for reception QR check-in.

The UI keeps confirmed virtual consultations in the upcoming section for up to 90 minutes after the scheduled start, so the Join button does not disappear the moment the meeting begins.

## Test locally with temporary memory (no PostgreSQL)

Open a terminal in the extracted `dietitian-app` folder:

```powershell
docker compose -f docker-compose.memory.yml up --build -d
```

Visit `http://127.0.0.1:8088`. The health check should report `database: "in_memory"`:

```powershell
Invoke-RestMethod http://127.0.0.1:8088/health
```

Create **fictional** test patient and dietitian accounts, complete any required test approval of the dietitian, then book and confirm a virtual consultation. Sign in as both parties (in separate browser sessions if needed) and follow the Join links. The temporary-memory Compose file includes `NUTRICARE_MEETING_BASE_URL=https://meet.jit.si` **only for demos**. The actual video service requires internet connectivity; the app's local API/UI still work without it. The room link is not usable until the external provider is reachable.

Stop the local memory test with:

```powershell
docker compose -f docker-compose.memory.yml down
```

Memory data is erased on API shutdown. This Compose configuration does not connect to your existing PostgreSQL volume and does not deploy anything to Oracle Cloud.

## Running with local PostgreSQL instead

The new optional columns must be added to the LOCAL database before running this updated backend:

```powershell
docker compose exec api python migrations/apply_018_virtual_appointments.py
```

Migration `018_virtual_appointments.sql` only adds `consultation_type` (defaulting old bookings to `IN_PERSON`) and `virtual_room_id`. It does not reset passwords, accounts, or data. Existing migrations through 017 must have been applied first where relevant. Never run this against Oracle Cloud without a separate production change approval.

## External video provider and privacy

`NUTRICARE_MEETING_BASE_URL` must be an approved **HTTPS** meeting-service base URL. This setting is deliberately **absent** from normal/production Compose: link retrieval returns HTTP 503 until your organization configures an approved provider. The `meet.jit.si` default is provided ONLY in `docker-compose.memory.yml` for fictional testing.

**Important:** A randomly generated meeting URL is not participant authentication at the video provider. Someone who obtains the room URL might be able to enter. A public demo service is **not** an approved confidential healthcare system. Do not use it for real patient consultations or transmit medical information until the provider's identity verification, waiting-room controls, data processing, consent, security and POPIA obligations have been reviewed. No recording, calendar integration, provider-hosted access control, real-time availability check, or automated meeting reminders were implemented in this milestone.

Cancelling an appointment blocks meeting URL retrieval from NutriCare, but it cannot revoke a room URL already copied to an external service. Production requires provider-side room access and revocation controls.

## APIs and database

- `POST /api/v1/appointments`: existing endpoint; accepts optional `consultation_type` (`IN_PERSON` or `VIRTUAL`), default `IN_PERSON` for backward compatibility.
- `GET /api/v1/appointments`: returns `consultation_type`, but **never** returns `virtual_room_id`.
- `PATCH /api/v1/appointments/{appointment_id}`: dietitian approval creates the room ID for a `VIRTUAL` booking.
- `GET /api/v1/appointments/{appointment_id}/meeting`: bearer token required; confirms exact patient/dietitian participant and appointment status, then returns configured HTTPS meeting URL with `Cache-Control: private, no-store`.
- `GET /api/v1/clients/{client_id}/checkin-appointments`, QR issuance and reception check-in: restricted to `IN_PERSON` appointments.
- `appointment.consultation_type`: `VARCHAR(12)` with check constraint.
- `appointment.virtual_room_id`: nullable `VARCHAR(96)`; never included in normal appointment listing.

## Checks performed in this review environment

- `qa/verify_virtual_appointments_api.py`: passed (isolated FastAPI, simulated sessions, no real DB/video requests).
- `qa/verify_virtual_appointments_browser.py`: passed on desktop and mobile with mocked API.
- `qa/verify_appointment_bound_checkin.py`: passed (previous in-person QR behavior).
- `qa/verify_appointment_qr_browser.py`: passed on desktop and mobile (previous QR browser flows).
- Python compilation and JavaScript syntax checks: passed.

**Not verified here:** actual Docker startup (Docker unavailable), PostgreSQL migration, clinician identity configuration, and a real live video call between two browsers/people. Verify these locally with fictional test accounts before accepting this for real use.
