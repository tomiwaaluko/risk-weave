"""Structured request/error logging middleware (RIS-33).

Logs one JSON line per HTTP request — method, path, status, duration_ms,
request_id — and one additional line with the traceback for unhandled
exceptions (5xx), so a Railway log-based alert on `level=ERROR` or on
`status>=500` catches production failures instead of them going silent.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import set_request_id

logger = logging.getLogger("riskweave_api.request")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        set_request_id(request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            logger.exception(
                "unhandled exception",
                extra={
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "duration_ms": round(duration_ms, 2),
                        "request_id": request_id,
                    }
                },
            )
            set_request_id(None)
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["x-request-id"] = request_id
        logger.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "request_id": request_id,
                }
            },
        )
        set_request_id(None)
        return response
