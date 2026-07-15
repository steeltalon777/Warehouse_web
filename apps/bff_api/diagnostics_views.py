"""BFF view for UI diagnostics events (TZ-DIAGNOSTICS_STAGE3 WP-1).

Proxy POST /bff/api/v1/diagnostics/ui-events/batch to SyncServer with:
- Validation (empty batch, invalid event_type, size)
- Rate limit (10 req/min per session)
- Header forwarding (X-Client-Session-Id, X-Request-Id)
"""
from __future__ import annotations

import json
import time

import structlog
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.sync_client.client import get_sync_client

logger = structlog.get_logger()

# Per contract §5.2
MAX_BATCH_BYTES = 100 * 1024
RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SEC = 60

ALLOWED_EVENT_TYPES = frozenset({
    "form_opened",
    "form_closed",
    "submit_clicked",
    "validation_failed",
    "request_started",
    "request_succeeded",
    "request_failed",
    "outcome_unknown",
    "response_processing_failed",
    "navigation_away_with_unsaved",
    "unexpected_error",
})


@csrf_exempt
@require_POST
def diagnostics_batch_view(request: HttpRequest) -> JsonResponse:
    """Receive a batch of UI diagnostic events and proxy to SyncServer."""
    # 1. Size check (per contract §5.2)
    content_length = request.META.get("CONTENT_LENGTH")
    if content_length is not None:
        try:
            if int(content_length) > MAX_BATCH_BYTES:
                return JsonResponse(
                    {"ok": False, "error": {"code": "batch_too_large", "message": "batch > 100 KB"}},
                    status=413,
                )
        except ValueError:
            pass

    # 2. Parse and validate body
    try:
        raw = request.body.decode("utf-8")
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return JsonResponse(
            {"ok": False, "error": {"code": "invalid_json", "message": str(exc)[:200]}},
            status=400,
        )

    events = payload.get("events")
    if not isinstance(events, list) or len(events) == 0:
        return JsonResponse(
            {"ok": False, "error": {"code": "empty_batch", "message": "events must be a non-empty list"}},
            status=400,
        )

    for ev in events:
        if not isinstance(ev, dict):
            return JsonResponse(
                {"ok": False, "error": {"code": "invalid_event", "message": "event must be a dict"}},
                status=400,
            )
        et = ev.get("event_type")
        if et not in ALLOWED_EVENT_TYPES:
            return JsonResponse(
                {"ok": False, "error": {"code": "invalid_event_type", "message": f"event_type '{et}' is not allowed"}},
                status=400,
            )

    # 3. Rate limit per session (X-Client-Session-Id OR Django session key)
    scope_id = (
        request.headers.get("X-Client-Session-Id")
        or request.session.session_key
        or "anonymous"
    )
    cache_key = f"diag_ratelimit:{scope_id}"
    count = cache.get(cache_key, 0)
    if count >= RATE_LIMIT_REQUESTS:
        return JsonResponse(
            {"ok": False, "error": {"code": "rate_limited", "message": "too many requests"}},
            status=429,
        )
    # Increment with TTL = window. Use add() to handle missing key.
    if count == 0:
        cache.set(cache_key, 1, RATE_LIMIT_WINDOW_SEC)
    else:
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, RATE_LIMIT_WINDOW_SEC)

    # 4. Proxy to SyncServer
    sync_url = settings.SYNC_SERVER_URL.rstrip("/") + "/api/v1/diagnostics/ui-events/batch"
    forward_headers = {
        "Content-Type": "application/json",
        "X-User-Token": request.headers.get("X-User-Token", ""),
        "X-Client-Session-Id": request.headers.get("X-Client-Session-Id", ""),
    }
    request_id = request.headers.get("X-Request-Id") or request.META.get("HTTP_X_REQUEST_ID", "")
    if request_id:
        forward_headers["X-Request-Id"] = request_id

    try:
        client = get_sync_client()
        response = client.post(sync_url, content=raw, headers=forward_headers, timeout=10)
        response.raise_for_status()
    except Exception as exc:  # httpx.HTTPError, connection errors, etc.
        logger.warning("diagnostics_proxy_failed", error=str(exc)[:200])
        # Per contract §5.4: do not retry on the client, do not fail the
        # user's flow — but we MUST tell the client that the batch was
        # rejected so it can stop. Return 502 (BFF itself is OK, upstream failed).
        return JsonResponse(
            {"ok": False, "error": {"code": "upstream_unavailable", "message": "SyncServer rejected the batch"}},
            status=502,
        )

    # 5. Return 204 No Content (BFF never returns a body)
    return JsonResponse({}, status=204)
