"""Access-event visibility for authorized audit reviewers.

Distinct from the existing administrator's dietitian approval history.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

import config
import database
from role_management import require_roles
from state import access_audit_events_db

router = APIRouter(tags=["Access Auditing"])


@router.get("/api/v1/admin/access-events")
def list_access_events(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor_role: Optional[str] = None,
    identity=Depends(require_roles("admin", "compliance_officer")),
):
    """Paged, read-only audit trail without request bodies or session tokens."""
    if config.DATABASE_ENABLED:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, actor_id, actor_role, http_method, resource_path, "
                "status_code, occurred_at FROM access_audit_event "
                "WHERE (%s IS NULL OR actor_role = %s) "
                "ORDER BY occurred_at DESC, event_id DESC LIMIT %s OFFSET %s",
                (actor_role, actor_role, limit, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        return rows
    filtered = [
        event for event in access_audit_events_db
        if actor_role is None or event["actor_role"] == actor_role
    ]
    return sorted(
        filtered, key=lambda e: (e["occurred_at"], e["event_id"]), reverse=True
    )[offset:offset + limit]
