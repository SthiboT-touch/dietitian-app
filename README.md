# Dietitian & Nutrition Management

The browser app is served by the API at `http://localhost:8000` when running with Docker Compose. The interactive API documentation is at `http://localhost:8000/docs`.

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

## Run with Llama

Start the API, database, and Ollama service:

```powershell
docker compose up --build -d
docker compose exec ollama ollama pull llama3.2
```

The model download is several gigabytes and is stored in the `ollama_data` volume. The API uses `llama3.2` by default. To select another model, set `OLLAMA_MODEL` in a `.env` file before starting Compose, then pull that model with `docker compose exec ollama ollama pull <model>`.

The API container connects to Ollama at `http://ollama:11434` over the Compose network and waits for the Ollama service to become healthy. If the AI still cannot reply, confirm the model is installed with `docker compose exec ollama ollama list`, then pull it if needed with `docker compose exec ollama ollama pull llama3.2`. Rebuild and restart the API after changing its configuration with `docker compose up --build -d api`.

The generated-plan endpoint is `POST /api/v1/ai/generate-plan` with a JSON body such as:

```json
{
  "client_id": "client-123",
  "dietary_goal": "More fiber and balanced meals"
}
```

The API sends the goal and any recorded allergies and medical conditions to Ollama. Recommendations remain `PENDING_REVIEW` until approved by a dietitian. These suggestions are not a substitute for clinical judgment.

Plan generation uses a LangChain prompt/model/output-parser chain with `ChatOllama`; chat uses a LangChain agent with read-only food-catalog search and includes up to eight recent turns as short-term context. Chat history is held in process memory and is cleared when the API restarts. Generated plans remain pending until reviewed by a dietitian. The routes and response shapes stay the same; LangChain dependencies are installed from `back-end/requirements.txt`.

Appointment requests are created as `PENDING`; dietitian decisions change them to `CONFIRMED` or `REJECTED`, and patients can cancel future pending or confirmed appointments. Patients may create an account before joining a dietitian. For an existing PostgreSQL database, apply the status migration once with `python back-end/migrations/apply_001_appointment_approval_states.py`.

For running the API outside Compose, set `OLLAMA_BASE_URL` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default `llama3.2`) to match an Ollama instance with the selected model downloaded.

## Admin approvals

When the database has no administrator, the **Admin setup** tab appears on the local sign-in page. Create the first admin from this computer; the setup endpoint is loopback-only and becomes unavailable after that account is created. Dietitians can upload PDF, JPEG, or PNG verification documents up to 10 MB from the **Verification documents** screen. Admins can preview them before approving or rejecting a registration; decisions and notes are recorded in `approval_log`. Admin and dietitian document sessions are held in process memory, so sign in again after an API restart.

To provision three local admin accounts, run `python back-end/seed_admin_accounts.py` with `DATABASE_URL` configured. It skips existing seeded accounts, generates random temporary passwords, and prints passwords only for newly created accounts. Store those credentials securely; they are not hard-coded in the source.

## Prototype limits

When `DATABASE_URL` is configured, accounts, patient health records, verification documents, progress, appointments, food catalog entries, meal plans, recipes, and AI reviews use PostgreSQL. For local development, set `DATABASE_URL` in the ignored `.env` file. URL-encode reserved characters in usernames or passwords (for example, encode `@` as `%40`). Docker Compose passes the same variable to the API container; without it, Compose uses the local database service.

Without `DATABASE_URL`, the API uses in-memory data for development and tests. Dietitian document and admin approval endpoints require process-local bearer sessions; other API areas still use prototype authentication. The app is not ready for real patient or clinical data until full authentication and access control are completed.
