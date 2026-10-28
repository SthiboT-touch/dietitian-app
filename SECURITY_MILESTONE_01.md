# NutriCare — Security Milestone 01

**Date:** 27 October 2026  
**Source:** `dietitian-app(5).zip`  
**Deadline:** 8 November 2026  
**Change type:** Local-development changes only. No production changes were performed.

## BRS alignment

- **FR-2.10:** Client health record filtering: clients see their own records; dietitians must be assigned; existing system administrators retain existing elevated permissions.
- **FR-6.5:** Consistent authorization for client-record, appointment and goal endpoints.
- **Section 6.2:** API bearer-session validation for protected endpoints. Existing opaque, in-memory sessions are preserved; persistence, MFA and session expiry are **not** implemented.

This milestone is **partial progress** toward these requirements, not full BRS compliance.

## Changes made

| File | Implementation |
|---|---|
| `back-end/security.py` | Added `current_identity`, `client_is_assigned_to_dietitian`, `authorize_client_access`, and reusable `require_client_record_access`. |
| `back-end/routers/clients.py` | Added FastAPI dependency guarding all 27 client-specific health, meal, metrics, progress, specialist-nutrition, and document routes. Protected filtered client directory lookup. |
| `back-end/routers/appointments.py` | Enforced caller ownership on bookings, role-scoped appointment lists, participant authorization on decisions, and authorization for goals. |
| `front-end/app.js` | Medical-document links now use an authenticated fetch and temporary Blob download rather than unauthenticated browser navigation. |
| `back-end/tests/test_authorization.py` | Added security regression tests, including a check that all `/clients/{client_id}` endpoints have the dependency. |
| `back-end/tests/test_app.py` | Updated affected existing tests to send role-appropriate authentication. |
| `back-end/tests/test_client_lactation_profile.py` | Updated regression tests to log in as the client before posting health records. |

No database schema changes, credential changes, password resets, or production deployment were made.

## Authorization rules implemented

- **Client:** View/edit their own client records, create their own appointment, view their own appointments and goals, and cancel their own future appointment.
- **Dietitian:** View/edit the records of assigned clients; see only their own appointments; review/cancel appointments addressed to them; access goals of assigned clients.
- **System administrator:** Existing broad access maintained for backward compatibility. Further least-privilege review and access auditing are still required.
- **Guest / invalid token:** Access to protected routes is denied with `401`.
- **Authenticated wrong account:** Access to protected records/appointments is denied with `403`.

This milestone intentionally does **not** add the other five planned BRS roles (reception staff, branch manager, compliance officer, executive, content manager).

## Test evidence

An isolated test harness exercised real FastAPI routes against the in-memory state rather than a live database. It stubbed optional PostgreSQL and AI imports unavailable in the review environment.

- **27 passed**, **38 deselected** in the security-related subset (new security tests + affected existing appointment/client/lactation tests).
- Python `compileall` passed.
- Node.js `--check front-end/app.js` passed.
- The complete project test suite, real PostgreSQL integration, Ollama integration, and live Docker deployment **were not run** in the review environment.

### Local verification procedure

Use a **local development copy** of the project and its existing local `.env` file (do not copy production secrets or use a production database).

1. Preserve a backup of your current local project and work in a separate feature branch.
2. Compare the delivered code with the existing local checkout before copying changes.
3. Start or confirm your local Docker environment; **never run `docker compose down -v`** for this change.
4. Build an updated **local** API image without deploying it:
   ```powershell
   docker compose build api
   ```
5. Run the tests in a disposable local container, explicitly forcing the in-memory database and installing test-only dependencies there:
   ```powershell
   docker compose run --rm --no-deps -e APP_USE_IN_MEMORY_DB=1 api sh -c "pip install -r requirements-dev.txt && python -m pytest -q tests/test_authorization.py tests/test_client_lactation_profile.py"
   ```
6. For the complete regression suite, use the same disposable-container approach with `python -m pytest -q` (without the two explicit test paths). Confirm that all tests use isolated data.
7. Verify locally: client login, dietitian login, client profile, appointment approval/cancellation, and download of a medical document.
8. Only after review, create a pull request into your development branch. Do not push directly to `main` because your repository has a production deployment workflow.

**Note:** The API Dockerfile currently installs runtime `requirements.txt`, not `requirements-dev.txt` (which includes pytest). This command adds pytest only to the disposable container and forces the in-memory test database. Do not connect a test run to a live or shared database.

## Remaining work and known limitations

1. Opaque sessions are held in memory; session persistence/expiration, staff MFA, credential rotation, logout/revocation and token management remain future security work.
2. Current administrators retain broad clinical-record access; audit and reconsider per least-privilege requirements.
3. Implement a comprehensive audit trail for all read and write actions (FR-2.8, FR-6.10). Existing approval logs do not meet that requirement.
4. Add dedicated roles and branch-level scopes from the BRS; none were added in this milestone.
5. Confirm assignment-change edge cases, concurrent scheduling, cross-branch transfers, encryption, document retention and POPIA requirements.
6. Test the PostgreSQL execution path on an isolated local database before merging.
7. Run the full regression suite with real app dependencies and perform manual role-based frontend testing.
8. This is a targeted first milestone; other routes and modules require separate security audits.

**Production status:** Not deployed; live Oracle Cloud, its data, and its passwords remain unchanged.
