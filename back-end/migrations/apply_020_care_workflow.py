"""Apply care history, branch/consultation selection, goals and QR appointment links."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: F401,E402
import database  # noqa: E402

if __name__ == "__main__":
    with database.cursor() as cursor:
        cursor.execute(Path(__file__).with_name("020_care_workflow.sql").read_text(encoding="utf-8"))
    print("Care workflow migration applied.")
