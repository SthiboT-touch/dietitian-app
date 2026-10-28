# NutriCare — Security Milestone 02: Staff Roles & Access Auditing

**Source:** `dietitian-app(6).zip` | **Implementation:** 28 October 2026 | **Target release:** 8 November 2026

> These changes are for local review and testing. No Oracle Cloud deployment, live database migration, or password change was performed.

## Implemented in this milestone

1. **Five additional BRS staff roles**: reception, branch manager, compliance officer, executive, content manager. The existing client, dietitian, and administrator roles are preserved.
2. **Admin-only staff provisioning**: create, list, change role/branch, enable/disable. Staff passwords are hashed using the existing PBKDF2 password routine, never returned through the staff directory. Reception and branch managers must be assigned to an existing branch. Staff cannot self-register or promote themselves to full administrator.
3. **Staff sign-in and identity**: existing login endpoint handles staff credentials, and staff have their own bearer-session store. Inactive staff accounts are rejected; updating a staff account revokes its in-memory sessions in this process.
4. **Least privilege**: all new staff roles are denied clinical record and administrator functionality by default. Only the compliance officer and administrator can read the new access-event API. Branch-scoped operational permissions are **not yet implemented**.
5. **Separate access-event trail**: logs actor role/id, HTTP method, resource path, response status, and timestamp for selected API requests (client records, appointments, goals, admin, AI, meal-planning, dietitian self-service, staff). No request body, health record content, passwords, or tokens are logged. Denied requests appear in the log. The existing approval history is kept separately.
6. **New admin interface**: `Staff & Roles` (create, change role/branch, enable/disable) and `Access Events`. Staff sign-in opens a limited dashboard and profile; compliance officers get access to the read-only event view.
7. **Additive SQL migration 008** for an existing PostgreSQL database; the equivalent tables are added to the initial SQL for fresh local installations.

### BRS alignment

| Area | Status |
| --- | --- |
| Section 4.4: eight user roles modeled | Implemented as a role foundation, **not all operational permissions** |
| FR-2.10: record access filtering | Retained from Milestone 01; new roles have no clinical access by default |
| FR-6.5: common permissions | Partially implemented; new `require_roles` helper and server-side restrictions |
| FR-2.8: data access and modification audit | Partially implemented; selected API events, best-effort writes |
| FR-6.10: unified audit trail across modules | Partially implemented; not every operation or internal change logged |
| Section 6.2: session/MFA requirements | **Not complete**: no MFA, persisted sessions or automatic expiry |

## What files changed

- `back-end/state.py`: added in-memory staff and audit stores.
- `back-end/security.py`: identity resolution for active staff accounts.
- `back-end/role_management.py` (new): strict role names and `require_roles` dependency.
- `back-end/routers/staff.py` (new): staff profile and admin-managed accounts.
- `back-end/routers/auth_admin.py`: added staff sign-in path while preserving legacy logins.
- `back-end/routers/access_audit.py` (new): restricted, paginated event listing.
- `back-end/audit.py` (new), `back-end/app.py`: access-event recording middleware and router registration.
- `back-end/helpers.py`: registration email uniqueness considers staff accounts; remains compatible with local databases prior to migration 008.
- `back-end/migrations/008_staff_roles_and_access_audit.sql` (new): non-destructive new tables/indexes.
- `back-end/migrations/apply_008_staff_roles_and_access_audit.py` (new): local migration runner.
- `back-end/dietitainDB.sql`: includes new tables for *fresh* local databases.
- `front-end/index.html`, `front-end/app.js`: staff/account and audit navigation and interfaces.
- `back-end/tests/test_staff_roles_and_audit.py` (new): staff provisioning, isolation, role changes, audit tests.

## Local testing instructions — **do not run on Oracle Cloud**

1. Keep your existing, known-working project as a backup and extract the updated ZIP in a separate folder for code review.
2. If integrating into Git, create a feature branch. **Do not push to `main`**: this repository's GitHub Actions workflow automatically deploys `main` to Oracle Cloud.
3. Confirm Docker Compose points to a local development PostgreSQL database and that the project-root `.env` contains only **local** credentials. Never use production credentials or a production database URL.
4. Build the local image in a project whose Docker containers and port mappings you control:
   ```powershell
   docker compose build api
   ```
5. Run the isolated unit tests using a disposable container (tests force the in-memory database):
   ```powershell
   docker compose run --rm --no-deps -e APP_USE_IN_MEMORY_DB=1 api sh -c "pip install -r requirements-dev.txt && python -m pytest -q tests/test_staff_roles_and_audit.py tests/test_authorization.py tests/test_client_lactation_profile.py"
   ```
6. For a **local-only existing PostgreSQL database**, after verifying the target database and taking a backup, apply **migration 008** once (safe to rerun):
   ```powershell
   docker compose run --rm --no-deps api python migrations/apply_008_staff_roles_and_access_audit.py
   ```
   **Do not run this against the Oracle Cloud production database.** The new admin Staff & Roles page requires this table.
7. Launch/update the local API using your normal Docker workflow after migration. Do not delete Docker volumes or reset the database. Hard-refresh the browser to load `/static/app.js?v=25`.
8. Sign in with an existing administrator. Navigate to **Staff & Roles**. Create a test Reception user assigned to a local branch, confirm that their password is not displayed, update their role, and disable the account. Check **Access Events** for the outcomes.
9. Sign in as a new staff test account and confirm the limited staff dashboard works, while patient and administrator pages remain inaccessible. Sign in as a compliance officer to verify read-only access events.
10. Recheck normal client login, dietitian login, medical records, appointments, meal plans, and AI against the local PostgreSQL and Ollama services before merging.

## Test evidence from the package preparation environment

- **32 passing tests** across `test_staff_roles_and_audit.py`, `test_authorization.py`, and `test_client_lactation_profile.py`. Parametrized role tests are counted individually.
- These tests ran through FastAPI's `TestClient` in an **isolated in-memory test harness**. The unavailable PostgreSQL and AI-service imports were replaced by throw-on-use stubs for the purpose of these tests only. The test harness is **not** included in the application package.
- Python compilation: passed. JavaScript `node --check`: passed.
- **Not tested here:** full regression suite, actual PostgreSQL migrations, Docker compose startup, full browser interactions, Ollama/AI functionality, real concurrent sessions or production access-event retention.

## Remaining critical work

- Confirm local PostgreSQL migration and end-to-end staff workflows.
- Add appropriate least-privilege branch-based operations to reception and branch managers; do not grant all staff access to clients by default.
- Implement MFA, persistent expiring sessions, password reset, login rate limiting, cross-worker revocation.
- Harden auditing for transactional durability and tamper resistance, broader coverage, retention and POPIA review. Currently audit writes are **best-effort**, meaning missing audit storage does not block the associated API response.
- Review existing administrator-wide clinical access under least-privilege and obtain agreement on compliance officer access scope.
- Add tests for real PostgreSQL, frontend, permissions after staff changes in multiple API workers, and security/privacy sign-off before any production release.

**This milestone is partial BRS progress, not a compliance certification.**
