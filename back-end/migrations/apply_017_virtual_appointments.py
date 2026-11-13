"""Add support for virtual appointments."""

from pathlib import Path
import sys

backend_folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_folder))
import config  # noqa: F401,E402
import database  # noqa: E402

if __name__ == "__main__":
    sql_file = Path(__file__).with_name("017_virtual_appointments.sql")
    sql_commands = sql_file.read_text(encoding="utf-8-sig")

    with database.cursor() as cursor:
        cursor.execute(sql_commands)

    print("Virtual appointments migration applied.")
