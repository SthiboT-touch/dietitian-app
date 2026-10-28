"""Add contact addresses for support requests submitted before sign-in."""

from pathlib import Path
import sys

backend_folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_folder))
import config  # noqa: F401,E402
import database  # noqa: E402

if __name__ == "__main__":
    # Read the SQL file beside this script, then run it in one transaction.
    sql_file = Path(__file__).with_name("016_guest_support.sql")
    sql_commands = sql_file.read_text(encoding="utf-8")

    with database.cursor() as cursor:
        cursor.execute(sql_commands)
    print("Guest support migration applied.")
