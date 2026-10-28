"""Privacy-conscious HTTP diagnostics for NutriCare.

Every request gets an opaque, server-generated ID. Logs deliberately contain
route *templates*, never raw URLs, headers, query strings, patient identifiers,
request bodies, or clinical data. Expected FastAPI 4xx responses keep their
existing response shape for backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class JsonLogFormatter(logging.Formatter):
    """Emit stable machine-readable logs without logging exception strings."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for name in ("request_id", "method", "route", "status", "elapsed_ms", "error_type"):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_diagnostics_logging() -> logging.Logger:
    """Configure only our application logger; do not overwrite server logs."""
    logger = logging.getLogger("nutricare.api")
    level = os.getenv("NUTRICARE_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = configure_diagnostics_logging()


def _safe_route(request: Request) -> str:
    """Use the matched route pattern, never actual patient IDs or query values."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and template.startswith("/") else "<unmatched>"


async def request_diagnostics(request: Request, call_next):
    """Issue a support reference and log HTTP failures without private data."""
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.monotonic()
    error_type = None
    try:
        response = await call_next(request)
    except Exception as error:
        # Never expose exception messages (which may contain SQL, paths or data).
        error_type = type(error).__name__
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "An unexpected server error occurred. Please try again.",
                "request_id": request_id,
            },
        )
    response.headers["X-Request-ID"] = request_id
    duration = round((time.monotonic() - started) * 1000, 1)
    status = response.status_code
    # Keep logs useful but avoid a line per static asset or health poll.
    if status >= 400 or (request.url.path.startswith("/api/") and request.url.path != "/api/openapi.json"):
        logger.log(
            logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO,
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": _safe_route(request),
                "status": status,
                "elapsed_ms": duration,
                **({"error_type": error_type} if error_type else {}),
            },
        )
    return response
