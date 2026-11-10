"""Meeting links using the existing appointment fields; no provider API calls."""

import secrets
from threading import RLock


ACTIVE_MEETING_STATUSES = {"CONFIRMED", "SCHEDULED"}
meeting_lock = RLock()  # In-memory development mode; PostgreSQL uses row locks.


def is_virtual(appointment):
    return (appointment.get("appointment_type") == "VIRTUAL"
            or appointment.get("consultation_type") == "VIRTUAL")


def ensure_meeting_link(appointment, supplied_link=None):
    """Persist one unpredictable room per appointment; retries reuse its link."""
    with meeting_lock:
        if not is_virtual(appointment):
            return None
        link = supplied_link or appointment.get("meeting_link")
        if not link:
            # Never place patient names, clinical data or record IDs in room URLs.
            link = "https://meet.jit.si/NutriCare-" + secrets.token_hex(32)
        appointment["meeting_link"] = link
        return link


def public_appointment(appointment, identity=None):
    """Inactive meetings and nonparticipants do not receive join links."""
    result = dict(appointment)
    participant = identity is None or (
        identity[0] == "client" and str(result.get("client_id")) == identity[1]
    ) or (
        identity[0] == "dietitian" and str(result.get("dietitian_id")) == identity[1]
    )
    if not participant or not is_virtual(result) or result.get("status") not in ACTIVE_MEETING_STATUSES:
        result["meeting_link"] = None
    return result
