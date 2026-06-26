"""HTTP middleware for request tracing and access logs."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from intersection_agent.logging.context import set_request_id
from intersection_agent.logging.helpers import log_event, safe_preview

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log inbound HTTP requests and responses with timing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with request_id and access log."""
        header_rid = request.headers.get("X-Request-ID")
        rid = set_request_id(header_rid or str(uuid.uuid4()))
        started = time.perf_counter()

        log_event(
            logger,
            logging.INFO,
            "http.request",
            method=request.method,
            path=request.url.path,
            query=safe_preview(str(request.query_params), 200),
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            log_event(
                logger,
                logging.ERROR,
                "http.error",
                method=request.method,
                path=request.url.path,
                elapsed_ms=elapsed_ms,
                error=type(exc).__name__,
                detail=safe_preview(str(exc), 300),
            )
            raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = rid
        log_event(
            logger,
            logging.INFO,
            "http.response",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        return response
