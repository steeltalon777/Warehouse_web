from __future__ import annotations

import time
import uuid

import structlog
from django.http import HttpRequest

logger = structlog.get_logger(__name__)


class RequestTracingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.META["X_REQUEST_ID"] = request_id
        request.META["SYNC_CALL_COUNT"] = 0

        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.error(
                "http_request",
                method=request.method,
                path=request.path,
                status_code=500,
                duration_ms=duration_ms,
                request_id=request_id,
                exc_info=True,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        status_code = response.status_code

        if status_code >= 500:
            logger.error(
                "http_request",
                method=request.method,
                path=request.path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
        elif status_code >= 400:
            logger.warning(
                "http_request",
                method=request.method,
                path=request.path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
        else:
            logger.info(
                "http_request",
                method=request.method,
                path=request.path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )

        response["X-Request-Id"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response