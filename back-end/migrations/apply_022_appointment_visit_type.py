"""Add a visit type to appointments."""

from pathlib import Path
import sys

backend_folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_folder))
import config  # noqa: F401,E402
import database  # noqa: E402

if __name__ == "__main__":
    sql_file = Path(__file__).with_name("022_appointment_visit_type.sql")
    with database.cursor() as cursor:
        cursor.execute(sql_file.read_text(encoding="utf-8"))
    print("Appointment visit type migration applied.")
