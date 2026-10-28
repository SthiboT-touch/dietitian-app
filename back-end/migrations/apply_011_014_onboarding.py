"""Safely apply FR-1.5 through FR-1.8 migrations to LOCAL PostgreSQL.

Prerequisites: migrations 008, 009, 010 already applied. Do not run on
Oracle Cloud or production without explicit authorization and a backup.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database

folder = Path(__file__).parent
names = [
    "011_registration_welcome_outbox.sql",
    "012_registration_uploads.sql",
    "013_client_qr_checkin.sql",
    "014_assisted_registration.sql",
]
# Transactional: if any migration fails, the database connection rolls back.
with database.cursor() as cursor:
    for name in names:
        cursor.execute((folder / name).read_text())
print("Applied local onboarding migrations 011 through 014")
