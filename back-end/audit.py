"""Minimal sensitive API access event trail.

Never log request bodies, passwords, bearer tokens, or clinical response data.
Audit writes are best-effort for this milestone; a production-grade fail-closed,
transactional audit implementation and retention policies remain future work.
"""

import logging
import uuid
from datetime import datetime, timezone
from fastapi import Request
from starlette.concurrency import run_in_threadpool

import config
import database
from state import access_audit_events_db

logger = logging.getLogger(__name__)


def _is_sensitive_path(path: str) -> bool:
    # The public setup-status probe is requested before users have signed in.
    if path == "/api/v1/admin/setup-status":
        return False
    return (
        path.startswith("/api/v1/clients/")
        or path == "/api/v1/clients"
        or path.startswith("/api/v1/appointments")
        or path.startswith("/api/v1/reception/")
        or path.startswith("/api/v1/goals")
        or path.startswith("/api/v1/admin/")
        or path.startswith("/api/v1/meal-plans/")
        or path.startswith("/api/v1/ai/")
        or path.startswith("/api/v1/dietitians/me/")
        or path.startswith("/api/v1/staff/")
        or path.startswith("/api/v1/support/")
        or path.startswith("/api/v1/admin/audit-logs")
        or path.startswith("/api/v1/admin/access-events")
    )


def _safe_actor(authorization):
    from security import current_identity
    from fastapi import HTTPException

    try:
        return current_identity(authorization)
    except HTTPException:
        return ("anonymous", None)


def record_event(event):
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "INSERT INTO access_audit_event "
                "(event_id, actor_id, actor_role, http_method, resource_path, status_code, occurred_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    event["event_id"],
                    event["actor_id"],
                    event["actor_role"],
                    event["http_method"],
                    event["resource_path"],
                    event["status_code"],
                    event["occurred_at"],
                ),
            )
    else:
        access_audit_events_db.append(event)


def _should_audit_request(path: str, method: str) -> bool:
    """Audit clinical endpoints and catalogue mutations, not public catalogue reads."""
    catalogue_write = path in {"/api/v1/foods", "/api/v1/recipes"} and method != "GET"
    return _is_sensitive_path(path) or catalogue_write


async def audit_sensitive_requests(request: Request, call_next):
    """Capture status and actor for protected API access without modifying the response."""
    if not _should_audit_request(request.url.path, request.method):
        return await call_next(request)
    identity = _safe_actor(request.headers.get("authorization"))
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        # Keep a 500 audit event when an endpoint raises unexpectedly. The
        # outer diagnostics middleware produces the safe client error response.
        event = {
            "event_id": str(uuid.uuid4()),
            "actor_id": identity[1],
            "actor_role": identity[0],
            "http_method": request.method,
            "resource_path": request.url.path[:512],
            "status_code": response.status_code if response is not None else 500,
            "occurred_at": datetime.now(timezone.utc),
        }
        try:
            await run_in_threadpool(record_event, event)
        except Exception as error:
            # Only the exception class is logged; database errors may contain
            # connection details, SQL or clinical identifiers.
            logger.error(
                "Failed to persist access audit event (error_type=%s)", type(error).__name__
            )
