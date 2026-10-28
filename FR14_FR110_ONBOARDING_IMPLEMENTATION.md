# NutriCare — Module 1, FR-1.4 through FR-1.10

**Baseline:** FR-1.3 ZIP, based on `dietitian-app(7).zip`.
**Scope:** Local/staging-only development. This file documents actual code changes, not production deployment or legal compliance certification.

## Implementation, one requirement at a time

| BRS ID | Functionality implemented | Main code and storage | Verification |
| --- | --- | --- | --- |
| FR-1.4 | Automatic centralized patient record with full UUID and original client/dietitian linkage | `routers/auth_admin.py::_create_client`, `client` | API registration/login/profile lookup passed in isolated tests |
| FR-1.5 | Transactional welcome-email outbox and retryable SMTP delivery worker | `registration_welcome_outbox`, `welcome_worker.py`, `onboarding_services.py` | Queue tests and mocked send/retry passed; **real mail delivery not verified** |
| FR-1.6 | Optional JPEG/PNG portrait and PDF/JPEG/PNG initial document in patient signup; file type and limits checked by backend; protected photo retrieval | `client_profile_photo`, existing `client_medical_document`, `routers/onboarding.py` | Malformed file rejection, authorized retrieval and desktop/mobile registration upload tests passed |
| FR-1.7 | Full UUID, patient-requested QR code carrying an opaque random code; receptionist/branch-manager check-in, single-use credential valid for 10 min | `client_checkin_credential`, `client_checkin_event`, `routers/onboarding.py` | API check-in, replay rejection, expiration and authorization tests passed |
| FR-1.8 | Reception-assisted signup with the same `ClientRegister` validation, patient consent, staff attribution and branch validation | `POST /api/v1/auth/register/client/assisted`, `client_registration_consent.registration_mode/registered_by_staff_id` | Auth/consent and reception-browser checks passed |
| FR-1.9 | Duplicate email across account roles and duplicate SA ID across clients, including DB-unique conflict handling | `auth_admin.py`, `client.email`, `client.id_number` UNIQUE | Duplicate email/SA-ID API checks passed |
| FR-1.10 | Explicit save, restore and discard registration drafts for 24 hours on the same browser/device | `front-end/app.js` localStorage | Desktop/mobile restore and purge-on-success tests passed |

**Privacy by design:** Drafts intentionally do **not** store SA ID numbers, birth dates, passwords, uploaded documents or consent decisions. Patient files remain in the existing protected database rather than public static folders. The check-in QR does not contain a South African ID or medical records. New client IDs are 36-character UUIDs; older `cli_...` identifiers remain unchanged and valid.

## Requirement limitations / deployment blockers

1. **FR-1.5 is conditional:** A real welcome message cannot be sent without a real SMTP provider and approved from-address/template. The code queues mail transactionally. Configure the optional `notifications` service to deliver, with a 30-second polling interval. **Five-minute delivery is not guaranteed during provider outages or when SMTP is unconfigured.** No live message was sent in these tests.
2. **FR-1.7 uses time-bound, on-demand QR codes:** Patients open **My QR Check-In**, generate a QR, then present it to reception. A QR is single-use and expires in 10 minutes. The requirement's unique patient ID is generated during registration, but the scannable QR is issued upon patient request, not permanently printed on account creation.
3. **FR-1.8 must undergo clinical/legal review:** Reception users can assist on their own branch's active account. The recorded IP is the reception terminal, not necessarily the patient's device. The privacy notice remains a **draft**, and patients must personally review it and choose whether to consent.
4. **FR-1.10 is device-local:** Only name, email, phone and selected gender are restored on the same device; draft expiry is 24 hours. It is not a synchronized server-side draft. Shared computers should not be used to save drafts.
5. **Full PostgreSQL and Docker integration was not available in this build environment.** Run the migrations and use fictional patient details locally before approving a merge.
6. Staff RBAC and clinical access across all eight roles are still not fully complete. This change does not grant reception users general clinical-record access.

## Local setup: do not alter your working environment

1. Back up your **local** database and retain your existing `.env` and Docker volumes. Keep the live Oracle Cloud deployment untouched.
2. Extract the updated ZIP to a **different development folder**, or apply the patch to a copied project.
3. Check existing local migrations `008`, `009` and `010` before applying the new ones. If those tables/columns already exist, do not reset or replace the database.
4. Build and run the API locally:

   ```powershell
   docker compose build api
   docker compose up -d --no-deps api
   docker compose exec api python migrations/apply_011_014_onboarding.py
   ```

   The migration runner executes `011`–`014` in one PostgreSQL transaction. A missing prerequisite produces an error without intentionally deleting existing data.
5. Hard-refresh the browser (Ctrl+F5) and test with fictional data. Verify patient signup, uploaded files, sign-in, My QR Check-In, and a receptionist account's Register Patient / Patient Check-In pages.
6. If **and only if** you have approved SMTP settings, configure `WELCOME_SMTP_HOST`, `WELCOME_FROM_EMAIL` and any needed SMTP credentials in a private `.env`, then start:

   ```powershell
   docker compose --profile notifications up -d --build welcome-worker
   ```

   Test with an address you control. The worker stays disabled unless the `notifications` profile is enabled.
7. Do **not** push to GitHub `main`. The existing workflow can deploy to Oracle Cloud automatically.

## New SQL migrations

- `011_registration_welcome_outbox.sql` — transactional email queue.
- `012_registration_uploads.sql` — secure profile-photo table.
- `013_client_qr_checkin.sql` — hashed QR credentials and check-in events.
- `014_assisted_registration.sql` — assisted consent provenance.

Each migration has its own optional apply script; `apply_011_014_onboarding.py` runs them together.

## Testing

Isolated API, mocked PostgreSQL insert-contract, SMTP mock, and browser test scripts are under `qa/`. The original FR-1.1/1.2/1.3 browser/API tests still run. **The full legacy Pytest suite could not collect here because `langchain_core` is absent from this testing environment.** Real PostgreSQL migration, container integration, SMTP and legal approval are separately pending.

## Next actions

After successful local Docker confirmation, plan a complete onboarding acceptance test with a real (fictional) receptionist account. Obtain a practice-approved privacy notice and approved SMTP configuration before using real patient data.
