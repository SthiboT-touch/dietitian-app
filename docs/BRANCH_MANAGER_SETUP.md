# Branch Manager — local development

The application already includes a `branch_manager` staff role and administrator-only account provisioning. This update introduces a dedicated branch dashboard with an assigned-branch name, counts of active branch staff, reception staff, and branch managers, plus links to patient registration, check-in and the staff profile.

## Create a Branch Manager
1. Start your application in a safe local setup (use your own local environment configuration; do not overwrite the production `.env` or database).
2. Log in as a **system administrator**.
3. Open **Staff & Roles** in the administration sidebar.
4. Fill in the staff member's real name, email, a unique strong password (12+ characters), choose **Branch Manager**, and select an **existing branch**.
5. Submit **Create staff account**. The branch assignment is mandatory.
6. Log out and log in with the new staff email and password. The branch dashboard should appear. Do not use production credentials for testing.

## New API
`GET /api/v1/branch-manager/overview` requires an authenticated active `branch_manager` account. It returns the manager's assigned branch and aggregate active staff counts for that branch only. It does not return patient clinical records, staff identity details, or cross-branch figures.

## Checks
- `node --check front-end/app.js`
- `python -m compileall -q back-end/routers/staff.py`
- With dependencies installed: `python -m pytest -q back-end/tests/test_staff_roles_and_audit.py`

**Security:** This is not a branch-wide administrative account. Branch Manager cannot provision staff or access protected clinical records. Existing admin/staff authentication is reused. No existing credentials, migrations, production services, or server files were changed.
