# NutriCare — Module 1, FR-1.1 implementation

**Source:** `dietitian-app(7).zip` (the latest uploaded locally working version)

**Scope:** FR-1.1 only — progressive digital patient registration. No other BRS module 1 item was intentionally implemented in this milestone.

## Implemented

- A three-step **patient** signup journey: (1) personal details, (2) patient identity and demographic details, (3) account password.
- Progress label, accessible progress bar, Back/Continue actions, and step-specific validation.
- Returning to a previous step preserves entered values. The registration request uses the **existing** `/api/v1/auth/register/client` payload and signs in through `/api/v1/auth/login`.
- Dietitian signup remains a one-page form, and the existing login/admin-setup experiences remain unchanged.
- Responsive CSS and focused step headings; no new backend migrations or database tables.

## Modified

- `front-end/index.html` — wizard sections and step controls.
- `front-end/app.js` — step navigation, validation, preservation of existing submit behavior.
- `front-end/styles.css` — spacing, progress component, mobile layout and reduced-motion support.

## New test utilities

- `qa/verify_fr11_api.py` — isolated FastAPI test of registration, login and duplicate email rejection (in-memory store only).
- `qa/verify_fr11_browser.py` — isolated Chromium/Playwright visual interaction tests with mocked network calls, at 1280px and 375px. Does not contact production.

## Checks run in the review environment

- Python compilation: PASS.
- JavaScript syntax (`node --check`): PASS.
- Isolated API registration/sign-in/duplicate tests: PASS.
- Desktop browser wizard validation, Back/Continue and submit payload: PASS.
- Mobile browser wizard validation, Back/Continue and submit payload: PASS.
- Dietitian one-page registration layout: PASS.

**Not confirmed:** Docker containers, the actual local PostgreSQL connection, SMTP, or an actual registration written to your local PostgreSQL database. The browser automation uses simulated API replies; local end-to-end confirmation is required before FR-1.1 can be signed off as running in your PC environment.

## Safe local verification (Windows PowerShell)

1. Keep your working folder and its `.env` intact; make a **separate copy** for FR-1.1.
2. Copy the three modified frontend files from the patch ZIP into that copy's `front-end/` directory, replacing just those three files.
3. If running the existing Docker frontend bind mount, refresh `http://localhost` with `Ctrl+F5`. No migration or Docker volume reset is needed. If your frontend is instead built into an image, rebuild only that local frontend service as appropriate.
4. Choose **Create account → Patient** and verify the three step headings, required field validation, Back/Continue, and preserved entries.
5. Register a **fictional test patient** and confirm it can log in and reach its own dashboard. Test the **Dietitian** signup layout still displays on one page. Check that administrator login remains unchanged.
6. Check the browser console for errors, API registration status, and local API logs. Never share tokens, credentials, `.env` files or real patient data.

**Never push directly to `main`**: the existing GitHub workflow may deploy that branch to Oracle Cloud. Do not run `docker compose down -v`, database reset, migrations, or commands on production.

## Next, only with permission

FR-1.2 — stricter real-time field validation (email, ID and phone), including backend validation and matching frontend errors. FR-1.2 is **not** included yet.
