# Dietitian & Nutrition Management

The browser app is served by the API at `http://localhost:8000` when running with Docker Compose.

## Project layout

- `front-end/` contains the HTML, CSS, and JavaScript browser app.
- `back-end/` contains the FastAPI app, database access, SQL schema, Python requirements, tests, and Dockerfiles. It is one API service, organised by area:
  - `app.py` is the entry point: it serves the browser app, `/health`, and includes every router below.
  - `routers/auth_admin.py` (auth, admin, branches, dietitian documents), `routers/clients.py` (health history, metrics, progress), `routers/appointments.py` (appointments, goals), `routers/meal_planning.py` (foods, recipes, meal plans), `routers/ai.py` (AI chat, plan generation, recommendation review).
  - `schemas.py` (request/response models), `security.py` (passwords and sessions), `helpers.py`, `state.py` (in-memory data), `config.py` (settings), `database.py` (PostgreSQL).
- `docker-compose.yml` and this README remain at the project root.

## Local development

Run the API and browser app with in-memory data (no PostgreSQL or Ollama required):

```powershell
python -m pip install -r back-end/requirements-dev.txt
$env:APP_USE_IN_MEMORY_DB = "1"
python -m uvicorn app:app --app-dir back-end --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001`. Run the test suite from the project root with `python -m pytest -q`.

The application uses `front-end/index.html` with its supporting CSS and JavaScript.

Signed-in users can open **Support & Tickets** to submit and reply to their own
tickets. System administrators use the same screen to review all tickets, reply,
mark them open/in progress/resolved, and search accounts to change passwords.
Password changes
require at least 12 characters and invalidate the account's existing sessions.

For an existing PostgreSQL installation, apply the additive ticket migration
before using support: `python back-end/migrations/apply_015_support_tickets.py`
with the normal database environment configured. The deployment workflow runs
this migration automatically. New databases include these tables in the base
schema. Local in-memory tickets last until the API restarts.

The login page also offers **Need help signing in? Contact support**. Guest
requests include a contact email and appear in the administrator's queue;
they do not grant access to an account or its tickets. Replies are kept in the
admin ticket thread; email delivery is not automatic. Existing databases also
need `python back-end/migrations/apply_016_guest_support.py` after migration 015.

## Run the nutrition AI

AI responses use a bounded, process-local cache (five minutes, up to 128 entries
by default). Exact repeats can reuse successful chat answers and generated plan
drafts. Keys include the authenticated user/patient scope, effective conversation,
patient records and clinician guidance, retrieved references, and model settings.
Changing these inputs generates a fresh answer; follow-up questions with changed
history are not treated as repeats. Access and assignment checks still run before
cache lookup. Live food-catalog tool results and failed responses are not cached.
Plan drafts still create separate recommendations requiring review.

Set `AI_CACHE_TTL_SECONDS` and `AI_CACHE_MAX_ENTRIES` in `.env` to adjust caching;
set either to `0` to disable it. Compose forwards both settings to the API.
Cached responses stay in API process memory, are not written to disk, and are
cleared on restart. Separate API workers keep separate caches.

In a dietitian's **Nutrition Coach** workspace, choose an assigned patient, add
clinical guidance or restrictions, and select **Activate patient assistant**.
Questions then use that patient's recorded allergies, conditions, measurements,
recent progress, goals, and care history, together with the dietitian's recorded
specialty and guidance. This patient assistant does not search the reference
library; the patient's records personalize suggestions but are not a medical
evidence source. Patient records are refreshed and assignment access is checked
on every question. Missing information must not be treated as a normal finding,
and model suggestions remain drafts requiring practitioner review. Activation
does not update clinical records or publish a care plan.

Changing the patient or guidance requires reactivation, which clears that
patient's assistant conversation. Activations and histories are separated by
dietitian and patient, stored in process memory, and cleared on API restart.
The assistant reads structured records and recorded care notes; it does not
extract text from uploaded PDFs or images. It requires the configured Ollama
chat model; patient-specific questions are not sent to LangSmith tracing.
Other AI workflows may still use the semantic reference library as described
below.

