# Patient My Meal Plan Sidebar Restoration

Baseline: NutriCare Patient Navigation Updated App.

## Change

- Restored **My Meal Plan** as a visible primary patient navigation item.
- Sidebar order: Dashboard, Appointments, Progress, Goals, My Meal Plan, AI Coach, Settings.
- Preserved top-right profile/avatar menu and all existing patient pages.
- Active navigation highlights **My Meal Plan** rather than Settings while viewing the plan.
- Meal plan continues to load only the backend's **approved** plans and is **read-only** for patients. Dietitian drafting and approval functionality is unchanged.
- Frontend static asset versions incremented to help refresh cached scripts/styles.
- No backend, database, API, or production deployment changes.

## Files changed
- front-end/index.html
- front-end/app.js
- front-end/vibrant-theme.css
- qa/verify_patient_navigation_browser.py

## Verification
See accompanying tool test results. Test browser uses synthetic client data, not real patient records. Full PostgreSQL/Docker integration must still be confirmed locally.
