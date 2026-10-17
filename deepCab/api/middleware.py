"""ASGI middleware:
- RequestIDMiddleware: stamps `X-Request-Id` in / out; threaded through structlog contextvars.
- PromMiddleware: increments http_request_duration_seconds histogram per request.

OTel auto-instrumentation and the unhandled-exception JSON handler are wired
in `app.create_app()`."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from deepCab.obs.prom import http_request_duration_seconds

# Client-supplied request ids are echoed back and bound into every log line,
# so only short, plain tokens are trusted; anything else gets a fresh id.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
# Unmatched requests (404 scans) share ONE route label: labelling by raw URL
# path would mint a new Prometheus series per probed path (unbounded growth).
_UNMATCHED_ROUTE = "<unmatched>"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or ""
        if not _REQUEST_ID_RE.fullmatch(rid):
            rid = uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


class PromMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        http_request_duration_seconds.labels(
            method=request.method,
            route=request.scope.get("route").path
            if request.scope.get("route") is not None
            else _UNMATCHED_ROUTE,
            status=str(response.status_code),
        ).observe(elapsed)
        return response
