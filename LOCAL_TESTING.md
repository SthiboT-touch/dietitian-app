# NutriCare local testing (PowerShell in VS Code)

**Never run the production GitHub workflow to troubleshoot locally.** Never use
`docker compose down -v`; it deletes local database volumes. Do not deploy
`APP_USE_IN_MEMORY_DB=1`, which is intended for mock-data testing.

1. Keep the existing `.env` (not tracked by Git); verify `DB_PASSWORD` matches
   the password in the **local** PostgreSQL database. `.env.example` is a template.
2. Run `docker compose config --quiet` then `docker compose up -d --build`.
3. Run `docker compose ps`.
4. Check `docker compose exec api python -c "import database; c=database.open_connection(); print('DB OK'); c.close()"`.
5. Visit `http://localhost/health`: database should say `online`, not `offline`
   or `in_memory` for the production-style test.
6. Run `docker compose logs --tail=80 api` to diagnose API errors. Do not paste
   credential values or patient information into issues or chat.
7. Run `docker compose exec api python -c "from routers.ai import _create_chat_model; print(_create_chat_model().invoke('Respond OK.').content)"` to test Ollama.
8. Test meal-plan review and retrieval with fictional patients, then check
   LangSmith only if the local container has its own authorized API key.

### Known limitation

Updating `DB_PASSWORD` in `.env` does **not** update an already initialized
PostgreSQL role. If the database reports `password authentication failed`,
stop and investigate credentials rather than reset/delete volumes. This release
makes authentication failures more diagnosable; it does not prove that your
existing local password is correct.

### Production safety

A push to `main` currently runs `.github/workflows/deploy.yml`, including
container restarts and migrations on Oracle Cloud. Review and back up the
production database before authorizing such a push.
