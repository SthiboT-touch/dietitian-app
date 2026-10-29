set -Eeuo pipefail
phase='locate server checkout'
trap 'code=$?; echo "::error::Deployment failed during: $phase (exit $code)"; exit "$code"' ERR
cd ~/dietitian-app_2
phase='fetch app updates'
git fetch origin main
git reset --hard FETCH_HEAD
phase='validate Docker Compose configuration'
docker compose config --quiet
phase='start database'
docker compose up -d --build db
for attempt in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U black -d dietitian_db; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Database did not become ready" >&2
    exit 1
  fi
  sleep 2
done
phase='back up database'
mkdir -p backups
docker compose exec -T db pg_dump -U black -d dietitian_db -Fc > "backups/pre-deploy-$(date +%Y%m%d-%H%M%S).dump"
phase='build API image'
docker compose build api
phase='apply database migrations'
docker compose run --rm --no-deps api python migrations/apply_002_client_health_schema.py
docker compose run --rm --no-deps api python migrations/apply_003_dietitian_document_branch.py
docker compose run --rm --no-deps api python migrations/apply_004_lactation_tracking.py
docker compose run --rm --no-deps api python migrations/apply_005_client_identity_gender.py
docker compose run --rm --no-deps api python migrations/apply_006_client_documents_and_meals.py
docker compose run --rm --no-deps api python migrations/apply_007_onboarding_consent.py
docker compose run --rm --no-deps api python migrations/apply_008_staff_roles.py
docker compose run --rm --no-deps api python migrations/apply_009_centralized_client_management.py
docker compose run --rm --no-deps api python migrations/apply_010_popia_consent_details.py
docker compose run --rm --no-deps api python migrations/apply_011_stytch_email_verification.py
for migration in 007_meal_plan_review 008_staff_roles_and_access_audit 009_client_registration_phone 010_client_registration_consent 011_registration_welcome_outbox 012_registration_uploads 013_client_qr_checkin 014_assisted_registration; do
  docker compose exec -T db psql -U black -d dietitian_db -v ON_ERROR_STOP=1 < "back-end/migrations/${migration}.sql"
done
docker compose run --rm --no-deps api python migrations/apply_015_support_tickets.py
docker compose run --rm --no-deps api python migrations/apply_016_guest_support.py
docker compose run --rm --no-deps api python migrations/apply_017_appointment_bound_checkin.py
docker compose run --rm --no-deps api python migrations/apply_018_virtual_appointments.py
docker compose run --rm --no-deps api python migrations/apply_019_care_reviews.py
docker compose run --rm --no-deps api python migrations/apply_020_account_profiles.py
phase='restart application'
docker compose up -d --build
phase='verify API health'
for attempt in $(seq 1 30); do
  if docker compose exec -T api python -c 'import urllib.request,json; h=json.load(urllib.request.urlopen("http://localhost:8000/health")); assert h["database"] == "online"'; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "API health check did not pass" >&2
    exit 1
  fi
  sleep 3
done
