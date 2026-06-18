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
    code_map = {
        400: "validation_error",
        401: "auth_error",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
    }
    code = code_map.get(exc.status_code or 0, "sync_error")
    return _error(str(exc), code, status=exc.status_code or 502)


sync_api_error = _handle_sync_error


def _require_root(user) -> bool:
    return is_root(user)


def _require_chief_or_root(user) -> bool:
    return is_root(user) or can_manage_catalog(user)


def _require_storekeeper(user) -> bool:
    return is_root(user) or is_storekeeper(user) or can_manage_catalog(user)
