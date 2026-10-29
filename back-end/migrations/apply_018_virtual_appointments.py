"""Apply virtual appointment columns to a LOCAL development database only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

sql = Path(__file__).with_name("018_virtual_appointments.sql").read_text()
with database.cursor() as db_cursor:
    db_cursor.execute(sql)
print("Local migration 018 applied: consultation_type and virtual_room_id")
