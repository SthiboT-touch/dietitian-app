"""Authoritative appointment context for post-consultation care."""
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
import config
import database
from state import appointments_db


def completed_consultation(client_id, dietitian_id, appointment_id=None):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT appointment_id FROM appointment WHERE client_id=%s AND dietitian_id=%s "
                "AND status='COMPLETED' AND date_time <= (NOW() AT TIME ZONE 'Africa/Johannesburg') "
                "AND (%s IS NULL OR appointment_id=%s) ORDER BY date_time DESC LIMIT 1",
                (client_id, dietitian_id, appointment_id, appointment_id),
            )
            row = cursor.fetchone()
        if row:
            return str(row["appointment_id"])
    else:
        matches = []
        local_timezone = timezone(timedelta(hours=2))
        for row in appointments_db.values():
            if row.get("client_id") != client_id or row.get("dietitian_id") != dietitian_id or row.get("status") != "COMPLETED":
                continue
            if appointment_id and row["appointment_id"] != appointment_id:
                continue
            when = datetime.fromisoformat(row["appointment_date"].replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=local_timezone)
            if when <= datetime.now(timezone.utc):
                matches.append((when, row["appointment_id"]))
        if matches:
            return max(matches)[1]
    raise HTTPException(409, "Complete this patient's consultation before creating or approving care. Choose a completed appointment with the assigned dietitian.")
