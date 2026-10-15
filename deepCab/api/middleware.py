"""ASGI middleware:
- RequestIDMiddleware: stamps `X-Request-Id` in / out; threaded through structlog contextvars.
- PromMiddleware: increments http_request_duration_seconds histogram per request.

OTel auto-instrumentation and the unhandled-exception JSON handler are wired
in `app.create_app()`."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from deepCab.obs.prom import http_request_duration_seconds


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Propagate or generate `X-Request-Id` and bind it to the structlog context."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Handle one request and echo the request id in the response headers."""
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


class PromMiddleware(BaseHTTPMiddleware):
    """Record request latency in the `http_request_duration_seconds` histogram."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Time one request, labelled by method, route path and status code."""
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        http_request_duration_seconds.labels(
            method=request.method,
            route=request.scope.get("route").path
            if request.scope.get("route") is not None
            else request.url.path,
            status=str(response.status_code),
        ).observe(elapsed)
        return response
