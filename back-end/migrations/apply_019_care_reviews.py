"""Apply additive clinician follow-up review table to a LOCAL database only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

sql = Path(__file__).with_name("019_care_reviews.sql").read_text(encoding="utf-8")
with database.cursor() as cursor:
    cursor.execute(sql)
print("Migration 019 applied: care_review table")
