# NutriCare Patient UI — Clinician-Controlled Goals and Meal Plans

**Baseline:** `dietitian-app(9).zip` (uploaded by the user).  
**Scope:** Patient Goals and Meal Plan views, plus assigned-dietitian goal creation.  
**Production status:** No production, database, GitHub, or password changes were made.

## What changed

| Area | File | Change |
|---|---|---|
| Goal authorization | `back-end/routers/appointments.py` | `POST /api/v1/goals` now requires an authenticated **assigned dietitian**. Patients, administrators, unauthenticated callers and unassigned dietitians cannot create goals. The existing `GET /api/v1/goals` remains available to an authorized patient for viewing. |
| Patient Goals | `front-end/app.js` | Removed the patient goal creation form and submit handler. Added a read-only goals panel, assigned-goal list and a link to appointments for discussing changes. |
| Dietitian workspace | `front-end/app.js` | Added **Set goals** in the dietitian's patient roster, and **Manage patient goals** in the patient profile. This opens a goal-setting form for the chosen client. |
| Patient Meal Plan | `front-end/app.js` | Updated heading and permissions guidance: only approved plans can be viewed; no editing. Improved approved schedule rendering when the reviewed schedule has a candidate recipe. Added a localized error card and a **Try again** button instead of losing the whole page on an API failure. |
| Styling | `front-end/styles.css` | Added clinician-guidance, read-only badge and mobile layout styles. |
| Test updates | `back-end/tests/test_authorization.py`, `back-end/tests/test_app.py` | Updated two legacy goal tests to reflect assigned-dietitian-only goal creation. |
| New regression test | `back-end/tests/test_clinician_controlled_goals.py` | Checks authentication, assignment, patient viewing, and visibility of approved vs. draft meal plans. |

### Access model

- **Client:** Can view only their own goals and published, approved meal plans; cannot create goals through the UI **or** the backend API.
- **Assigned dietitian:** Can create a goal for an assigned client; can use the existing meal plan draft, screening and review workflow.
- **Unassigned dietitian:** Cannot create goals for someone else's patient.
- **Administrator:** Does not receive the right to prescribe clinical goals from the admin role.
- **Other staff:** No new prescribing rights were added.

### Verification completed in this environment

- 7 isolated FastAPI/meal-access tests **passed**, using an in-memory store (a review-only stub replaced the unavailable `psycopg2` import, and no actual database was contacted).
- 4 Node.js UI behavior checks **passed** (patient goal read-only view; approved meal plan read-only rendering; meal plan API error + retry; dietitian goal form).
- JavaScript syntax check **passed**.
- Python compilation of changed files **passed**.

**Not verified:** actual Docker startup, PostgreSQL integration, user sign-in in a real browser, full repository regression suite, or the cause of the server-side 500 error in the supplied Meal Plan screenshot. A newer ZIP cannot by itself repair missing database migrations or production errors. The view now reports an actionable error and allows a retry.

### Running locally (not production)

1. Make a backup of your working `dietitian-app(9)` folder and keep its current `.env` private.
2. Extract the full updated ZIP into a **different** folder (the ZIP deliberately excludes `.env`, `.git` and generated caches). Copy only the **local** `.env` from your existing developer workspace if needed. Do not replace any live credentials.
3. From this separate **local** development folder:

   ```powershell
   docker compose build api
   docker compose up -d --no-deps api
   ```

4. Sign in as a patient, open **My Goals**: the add-goal form should be gone; assigned goals should be visible only.
5. Sign in as a dietitian assigned to that patient, go to **My Patients → Set goals**, create a fictional test goal, and confirm it appears on the patient's read-only Goals screen.
6. Sign in as the patient and open **My Meal Plan**: only approved plans should appear. On an API failure it should display a clear message and **Try again**.
7. If Meal Plan still returns HTTP 500, retrieve the API log for the displayed reference without sharing patient information or secrets. Also check locally that the `meal_plan_review` table (introduced in migration 007) exists; do not modify a production database to troubleshoot a local UI issue.

### Important limitations

- This changes **who may create** goals; it does not yet add edit/delete, revision history, or physician-specific roles. Existing goals are preserved in the database.
- In the current application, clinical plan authority is represented by the **assigned dietitian** role, not by a separate `doctor` account type.
- No database schema changes or new migrations are required.
- Existing meal-plan approval logic is preserved; the new frontend does not show unapproved drafts as a fallback.
