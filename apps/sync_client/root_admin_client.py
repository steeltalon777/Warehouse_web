from __future__ import annotations

import structlog
import time
from typing import Any

import httpx
from django.conf import settings

from .exceptions import (
    SyncAuthError,
    SyncBackendUnavailable,
    SyncConflictError,
    SyncForbiddenError,
    SyncNotFoundError,
    SyncServerAPIError,
    SyncServerInternalError,
    SyncValidationError,
)
from .redaction import sanitize_payload
from .token_resolver import get_device_token
from .transport import execute_with_retry, get_sync_client

logger = structlog.get_logger()


class SyncServerRootAdminClient:
    """
    Root-token SyncServer client for Django-admin management operations.

    This client is for Django staff/superuser admin or system jobs only.
    It must not be exposed to browser-facing BFF endpoints for ordinary users.
    """

    def __init__(self) -> None:
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = float(getattr(settings, "SYNC_SERVER_TIMEOUT", 10))
        self.device_token = get_device_token()
        self.root_user_token = getattr(settings, "SYNC_ROOT_USER_TOKEN", "").strip()

        if not self.base_url.endswith("/api/v1"):
            raise RuntimeError(
                "SYNC_SERVER_URL must include '/api/v1'. "
                f"Current value: {self.base_url}"
            )
        if not self.root_user_token:
            raise RuntimeError("SYNC_ROOT_USER_TOKEN is not configured.")

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-User-Token": self.root_user_token,
        }
        if self.device_token:
            headers["X-Device-Token"] = self.device_token
        return headers

    def _normalize_path(self, path: str) -> str:
        if not path:
            return "/"
        return path if path.startswith("/") else f"/{path}"

    def _extract_payload(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"detail": payload}
        except ValueError:
            return {"detail": response.text or "SyncServer error"}

    def _raise_for_response(self, response: httpx.Response, *, method: str, path: str) -> None:
        payload = self._extract_payload(response)
        sanitized = sanitize_payload(payload)
        message = str(sanitized.get("detail") or "SyncServer error")
        kwargs = {
            "status_code": response.status_code,
            "payload": sanitized,
            "method": method,
            "path": path,
        }

        if response.status_code in (400, 422):
            raise SyncValidationError(message, **kwargs)
        if response.status_code == 401:
            raise SyncAuthError(message, **kwargs)
        if response.status_code == 403:
            raise SyncForbiddenError(message, **kwargs)
        if response.status_code == 404:
            raise SyncNotFoundError(message, **kwargs)
        if response.status_code == 409:
            raise SyncConflictError(message, **kwargs)
        if response.status_code >= 500:
            raise SyncServerInternalError(message, **kwargs)
        raise SyncServerAPIError(message, **kwargs)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        normalized_path = self._normalize_path(path)
        url = f"{self.base_url}{normalized_path}"
        headers = self._build_headers()

        _t0 = time.perf_counter()

        _retries = int(getattr(settings, "SYNC_SERVER_RETRIES", 2))
        _backoff = float(getattr(settings, "SYNC_SERVER_RETRY_BACKOFF", 0.2))

        def _do_request() -> httpx.Response:
            client = get_sync_client()
            return client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                params=params,
            )

        try:
            response = execute_with_retry(_do_request, method, retries=_retries, backoff=_backoff)
        except httpx.TimeoutException as exc:
            _duration = (time.perf_counter() - _t0) * 1000
            logger.error(
                "sync_root_admin_timeout",
                path=normalized_path,
                duration_ms=round(_duration, 1),
                exc_info=True,
            )
            raise SyncBackendUnavailable(
                "SyncServer did not respond in time.",
                method=method,
                path=normalized_path,
            ) from exc
        except httpx.RequestError as exc:
            _duration = (time.perf_counter() - _t0) * 1000
            logger.error(
                "sync_root_admin_request_failed",
                path=normalized_path,
                duration_ms=round(_duration, 1),
                exc_info=True,
            )
            raise SyncBackendUnavailable(
                "SyncServer is unavailable.",
                method=method,
                path=normalized_path,
            ) from exc

        if response.status_code >= 400:
            self._raise_for_response(response, method=method, path=normalized_path)

        if response.status_code == 204 or not response.content:
            return None

        try:
            return response.json()
        except ValueError:
            return {"detail": response.text}

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, json=json)

    def patch(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, json=json)
