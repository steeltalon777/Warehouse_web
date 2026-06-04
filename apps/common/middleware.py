from __future__ import annotations

import uuid

import structlog
from django.http import HttpRequest


class RequestTracingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.META["X_REQUEST_ID"] = request_id
        request.META["SYNC_CALL_COUNT"] = 0

        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = self.get_response(request)

        response["X-Request-Id"] = request_id

        structlog.contextvars.unbind_contextvars("request_id")
        return response