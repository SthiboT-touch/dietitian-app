# NutriCare — local-only temporary-memory test

This is an **isolated local Docker Compose setup** for the latest Patient UI (Settings removed, appointment-linked QR, read-only dietitian-managed goals and meal plans). It **does not connect to PostgreSQL**, **does not create database volumes**, and **does not deploy to Oracle Cloud**.

### Requirements
- Docker Desktop running on Windows
- Free port `8088` on your PC
- The files in this ZIP, extracted into a separate folder

### Start from PowerShell

Open PowerShell in the folder containing `docker-compose.memory.yml`, then run:

```powershell
docker compose -f docker-compose.memory.yml up --build -d
docker compose -f docker-compose.memory.yml ps
Invoke-RestMethod http://127.0.0.1:8088/health
```

The health response should report `status: online` and `database: in_memory`.

Open **http://127.0.0.1:8088** and register a new patient using **fictional** data. Test the Patient sidebar, top-right profile menu, appointments, and the dietitian-controlled goals and meal-plan views. Since memory starts empty, goals and approved meal plans will appear only after you create suitable demo accounts and records.

For developer-only API documentation, open **http://127.0.0.1:8088/api/docs**.

### Inspect errors

```powershell
docker compose -f docker-compose.memory.yml logs --tail=100 api
```

### Stop the test (data is discarded)

```powershell
docker compose -f docker-compose.memory.yml down
```

**Do not use** `docker compose down -v` on the normal production/local database stack. This separate memory-only configuration has no named database volumes and has a distinct project name (`nutricare-memory-test`), so the `down` command above stops only the temporary test services.

### Limitations and safeguards
- All test accounts, sessions, appointments, goals and check-in codes are held **in RAM** and disappear when the API process stops or restarts.
- This environment uses **no PostgreSQL data or migrations**.
- The **AI Coach will not respond** unless an Ollama server is separately connected to this isolated environment; no Ollama is started in this mode.
- External Stytch verification, LangSmith tracing and SMTP welcome delivery are **disabled / not started**.
- A QR appears only for a **confirmed future appointment**, never immediately after registration.
- Patient goals and meal plans remain **read-only**; the assigned dietitian controls goals and plan approval.
- The browser is bound only to `127.0.0.1:8088`, not exposed to the internet. Use **fictional test data**, not real patient records.
- If you already run a different local NutriCare stack, leave it alone; always include `-f docker-compose.memory.yml` in the commands here.

### Troubleshooting

If the browser says it cannot connect, check that Docker Desktop is running, `docker compose -f docker-compose.memory.yml ps` shows both services, and port 8088 is free. If `api` is unhealthy, read the `api` logs before changing anything. If port 8088 is already occupied, change only the `frontend.ports` value in `docker-compose.memory.yml` to another loopback port such as `127.0.0.1:8090:80`.
