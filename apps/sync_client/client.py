from __future__ import annotations

import logging
from typing import Any

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model

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
    - Django runtime auth is token-based
    - root user uses root token from env
    - non-root user uses token from local SyncUserBinding
    - all HTTP calls to SyncServer should go through this client
    """

    def __init__(
        self,
        user_id: str | int | None = None,
        site_id: str | int | None = None,
        request=None,
        *,
        force_root: bool = False,
    ) -> None:
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = float(getattr(settings, "SYNC_SERVER_TIMEOUT", 10))
        self.device_token = getattr(settings, "SYNC_DEVICE_TOKEN", "").strip()
        self.root_user_token = getattr(settings, "SYNC_ROOT_USER_TOKEN", "").strip()
        self.request = request
        self.force_root = force_root

        self.default_user_id = (
            user_id if user_id is not None else getattr(settings, "SYNC_DEFAULT_ACTING_USER_ID", "")
        )
        self.default_site_id = (
            site_id if site_id is not None else getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")
        )
        if not self.device_token:
            raise RuntimeError("SYNC_DEVICE_TOKEN is not configured.")
        if not self.root_user_token:
            raise RuntimeError("SYNC_ROOT_USER_TOKEN is not configured.")

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
        user_token = self._resolve_user_token(acting_user_id=acting_user_id)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Device-Token": self.device_token,
            "X-User-Token": user_token,
        }
        site_id = self._resolve_site_id(acting_site_id=acting_site_id)
        if site_id:
            headers["X-Site-Id"] = site_id
        return headers

    def _resolve_site_id(self, *, acting_site_id: str | int | None = None) -> str:
        candidates = [
            acting_site_id,
            self.default_site_id,
        ]

        request_session = getattr(self.request, "session", None)
        if request_session is not None:
            candidates.extend(
                [
                    request_session.get("active_site"),
                    request_session.get("sync_default_site_id"),
                    request_session.get("site_id"),
                ]
            )

        request_user = getattr(self.request, "user", None)
        if request_user is not None and getattr(request_user, "is_authenticated", False):
            try:
                candidates.append(request_user.sync_binding.default_site_id)
            except Exception:
                pass

        for candidate in candidates:
            if candidate in (None, ""):
                continue
            return str(candidate).strip()

        return ""

    def _resolve_user_token(self, *, acting_user_id: str | int | None = None) -> str:
        if self.force_root:
            return self.root_user_token

        request_user = getattr(self.request, "user", None)
        if request_user is not None and getattr(request_user, "is_authenticated", False):
            if getattr(request_user, "is_superuser", False):
                return self.root_user_token

            token = self._get_binding_token_for_user(request_user)
            if token:
                logger.info("Resolved user token from sync_binding for user %s", request_user.username)
                return token
            logger.error(
                "Sync user token is not configured for Django user '%s'",
                request_user.username,
            )
            raise RuntimeError(
                f"Sync user token is not configured for Django user '{request_user.username}'."
            )

        lookup_user_id = acting_user_id if acting_user_id is not None else self.default_user_id
        if lookup_user_id not in (None, ""):
            token = self._get_binding_token_for_user_id(lookup_user_id)
            if token:
                return token

        logger.error("Unable to resolve SyncServer user token for the current request. acting_user_id=%s, default_user_id=%s, request.user=%s", acting_user_id, self.default_user_id, getattr(self.request, 'user', None))
        raise RuntimeError("Unable to resolve SyncServer user token for the current request.")

    @staticmethod
    def _get_binding_token_for_user(user) -> str:
        try:
            binding = user.sync_binding
        except Exception:
            return ""
        return (binding.sync_user_token or "").strip()

    @staticmethod
    def _get_binding_token_for_user_id(user_id: str | int) -> str:
        UserModel = get_user_model()
        try:
            user = UserModel.objects.select_related("sync_binding").get(pk=user_id)
        except UserModel.DoesNotExist:
            return ""
        return SyncServerClient._get_binding_token_for_user(user)

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

        if status_code in (400, 422):
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

        logger.info(
            "SyncServer request",
            extra={
                "sync_method": method,
                "sync_url": url,
                "sync_headers": {k: v for k, v in headers.items() if k != "X-User-Token"},
                "sync_params": params,
                "sync_json": json,
            },
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

        logger.info(
            "SyncServer response",
            extra={
                "sync_method": method,
                "sync_path": normalized_path,
                "sync_status_code": response.status_code,
                "sync_response_headers": dict(response.headers),
            },
        )

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

    def delete(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._request(
            "DELETE",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            params=params,
        )
