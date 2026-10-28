# NutriCare — BRS FR-1.2: Registration field validation

Implementation date: 28 October 2026. Baseline: FR-1.1 updated application.

## Changes

- Added immediate field validation feedback for patient email, South African 13-digit identity number, phone number and date-of-birth consistency.
- Added the phone field to the second step of patient signup. New registrations require it; older client records are not modified.
- Validates the same formats on the API server using Pydantic 2 field validators. The API responds with 422 for invalid inputs.
- Normalizes registration email to lowercase and South African phone numbers to `+27XXXXXXXXX` before storage.
- Added an additive local PostgreSQL migration 009 to create the nullable `client.phone` column; included it in the initial database SQL for new installations.
- Existing password/login, dietitian registration, and FR-1.1 wizard flow preserved.

## Important limitations

- New patient registration currently expects a **South African ID**. Passport/other-country identity documents are a separate later design decision.
- This is **format and checksum validation**, not identity verification, age verification, phone ownership, or OTP/email confirmation.
- Older client records retain a NULL phone value until a later contact-details-update workflow is created.
- No modifications were made to Oracle Cloud or any live database.

## Local update steps (Windows PowerShell)

1. Save a backup or commit your **local** work first and keep your existing project root `.env` unchanged.
2. Apply the patch ZIP's changed files to your **local** working project only. Do not push to `main` (it triggers production deployment).
3. Rebuild and recreate only the local API container from the project root:

   ```powershell
   docker compose build api
   docker compose up -d --no-deps api
   ```

4. Apply the new phone column migration **only to the local development database**:

   ```powershell
   docker compose exec api python migrations/apply_009_client_registration_phone.py
   ```

   This is a nullable, additive column. It does not reset volumes or replace existing records.
5. Refresh the browser with Ctrl+F5. Navigate to **Create account → Patient**. Enter a test email, a fabricated test ID number with a valid checksum and matching fabricated date of birth, and a test phone number; verify invalid inputs are blocked. Use only fictional information for testing.
6. Verify registration and login against your **local** PostgreSQL database. Verify dietitian registration and current staff/admin login still work. Do not use real patient data for testing.
7. If the migration reports an error, **stop** and share the error text without posting credentials.

## Automated checks done here

- Python source compilation and JS syntax: passed.
- FR-1.1 API and browser regression tests: passed.
- FR-1.2 FastAPI validation and login smoke tests (in-memory): passed.
- FR-1.2 desktop (1280px) and mobile (375px) interactive browser tests with mocked network: passed.
- Database INSERT contract and migration SQL presence (mocked DB cursor): passed.

**Not tested here:** an actual running local PostgreSQL migration, live Docker service integration, full suite importing LangChain, and an actual browser registration saved to your local DB.

FR-1.3 (POPIA consent) has **not** been implemented. Await permission and local result confirmation before proceeding.
