from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


class SyncServerRootAdminClient:
    """
    Root-token SyncServer client for Django-admin management operations.
    """

    def __init__(self) -> None:
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = float(getattr(settings, "SYNC_SERVER_TIMEOUT", 10))
        self.device_token = getattr(settings, "SYNC_DEVICE_TOKEN", "").strip()
        self.root_user_token = getattr(settings, "SYNC_ROOT_USER_TOKEN", "").strip()

        if not self.base_url.endswith("/api/v1"):
            raise RuntimeError(
                "SYNC_SERVER_URL must include '/api/v1'. "
                f"Current value: {self.base_url}"
            )
        if not self.device_token:
            raise RuntimeError("SYNC_DEVICE_TOKEN is not configured.")
        if not self.root_user_token:
            raise RuntimeError("SYNC_ROOT_USER_TOKEN is not configured.")

    def _build_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Device-Token": self.device_token,
            "X-User-Token": self.root_user_token,
        }

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
        message = str(payload.get("detail") or "SyncServer error")
        kwargs = {
            "status_code": response.status_code,
            "payload": payload,
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

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            logger.exception("SyncServer root-admin timeout", extra={"path": normalized_path})
            raise SyncBackendUnavailable(
                "SyncServer did not respond in time.",
                method=method,
                path=normalized_path,
            ) from exc
        except httpx.RequestError as exc:
            logger.exception("SyncServer root-admin request failed", extra={"path": normalized_path})
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
