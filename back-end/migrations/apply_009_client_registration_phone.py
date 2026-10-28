"""Apply additive FR-1.2 phone migration to the LOCAL development DB only.

Run explicitly from the local API container after reviewing the SQL:
    docker compose exec api python migrations/apply_009_client_registration_phone.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

sql = (Path(__file__).with_name("009_client_registration_phone.sql")).read_text()
with database.cursor() as cursor:
    cursor.execute(sql)
print("Applied migration 009: client.phone is available")
