"""Add encrypted Google connections and appointment-specific Meet links."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # Load the repository's database environment.
import database

if __name__ == "__main__":
    with database.cursor() as cursor:
        cursor.execute(Path(__file__).with_name("019_google_meet.sql").read_text())
    print("Google Meet migration applied.")
