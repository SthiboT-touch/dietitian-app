"""Apply migration 011 to your LOCAL development database only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
sql = Path(__file__).with_name("011_registration_welcome_outbox.sql").read_text()
with database.cursor() as cursor:
    cursor.execute(sql)
print("Local migration 011 applied successfully")
