# NutriCare — Patient UI Navigation and Profile Menu

**Baseline:** `NutriCare_Patient_UI_Dietitian_Control_Updated_App.zip` (the previous updated application based on `dietitian-app(9).zip`).

## Delivered

- The Patient sidebar now shows **Dashboard, Appointments, Progress, Goals, AI Coach, Settings**, in that order. No other primary Patient sidebar links are displayed.
- The Patient's full name and initials avatar appear in a clickable top-right account control. Its menu contains **My profile**, **Settings**, **My QR check-in**, and **Sign out**. It closes when navigating, clicking elsewhere, or pressing Escape, and exposes its state via `aria-expanded`.
- The new Patient Settings page groups existing destinations: profile, QR check-in, medical conditions, allergies, approved meal plan, recommendations, pregnancy/lactation when applicable, and Support & Tickets. These features were **moved out of the sidebar**, not deleted.
- Existing dietitian, receptionist, manager, compliance, executive, content-manager, and administrator navigation is not intentionally changed.
- The patient Goals page remains read-only and approved Meal Plans remain dietitian-controlled, as in the previous implementation.
- Desktop and mobile styles were adjusted without touching FastAPI endpoints, PostgreSQL schema, login credentials, or production configuration.

### Files changed

- `front-end/index.html` — account menu markup, new patient Settings nav, sidebar visibility markers, asset cache versions.
- `front-end/app.js` — role-specific sidebar visibility, account menu events, settings content and navigation logic.
- `front-end/vibrant-theme.css` — ordered six-item patient nav, responsive account menu and compact Settings cards.
- `qa/verify_patient_navigation_browser.py` — browser tests using mock API data.

### Verification in isolated test environment

- **PASS**: Desktop Chromium at 1440×900: six Patient nav destinations, visual order, avatar menu, keyboard Escape, Settings and Profile, Sign Out.
- **PASS**: Mobile Chromium at 390×844: the same navigation and account-menu checks.
- **PASS**: Dietitian navigation regression: original profile sidebar stays present and patient Settings remains hidden.
- **PASS**: Existing clinician-controlled Goals and Meal Plans frontend checks (4 cases).
- **PASS**: Existing frontend diagnostics/health checks.
- **PASS**: JavaScript syntax and Python source compilation checks.

**Not verified:** real PostgreSQL/Compose startup, live login, real patient records, or the full backend regression suite in this environment. Browser checks used synthetic names and mocked API responses.

### How to test locally

1. Keep a copy of your currently working project.
2. Extract the updated ZIP to a **separate development folder**. The ZIP intentionally excludes `.env` and Git history. Preserve your local `.env` separately; do not change production secrets.
3. If your Nginx container serves the static files through a volume, restart only the local stack as appropriate. If they are baked into the image, rebuild the local serving image according to your Compose configuration.
4. Open `http://localhost/` in a local browser and hard refresh with `Ctrl+F5` to bypass cached scripts.
5. Sign in as a **patient**. Verify the sidebar has only the six requested items, the top-right avatar/name opens Profile, and the Settings page provides the previously available tools.
6. Check a **dietitian** account to confirm their dashboard and original navigation remain available.

No SQL migration is required, and no server or account credentials were changed.
