# NutriCare — FR-1.3 Electronic POPIA Consent

**Baseline:** FR-1.2 updated application (built from `dietitian-app(7).zip`).

**BRS:** FR-1.3 requires electronic POPIA consent with a timestamp and IP address.

## Implemented

- Patient registration step 3 displays an accessible, expandable **privacy notice summary** and a mandatory, unchecked-by-default **consent checkbox**.
- Only patient signups are affected. Existing dietitian registration does not require patient consent.
- The API requires explicit `consent_to_care: true` and `privacy_notice_version: "2026-10-28-v1"`; absent, false, or outdated values receive **HTTP 422**.
- At registration, the server generates a UTC timestamp and obtains the peer IP (or a trusted proxy's X-Real-IP if explicitly configured).
- A new `client_registration_consent` PostgreSQL table stores `client_id`, `privacy_notice_version`, `consented_at`, and `ip_address`.
- The **client INSERT and consent INSERT use the same database transaction**, so errors cause a rollback rather than creating a client without a record of consent.
- In-memory development mode uses `client_registration_consents_db` instead of PostgreSQL.
- No previous account or password is rewritten. Historical consent is not manufactured for old client accounts.

## Database table

| Column | SQL type | Meaning |
|---|---|---|
| `client_id` | `VARCHAR(36) PRIMARY KEY` | Links uniquely to `client(client_id)` |
| `privacy_notice_version` | `VARCHAR(40) NOT NULL` | Version of the notice agreed to |
| `consented_at` | `TIMESTAMPTZ NOT NULL` | Server UTC acceptance time |
| `ip_address` | `VARCHAR(45) NOT NULL` | Validated TCP peer IP or trusted proxy-reported client IP |

## Before testing in local Docker

1. **Do not replace your working database, Docker volumes, or `.env`.** Extract this app to a separate local development directory; copy your existing local `.env` there securely.
2. **Make sure migration 009 is already applied** (phone field). If not, apply it in your *local* environment before proceeding.
3. From the copied project root, run:

   ```powershell
   docker compose build api
   docker compose up -d --no-deps api
   docker compose exec api python migrations/apply_010_client_registration_consent.py
   ```

4. Open your local app in a browser, hard-refresh (Ctrl+F5), select **Create account → Patient**, and proceed to step 3.
5. Confirm a patient **cannot register without ticking consent**, that the expandable notice is readable, and that a fictional test patient **can register and sign in** after ticking the box.
6. Verify local PostgreSQL has a consent record without exposing any real patient's personal information. For example, after inserting only a fictional test record, inspect the table structure in your local DB tool or run a limited query.
7. Confirm dietitian login and signup still work. **Do not push to GitHub `main` or touch Oracle Cloud.**

## Trusted proxy IP

By default, the server records the direct request peer IP. Behind Nginx, that might be the **proxy container's address**, not the patient's public IP. To trust `X-Real-IP`, the API must be configured with **only the known Nginx proxy IP/subnet**, using `REGISTRATION_TRUSTED_PROXY_CIDRS`; this is optional and should be approved by the deployment owner. Never trust all IPs (`0.0.0.0/0`), as this enables spoofing.

## Privacy/legal review required

The notice currently shown is an **illustrative draft**. The practice must approve a correct, complete POPIA privacy notice with accurate responsible-party identity, contact details, purposes, retention, recipients, rights and any additional applicable requirements **before real patient registration**. This code alone **does not certify POPIA compliance**. Marketing permission is not bundled with patient-care consent.

## Verification performed in this environment

- FR-1.3 API smoke checks: **PASS** (missing/false/outdated consent rejected, version and UTC timestamp recorded, trusted/untrusted IP behavior, existing login/dietitian registration).
- FR-1.3 database query and failure contract: **PASS** (atomic dual INSERT structure and migration; simulated write failure cannot return success).
- FR-1.3 browser smoke checks at 1280px and 375px: **PASS**.
- Previous FR-1.1 and FR-1.2 API/browser/database smoke checks: **PASS**.
- Python compilation and Node JavaScript syntax: **PASS**.
- Full legacy Pytest: **NOT RUN** — this review environment lacks `langchain_core` and other application dependencies.
- Real Docker/PostgreSQL integration and migration: **NOT VERIFIED HERE**; needs testing on the user's local development PC.

## Stop point

No implementation of FR-1.4 or later has been made. Await the user's permission for the next requirement.
