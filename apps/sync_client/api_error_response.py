from django.http import JsonResponse

from apps.sync_client.exceptions import SyncServerAPIError

_FALLBACK_TYPE = "urn:warehouse:problem:sync-error"
_FALLBACK_TITLE = "Ошибка взаимодействия с сервером"
_FALLBACK_CODE = "sync_error"
_FALLBACK_STATUS = 502


def api_error_response(exc: SyncServerAPIError):
    """
    Structured proxy for SyncServer errors in submit-flow.

    - If exc.payload is a JSON object/dict, pass it through unchanged.
    - For None, string, list, or any other non-dict payload, return a fallback envelope.
    - HTTP status: exc.status_code if valid (>= 400, <= 599), else 502.
    - Payload already passed through sanitize_payload in client.py; do not re-sanitize.
    """
    if isinstance(exc.payload, dict) and exc.payload:
        status = exc.status_code if 400 <= (exc.status_code or 0) <= 599 else _FALLBACK_STATUS
        return JsonResponse(exc.payload, status=status)

    return JsonResponse(
        {
            "type": _FALLBACK_TYPE,
            "title": _FALLBACK_TITLE,
            "status": _FALLBACK_STATUS,
            "code": _FALLBACK_CODE,
            "detail": str(exc),
            "errors": [],
        },
        status=_FALLBACK_STATUS,
    )
