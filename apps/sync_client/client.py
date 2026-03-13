from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from .exceptions import ConflictError, PermissionDenied, SyncServerAPIError, ValidationError


class SyncServerClient:
    def __init__(self, user_id: str | int, site_id: str | int):
        self.base_url = settings.SYNC_SERVER_URL.rstrip("/")
        self.timeout = getattr(settings, "SYNC_SERVER_TIMEOUT", 10)
        self.headers = {
            "Authorization": f"Bearer {settings.SYNC_SERVER_SERVICE_TOKEN}",
            "X-Acting-User-Id": str(user_id),
            "X-Acting-Site-Id": str(site_id),
        }

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=self.headers, json=json, params=params)
        except httpx.RequestError as exc:
            raise SyncServerAPIError("SyncServer временно недоступен.") from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {"detail": response.text or "SyncServer error"}
            message = str(payload.get("detail") or "SyncServer error")
            if response.status_code == 400:
                raise ValidationError(message, response.status_code, payload)
            if response.status_code in {401, 403}:
                raise PermissionDenied(message, response.status_code, payload)
            if response.status_code == 409:
                raise ConflictError(message, response.status_code, payload)
            raise SyncServerAPIError(message, response.status_code, payload)

        if response.status_code == 204:
            return None
        return response.json()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, json=json, params=params)

    def patch(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, json=json)
