"""Apply FR-1.3 migration to a LOCAL PostgreSQL DB only.

Run explicitly after migration 009:
    docker compose exec api python migrations/apply_010_client_registration_consent.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

sql = Path(__file__).with_name("010_client_registration_consent.sql").read_text()
with database.cursor() as cursor:
    cursor.execute(sql)
print("Applied migration 010: client_registration_consent is available")
