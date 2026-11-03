"""Apply additive medical history and appointment workflow schema."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # Load the repository's database environment.
import database

if __name__ == "__main__":
    with database.cursor() as cursor:
        cursor.execute(Path(__file__).with_name("017_care_workflow.sql").read_text())
    print("Care workflow migration applied.")
