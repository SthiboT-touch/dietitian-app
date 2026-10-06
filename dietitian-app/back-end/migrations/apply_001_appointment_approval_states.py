from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app  # noqa: F401
import database


migration_path = Path(__file__).with_name("001_appointment_approval_states.sql")
with database.cursor() as cursor:
    cursor.execute(migration_path.read_text(encoding="utf-8"))

print("Appointment approval states migration applied.")
