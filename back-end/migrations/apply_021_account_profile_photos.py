"""Apply role-scoped profile photo storage to an existing PostgreSQL database."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402
import database  # noqa: E402


if __name__ == "__main__":
    migration = Path(__file__).with_name("021_account_profile_photos.sql")
    with database.cursor() as cursor:
        cursor.execute(migration.read_text(encoding="utf-8"))
    print("Account profile photos migration applied.")
