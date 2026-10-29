"""Apply local-only migration 017. Never run on production without approval."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

migration = Path(__file__).with_name("017_appointment_bound_checkin.sql")
with database.cursor() as cursor:
    cursor.execute(migration.read_text())
print("Local migration 017 applied: check-in QR codes now require an appointment")
