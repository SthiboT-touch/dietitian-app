"""Local HPCSA checks; these do not establish registration with the council."""

import re
from datetime import date, datetime, timedelta, timezone

from fastapi import Header, HTTPException


def today():
    # South Africa is UTC+02:00 year round; no OS timezone database is required.
    return datetime.now(timezone(timedelta(hours=2))).date()


def normalize_hpcsa_number(value: str) -> str:
    number = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"DT[0-9]{5,8}", number):
        raise ValueError("Use an HPCSA dietitian number: DT followed by 5 to 8 digits")
    return number


def validate_card_expiry(value: date) -> date:
    current = today()
    annual_end = date(current.year + (current.month > 3), 3, 31)
    if value != annual_end:
        raise ValueError(f"Use the current practising-card expiry date ({annual_end.isoformat()})")
    return value


def verification_is_current(record) -> bool:
    if not record or record.get("status") != "APPROVED":
        return False
    expiry = record.get("hpcsa_verified_until")
    if isinstance(expiry, str):
        expiry = date.fromisoformat(expiry)
    return bool(expiry and expiry >= today())


def require_current_verification(authorization: str | None = Header(default=None)):
    """Recheck each clinical request, including sessions issued before expiry."""
    import config
    import database
    from state import dietitian_sessions_db, users_db

    scheme, _, token = (authorization or "").partition(" ")
    dietitian_id = dietitian_sessions_db.get(token) if scheme.lower() == "bearer" else None
    if not dietitian_id:
        return  # The route's role/ownership dependency handles other callers.
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT status, hpcsa_verified_until FROM dietitian WHERE dietitian_id = %s",
                (dietitian_id,),
            )
            record = cursor.fetchone()
    else:
        record = users_db.get(dietitian_id)
    if not verification_is_current(record):
        raise HTTPException(403, "Current HPCSA verification is required. Submit your practising card for admin review.")
