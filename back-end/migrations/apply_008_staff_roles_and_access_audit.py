"""Apply locally using explicit credentials: python migrations/apply_008_staff_roles_and_access_audit.py.

Use an isolated LOCAL database. Do not run against Oracle Cloud or production.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

sql = Path(__file__).with_name('008_staff_roles_and_access_audit.sql').read_text(encoding='utf-8')
with database.cursor() as cursor:
    cursor.execute(sql)
print('Staff roles and access audit migration applied.')
