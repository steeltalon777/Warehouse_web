from typing import Any

import httpx
import structlog
from django.conf import settings
from django.http import JsonResponse

from apps.common.permissions import can_manage_catalog, is_root, is_storekeeper

from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.transport import execute_with_retry, get_sync_client

logger = structlog.get_logger()


def _build_client(request) -> SyncServerClient:
    site_id = (
        request.session.get("active_site")
        or request.session.get("sync_default_site_id")
        or request.session.get("site_id")
        or ""
    )
    return SyncServerClient(
        user_id=request.user.id,
        site_id=site_id,
        request=request,
    )


def _public_get(path: str, params: dict[str, Any] | None = None) -> Any:
    base_url = settings.SYNC_SERVER_URL.rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{base_url}{normalized_path}"

    _retries = int(getattr(settings, "SYNC_SERVER_RETRIES", 2))
    _backoff = float(getattr(settings, "SYNC_SERVER_RETRY_BACKOFF", 0.2))

    def _do_request() -> httpx.Response:
        client = get_sync_client()
        return client.get(
            url,
            params=params,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    try:
        response = execute_with_retry(_do_request, "GET", retries=_retries, backoff=_backoff)
    except httpx.TimeoutException as exc:
        raise SyncServerAPIError(
            "SyncServer did not respond in time.",
            status_code=504,
            method="GET",
            path=normalized_path,
        ) from exc
    except httpx.RequestError as exc:
        raise SyncServerAPIError(
            "SyncServer is unavailable.",
            status_code=503,
            method="GET",
            path=normalized_path,
        ) from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                payload = {"detail": payload}
        except ValueError:
            payload = {"detail": response.text or "SyncServer error"}
        raise SyncServerAPIError(
            str(payload.get("detail") or "SyncServer error"),
            status_code=response.status_code,
            payload=payload,
            method="GET",
            path=normalized_path,
        )

    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except ValueError:
        return {"detail": response.text}


def _ok(data: Any) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data})


def json_error(message: str, status: int = 500) -> JsonResponse:
    """Shortcut: error response with no code field, just message."""
    return JsonResponse({"ok": False, "error": message}, status=status)


def _error(message: str, code: str = "error", status: int = 400) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _extract_pagination(request) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in ("page", "page_size", "limit", "offset"):
        val = request.GET.get(key)
        if val is not None:
            params[key] = val
    return params


def _handle_sync_error(exc: SyncServerAPIError) -> JsonResponse:
    """Convert SyncServer failure to a BFF error response, preserving structure.

    TZ-V3.2 stage C5 contract: structured ``detail`` dicts from SyncServer
    (e.g. ``{"code": "operation_version_conflict", "current_version": 4}``)
    must reach Angular without string parsing. We unwrap the SyncServer
    payload and surface as much as possible:

    - ``code`` — Stable top-level code; defaults are mapped from HTTP status
      but a SyncServer-provided ``code`` always wins.
    - ``detail`` — Structured dict if SyncServer sent a dict, else raw string.
    - ``fields`` — Forwarded as-is for the 422-validation-style contracts.
    - ``current_version`` / ``request_id`` — Surfaced at top level for 409s.
    - ``status`` — Surfaced if provided by SyncServer (operations, balance).
    """
    code_map = {
        400: "validation_error",
        401: "auth_error",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
    }

    status_code = exc.status_code or 502
    payload = exc.payload if isinstance(exc.payload, dict) else {}

    # SyncServer may send {"detail": {...}} or {"detail": "msg"} or {"code": ..., "detail": ...}.
    raw_detail = payload.get("detail", payload)
    if isinstance(raw_detail, dict):
        detail_obj: Any = dict(raw_detail)
        if "code" in detail_obj and isinstance(detail_obj.get("code"), str):
            code = detail_obj["code"]
        else:
            code = code_map.get(status_code, "sync_error")
        message = (
            detail_obj.get("message")
            or detail_obj.get("detail")
            or str(detail_obj)
        )
    elif raw_detail:
        code = code_map.get(status_code, "sync_error")
        message = str(raw_detail)
        detail_obj = None
    else:
        code = code_map.get(status_code, "sync_error")
        message = str(exc) or "SyncServer error"
        detail_obj = None

    error_body: dict[str, Any] = {"code": code, "message": message}

    # Forward structured contract fields transparently.
    for passthrough_key in (
        "fields",
        "current_version",
        "request_id",
        "status",
        "retry_safe",
    ):
        if passthrough_key in payload:
            error_body[passthrough_key] = payload[passthrough_key]
    if isinstance(detail_obj, dict):
        # Detail carries its own structured contract; expose nested fields too.
        for passthrough_key in (
            "code",
            "fields",
            "current_version",
            "request_id",
            "status",
            "retry_safe",
        ):
            if passthrough_key in detail_obj and passthrough_key not in error_body:
                error_body[passthrough_key] = detail_obj[passthrough_key]
        # Finally, store the raw structured detail for clients that want it.
        if "detail" not in error_body:
            error_body["detail"] = detail_obj

    return JsonResponse(
        {"ok": False, "error": error_body},
        status=status_code,
    )


sync_api_error = _handle_sync_error


def _require_root(user) -> bool:
    return is_root(user)


def _require_chief_or_root(user) -> bool:
    return is_root(user) or can_manage_catalog(user)


def _require_storekeeper(user) -> bool:
    return is_root(user) or is_storekeeper(user) or can_manage_catalog(user)
