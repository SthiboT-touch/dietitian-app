"""Prometheus metrics for the API.

Labels use route templates only (never real URLs), so patient identifiers and
query strings cannot end up in metrics, and the number of label values stays
bounded.
"""

import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "nutricare_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "nutricare_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
_SKIPPED_ROUTES = {"/metrics", "/health"}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) and template.startswith("/") else "<unmatched>"


async def collect_metrics(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = _route_template(request)
        if route not in _SKIPPED_ROUTES:
            REQUESTS.labels(request.method, route, str(status)).inc()
            LATENCY.labels(request.method, route).observe(time.perf_counter() - started)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)