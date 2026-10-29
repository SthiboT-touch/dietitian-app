# NutriCare: Advanced account profile, all eight user roles

## Included

- **All authenticated roles:** client/patient, dietitian, admin, reception, branch manager, compliance officer, executive and content manager.
- **One private account page** accessible from the top-right account menu (staff profile navigation also opens it).
- Professional profile hero, role and account verification details, contact form, appointment status summary, quick actions.
- Patient-only health summary, assigned dietitian/branch and next appointment details. Health data still comes from the existing authorization-protected patient endpoints, never from a new staff endpoint.
- Photo upload (JPG, PNG, WebP), preview, reposition and zoom crop, save, change and remove. Original files are decoded, EXIF orientation is applied, embedded metadata is stripped, and 512x512 WebP bytes are stored in `account_profile` in PostgreSQL (or memory for local demo). The API limits incoming file size to 2 MB; the browser can crop source photos up to 8 MB before sending the smaller file. Photos are only served through authenticated self-service endpoints with `Cache-Control: private, no-store`.
- Patient photos already submitted during registration are preserved and shown as a fallback until changed or explicitly removed.
- Save name, phone number and address; patients can also save emergency contact; non-patient roles can save a bio. Email/verified identity details, role, license and clinical assignments remain **read-only**.
- Manage preference flags (preferred contact, optional email notifications, appointment reminders); these are **stored settings, not proof that any SMS/email reminder delivery service is configured**.
- Secure change-password using the account's current password, hashing the new one and invalidating this process's bearer sessions. Do not reuse production passwords for local demo tests.
- Preserves patient navigation in the exact order: Dashboard, Appointments, Progress, Goals, AI Coach, Settings. No separate Meal Plan sidebar item; authorized meal plans remain accessible via Profile, Settings and Dashboard.

## Running in isolated temporary memory mode (recommended first)

1. Extract the **complete updated app ZIP** into its own local directory.
2. Open a terminal in the extracted `dietitian-app` folder.
3. Run `docker compose -f docker-compose.memory.yml up --build -d`.
4. Open `http://127.0.0.1:8088`, sign in and click your name/photo at the top-right, then **My profile**.
5. Change the photo, edit contact information, check Security & preferences, and verify each account type in a separate session.
6. `docker compose -f docker-compose.memory.yml down` when done. In-memory account changes disappear with the container. The AI Coach requires a separately configured Ollama service.

## PostgreSQL and production safety

**Do not push this directly to `main` or deploy to Oracle Cloud yet.** The existing repository's GitHub Actions workflow can deploy automatically, and production still needs a controlled migration plan for earlier migrations 017, 018 and 019 as well as this new 020 migration. No live server or password was changed.

For a **local, backed-up PostgreSQL test database** where migrations through 019 have already been applied, run the following **against that local instance only**:

`docker compose exec api python migrations/apply_020_account_profiles.py`

Migration `back-end/migrations/020_account_profiles.sql` only creates the optional `account_profile` table; it does not modify or replace the existing client, dietitian, staff, admin or password tables. It does **not** run automatically when you start normal Docker Compose. Do not use this command on the live server until there is a reviewed rollout and backup. The local memory mode requires no database migration.

## Code organization

- `back-end/routers/account_profile.py` — shared role-protected API endpoints.
- `back-end/state.py` — local-memory profile storage.
- `back-end/app.py` — router registration.
- `back-end/migrations/020_account_profiles.sql` + runner — additive PostgreSQL table.
- `back-end/dietitainDB.sql` — fresh installations include the profile table.
- `front-end/app.js`, `front-end/index.html`, `front-end/vibrant-theme.css` — profile pages, menu and responsive styling.
- `qa/verify_account_profiles_api.py` — self-service role isolation, images, passwords and preferences.
- `qa/verify_account_profiles_browser.py` — real Chromium desktop/mobile smoke tests.

## Checks performed

- 122 isolated FastAPI account-profile checks across all eight roles.
- Chromium account profile tests across all eight roles, including phone-sized patient layout and real crop-and-upload interaction (against mocked local API calls).
- Appointment virtual meetings API/browser regression checks.
- Appointment QR check-in regression checks.
- Care journey API/browser regression checks.
- Registration and six-menu patient navigation regression checks.
- Python compileall and Node JS syntax checks.

Docker integration with a live PostgreSQL container was **not** executed in this build environment; perform the local Docker integration test before considering production deployment. The public demo Jitsi video configuration is not suitable for confidential healthcare consultations without a vetted provider and controls.
