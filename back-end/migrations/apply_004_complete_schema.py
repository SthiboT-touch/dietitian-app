"""Create any tables, indexes and seed rows from dietitainDB.sql that an older database is missing.

Safe to run repeatedly: existing tables and rows are left untouched.
"""
from pathlib import Path
import re
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import app  # noqa: F401
import database


schema = (BACKEND_DIR / "dietitainDB.sql").read_text(encoding="utf-8")
schema = re.sub(r"\bCREATE TABLE (?!IF NOT EXISTS)", "CREATE TABLE IF NOT EXISTS ", schema)
schema = re.sub(r"\bCREATE INDEX (?!IF NOT EXISTS)", "CREATE INDEX IF NOT EXISTS ", schema)
schema = re.sub(r"(\bINSERT INTO\b[^;]*?)\s*;", r"\1 ON CONFLICT DO NOTHING;", schema)

starter_foods = """
INSERT INTO food_item (name, calories, protein, carbs, fat, glycemic_index)
SELECT v.* FROM (VALUES
    ('Oatmeal', 150, 5.0, 27.0, 3.0, 55),
    ('Grilled Chicken Breast', 165, 31.0, 0.0, 3.6, 0)
) AS v(name, calories, protein, carbs, fat, glycemic_index)
WHERE NOT EXISTS (SELECT 1 FROM food_item f WHERE LOWER(f.name) = LOWER(v.name));
"""

with database.cursor() as cursor:
    cursor.execute(schema)
    cursor.execute(starter_foods)

print("Complete schema migration applied.")