Create a root `.env` file with the database password before starting the API, database, and Ollama service:

```dotenv
DB_PASSWORD=your-database-password
```

For an existing database, use the same password already configured for it. Compose now reports a clear error if this required value is missing rather than starting with an empty password.

Start the services:

```powershell
docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5:0.5b
```

The selected model is stored in the `ollama_data` volume. Compose uses `qwen2.5:0.5b` by default. To select another model, set `OLLAMA_MODEL` in `.env` before starting Compose, then pull the same model with `docker compose exec ollama ollama pull <model>`. Deployments automatically pull the configured model before starting the API.

The API container connects to Ollama at `http://ollama:11434` over the Compose network. If the AI still cannot reply, confirm the configured model is installed with `docker compose exec ollama ollama list`, and pull it with `docker compose exec ollama ollama pull qwen2.5:0.5b` if it is missing. Rebuild and restart the API after changing its configuration with `docker compose up --build -d api`.

LangSmith tracing is optional. The root `.env.example` has a blank `LANGSMITH_API_KEY` slot. Copy it to `.env` if you do not already have a `.env`, keep your existing database password, paste your LangSmith key into that slot, and set tracing to `true`:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=dietitian-app
```

Keep the real key in `.env` only; `.env` is ignored by Git. Never paste the key into source files, commits, or chat. After saving `.env`, start or recreate the API with the optional Compose override; the main `docker-compose.yml` is unchanged:

```powershell
docker compose -f docker-compose.yml -f docker-compose.langsmith.yml up --build -d
```

The LangChain/LangGraph workflows automatically send chat, plan-generation, and recommendation-review traces to the `dietitian-app` project when a valid API key is set. Traces have workflow-specific run names and tags. Without a key, the app continues to run but traces are not uploaded. For local runs outside Docker, the root `.env` settings are loaded automatically. Traces may include chat messages, model responses, and health details sent to LangSmith. Use synthetic data only; do not send real patient or other sensitive data.

If the services are already running, recreate only the API so Compose does not try to recreate the existing database or Ollama containers:

```powershell
docker compose -f docker-compose.yml -f docker-compose.langsmith.yml up -d --build --no-deps --force-recreate api
```

The generated-plan endpoint is `POST /api/v1/ai/generate-plan` with a JSON body such as:

```json
{
  "client_id": "client-123",
  "dietary_goal": "More fiber and balanced meals"
}
```

The API sends the goal and any recorded allergies and medical conditions to Ollama. Recommendations remain `PENDING_REVIEW` until approved by a dietitian. These suggestions are not a substitute for clinical judgment.

AI workflows use LangGraph `StateGraph`s: chat loads recent context, routes greetings directly or invokes the tool-enabled LangChain agent, and saves the turn; plan generation loads the client profile, drafts a plan with `ChatOllama`, and stores the recommendation as `PENDING_REVIEW`; and a separate review graph applies the dietitian's decision. Chat history remains in process memory and is cleared when the API restarts; recommendation and review state use PostgreSQL when configured. The routes and response shapes stay the same; LangChain and LangGraph dependencies are installed from `back-end/requirements.txt`.

The Oracle Cloud deployment workflow applies the client health schema repair and dietitian document-branch association before starting the API. It creates any missing client health tables, adds the missing lactation end date column, and associates existing verification documents with each dietitian's current branch without replacing existing records. For other deployments, run `python back-end/migrations/apply_002_client_health_schema.py` and `python back-end/migrations/apply_003_dietitian_document_branch.py` once with `DATABASE_URL` configured.

All signed-in account roles can upload, replace, or remove a JPEG/PNG profile picture (up to 1 MB) from **My Profile**. Uploaded pictures appear in signed-in user and dietitian listings; signed-out visitors cannot view them. For an existing PostgreSQL database outside the deployment workflow, run `python back-end/migrations/apply_021_account_profile_photos.py` after `012_registration_uploads.sql`; existing patient registration photos are carried forward.

Appointment requests are created as `PENDING`; dietitian decisions change them to `CONFIRMED` or `REJECTED`, and patients can cancel future pending or confirmed appointments. Patients may create an account before joining a dietitian. For an existing PostgreSQL database, apply the status migration once with `python back-end/migrations/apply_001_appointment_approval_states.py`.

Appointment requests use 50-minute visits with a 5-minute buffer, offered in 55-minute slots from 08:00 through 16:15. Clients must choose an initial visit or follow-up. For existing PostgreSQL databases, apply `python back-end/migrations/apply_022_appointment_visit_type.py` to store the visit type.

When a client requests an appointment, the assigned dietitian is emailed the client's name and email and the appointment details. Configure `RESEND_API_KEY` and `RESEND_FROM_EMAIL` on the API server to enable delivery. The appointment is still created if email delivery is unavailable; the response and client UI report that the notification could not be sent.

Appointment check-in QR codes stay on the appointment record and can be scanned only by administrators or the dietitian assigned to the appointment. The camera scanner prefers native QR detection and falls back to the locally bundled jsQR decoder on browsers without `BarcodeDetector`; camera access requires HTTPS and permission from the device. Keyboard QR scanners and manual code entry are also available. The bundled decoder is licensed under Apache-2.0; see `front-end/jsQR-LICENSE.txt`. For existing PostgreSQL deployments, apply `back-end/migrations/023_checkin_actor_roles.sql` after the check-in schema migrations. The deployment workflow applies it automatically.

For running the API outside Compose, set `OLLAMA_BASE_URL` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default `llama3.2`) to match an Ollama instance with the selected model downloaded.

## Admin approvals

Branch managers can inspect, approve, reject, suspend, and restore dietitians in
their assigned branch. Suspension blocks new and existing dietitian sessions
without deleting patient, appointment, or care records; restoration returns the
dietitian to approved status. A reason is required to suspend, and status changes
are recorded in the approval history. Branch managers can also view the account
directory for patients assigned to dietitians at their branch, with branch-only
reports and approval history. They can create and manage reception accounts
within their branch; other branch-manager accounts are visible but read-only.
Patient clinical records, other branches, and organization-wide settings remain
restricted. Before using this with an existing
PostgreSQL database, run `python back-end/migrations/apply_024_branch_manager_approvals.py`.
The deployment workflow applies this migration automatically.

Dietitian registrations use the `PENDING` / `APPROVED` / `REJECTED` workflow. Dietitians add a branch and submit PDF, JPEG, or PNG verification documents up to 10 MB from the **Verification documents** screen. Administrators can review all registrations; branch managers can review and inspect only dietitians assigned to their own branch, including submitted documents, and approve or reject them. Rejection requires a reason, and decisions are recorded in `approval_log`. Other branches and organization-wide administration remain admin-only. Documents remain private and are served through authenticated endpoints.

When the database has no administrator, the **Admin setup** tab appears on the local sign-in page. Create the first admin from this computer; the setup endpoint is loopback-only and becomes unavailable after that account is created. Admin and dietitian document sessions are held in process memory, so sign in again after an API restart.

To provision three local admin accounts, run `python back-end/seed_admin_accounts.py` with `DATABASE_URL` configured. It skips existing seeded accounts, generates random temporary passwords, and prints passwords only for newly created accounts. Store those credentials securely; they are not hard-coded in the source.

## Prototype limits

When `DATABASE_URL` is configured, accounts, patient health records, verification documents, progress, appointments, food catalog entries, meal plans, recipes, and AI reviews use PostgreSQL. For local development, set `DATABASE_URL` in the ignored `.env` file. URL-encode reserved characters in usernames or passwords (for example, encode `@` as `%40`). Docker Compose passes the same variable to the API container; without it, Compose uses the local database service.

Without `DATABASE_URL`, the API uses in-memory data for development and tests. Dietitian document and admin approval endpoints require process-local bearer sessions; other API areas still use prototype authentication. The app is not ready for real patient or clinical data until full authentication and access control are completed.
