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


class SyncServerClient:
    """
    Canonical low-level transport for Warehouse_web -> SyncServer communication.

    Rules:
    - base URL MUST already include /api/v1
    - service-auth only
    - acting user/site headers are added here, not in view layer
    - all HTTP calls to SyncServer should go through this client
    """

    def __init__(
        self,
        user_id: str | int | None = None,
        site_id: str | int | None = None,
    ) -> None:
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = float(getattr(settings, "SYNC_SERVER_TIMEOUT", 10))
        self.service_token = getattr(settings, "SYNC_SERVER_SERVICE_TOKEN", "").strip()

        self.default_user_id = user_id if user_id is not None else getattr(settings, "SYNC_DEFAULT_ACTING_USER_ID", "")
        self.default_site_id = site_id if site_id is not None else getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")

        if not self.service_token:
            raise RuntimeError("SYNC_SERVER_SERVICE_TOKEN is not configured.")

        if not self.base_url.endswith("/api/v1"):
            raise RuntimeError(
                "SYNC_SERVER_URL must include '/api/v1'. "
                f"Current value: {self.base_url}"
            )

    def build_headers(
            self,
            *,
            acting_user_id: str | int | None = None,
            acting_site_id: str | int | None = None,
    ) -> dict[str, str]:
        user_id = acting_user_id if acting_user_id is not None else self.default_user_id
        site_id = acting_site_id if acting_site_id is not None else self.default_site_id

        if user_id in (None, ""):
            raise RuntimeError("Acting user id is required for SyncServer service-auth requests.")

        if site_id in (None, ""):
            raise RuntimeError("Acting site id is required for SyncServer service-auth requests.")

        return {
            "Authorization": f"Bearer {self.service_token}",
            "X-User-Id": str(user_id),
            "X-Site-Id": str(site_id),
            "X-Device-Id": "web-admin",
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

    def _log_error(
        self,
        *,
        method: str,
        path: str,
        status_code: int | None,
        payload: dict[str, Any] | None,
    ) -> None:
        logger.warning(
            "SyncServer request failed",
            extra={
                "sync_method": method,
                "sync_path": path,
                "sync_status_code": status_code,
                "sync_response_body": payload or {},
            },
        )

    def _raise_for_response(
        self,
        response: httpx.Response,
        *,
        method: str,
        path: str,
    ) -> None:
        payload = self._extract_payload(response)
        message = str(payload.get("detail") or "SyncServer error")
        status_code = response.status_code

        self._log_error(
            method=method,
            path=path,
            status_code=status_code,
            payload=payload,
        )

        kwargs = {
            "status_code": status_code,
            "payload": payload,
            "method": method,
            "path": path,
        }

        if status_code == 400 or status_code == 422:
            raise SyncValidationError(message, **kwargs)
        if status_code == 401:
            raise SyncAuthError(message, **kwargs)
        if status_code == 403:
            raise SyncForbiddenError(message, **kwargs)
        if status_code == 404:
            raise SyncNotFoundError(message, **kwargs)
        if status_code == 409:
            raise SyncConflictError(message, **kwargs)
        if status_code >= 500:
            raise SyncServerInternalError(message, **kwargs)

        raise SyncServerAPIError(message, **kwargs)

    def _request(
        self,
        method: str,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        normalized_path = self._normalize_path(path)
        url = f"{self.base_url}{normalized_path}"
        headers = self.build_headers(
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

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
            logger.exception(
                "SyncServer timeout",
                extra={"sync_method": method, "sync_path": normalized_path},
            )
            raise SyncBackendUnavailable(
                "SyncServer не ответил вовремя.",
                method=method,
                path=normalized_path,
            ) from exc
        except httpx.RequestError as exc:
            logger.exception(
                "SyncServer unreachable",
                extra={"sync_method": method, "sync_path": normalized_path},
            )
            raise SyncBackendUnavailable(
                "SyncServer недоступен.",
                method=method,
                path=normalized_path,
            ) from exc

        if response.status_code >= 400:
            self._raise_for_response(
                response,
                method=method,
                path=normalized_path,
            )

        if response.status_code == 204:
            return None

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError:
            return {"detail": response.text}

    def get(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._request(
            "GET",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            params=params,
        )

    def post(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._request(
            "POST",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            params=params,
        )

    def patch(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        return self._request(
            "PATCH",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
        )