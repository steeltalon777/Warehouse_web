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
from .token_resolver import (
    SyncIdentityNotBoundError,
    get_device_token,
    resolve_sync_identity,
)
from .transport import execute_with_retry, get_sync_client

logger = structlog.get_logger()


class SyncServerClient:
    """
    Canonical low-level transport for Warehouse_web -> SyncServer communication.

    Rules:
    - base URL MUST already include /api/v1
    - Django runtime auth is token-based
    - Django superusers use SYNC_ROOT_USER_TOKEN from env
    - non-root users use token from local SyncUserBinding or session
    - force_root=True also uses SYNC_ROOT_USER_TOKEN for explicit admin/system flow
    - missing non-root binding raises SyncIdentityNotBoundError, never falls back to root
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
        self.device_token = get_device_token()
        self.request = request
        self.force_root = force_root

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
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        identity = resolve_sync_identity(
            request=self.request,
            force_root=self.force_root,
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-User-Token": identity.user_token,
        }
        if self.device_token:
            headers["X-Device-Token"] = self.device_token
        if self.request is not None:
            request_id = self.request.META.get("X_REQUEST_ID")
            if request_id:
                headers["X-Request-Id"] = request_id
        if extra_headers:
            for key, value in extra_headers.items():
                if value is None:
                    continue
                headers[str(key)] = str(value)
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

    def _log_error(
        self,
        *,
        method: str,
        path: str,
        status_code: int | None,
        payload: dict[str, Any] | None,
    ) -> None:
        logger.warning(
            "sync_request_failed",
            sync_method=method,
            sync_path=path,
            sync_status_code=status_code,
            sync_response_body=payload or {},
        )

    def _raise_for_response(
        self,
        response: httpx.Response,
        *,
        method: str,
        path: str,
    ) -> None:
        payload = self._extract_payload(response)
        sanitized = sanitize_payload(payload)
        detail = sanitized.get("detail")
        if isinstance(detail, dict):
            # SyncServer problem-envelope case: detail is a structured object.
            message = detail.get("message") or detail.get("detail") or str(detail) or "SyncServer error"
        elif isinstance(detail, str):
            message = detail or "SyncServer error"
        else:
            message = str(detail or "SyncServer error")
        status_code = response.status_code

        self._log_error(
            method=method,
            path=path,
            status_code=status_code,
            payload=sanitized,
        )

        kwargs = {
            "status_code": status_code,
            "payload": sanitized,
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
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        normalized_path = self._normalize_path(path)
        url = f"{self.base_url}{normalized_path}"
        headers = self.build_headers(
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
        )

        _request_id = headers.get("X-Request-Id", "")
        _call_log = {
            "sync_method": method,
            "sync_url": url,
            "sync_path": normalized_path,
        }
        if _request_id:
            _call_log["sync_request_id"] = _request_id
        logger.info("sync_request", **_call_log)

        _t0 = time.perf_counter()

        if self.request is not None:
            current_count = self.request.META.get("SYNC_CALL_COUNT", 0)
            self.request.META["SYNC_CALL_COUNT"] = current_count + 1

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
                "sync_server_timeout",
                sync_method=method,
                sync_path=normalized_path,
                sync_duration_ms=round(_duration, 1),
                exc_info=True,
            )
            raise SyncBackendUnavailable(
                "SyncServer не ответил вовремя.",
                method=method,
                path=normalized_path,
            ) from exc
        except httpx.RequestError as exc:
            _duration = (time.perf_counter() - _t0) * 1000
            logger.error(
                "sync_server_unreachable",
                sync_method=method,
                sync_path=normalized_path,
                sync_duration_ms=round(_duration, 1),
                exc_info=True,
            )
            raise SyncBackendUnavailable(
                "SyncServer недоступен.",
                method=method,
                path=normalized_path,
            ) from exc

        _duration = (time.perf_counter() - _t0) * 1000

        logger.info(
            "sync_response",
            sync_method=method,
            sync_path=normalized_path,
            sync_status_code=response.status_code,
            sync_duration_ms=round(_duration, 1),
            sync_request_id=_request_id or None,
        )

        if response.status_code >= 400:
            self._raise_for_response(
                response,
                method=method,
                path=normalized_path,
            )

        if response.status_code == 204:
            return None if not return_response else (None, dict(response.headers))

        if not response.content:
            return None if not return_response else (None, dict(response.headers))

        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"detail": response.text}

        if return_response:
            return payload, dict(response.headers)
        return payload

    def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        params: dict[str, Any] | None = None,
        accept: str = "application/octet-stream",
    ) -> tuple[bytes, dict[str, str]]:
        normalized_path = self._normalize_path(path)
        url = f"{self.base_url}{normalized_path}"
        headers = self.build_headers(
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        headers["Accept"] = accept

        _request_id = headers.get("X-Request-Id", "")
        _t0 = time.perf_counter()

        _retries = int(getattr(settings, "SYNC_SERVER_RETRIES", 2))
        _backoff = float(getattr(settings, "SYNC_SERVER_RETRY_BACKOFF", 0.2))

        def _do_request_bytes() -> httpx.Response:
            client = get_sync_client()
            return client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
            )

        try:
            response = execute_with_retry(_do_request_bytes, method, retries=_retries, backoff=_backoff)
        except httpx.TimeoutException as exc:
            _duration = (time.perf_counter() - _t0) * 1000
            logger.error(
                "sync_server_timeout",
                sync_method=method,
                sync_path=normalized_path,
                sync_duration_ms=round(_duration, 1),
                exc_info=True,
            )
            raise SyncBackendUnavailable(
                "SyncServer не ответил вовремя.",
                method=method,
                path=normalized_path,
            ) from exc
        except httpx.RequestError as exc:
            _duration = (time.perf_counter() - _t0) * 1000
            logger.error(
                "sync_server_unreachable",
                sync_method=method,
                sync_path=normalized_path,
                sync_duration_ms=round(_duration, 1),
                exc_info=True,
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

        return response.content, dict(response.headers)

    def get(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        return self._request(
            "GET",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            params=params,
            extra_headers=extra_headers,
            return_response=return_response,
        )

    def get_bytes(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        params: dict[str, Any] | None = None,
        accept: str = "application/octet-stream",
    ) -> tuple[bytes, dict[str, str]]:
        return self._request_bytes(
            "GET",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            params=params,
            accept=accept,
        )

    def post(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        return self._request(
            "POST",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            params=params,
            extra_headers=extra_headers,
            return_response=return_response,
        )

    def put(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        return self._request(
            "PUT",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            extra_headers=extra_headers,
            return_response=return_response,
        )

    def patch(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        return self._request(
            "PATCH",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            extra_headers=extra_headers,
            return_response=return_response,
        )

    def delete(
        self,
        path: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        return_response: bool = False,
    ) -> Any:
        return self._request(
            "DELETE",
            path,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            json=json,
            params=params,
            extra_headers=extra_headers,
            return_response=return_response,
        )
