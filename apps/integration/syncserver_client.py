from __future__ import annotations

from typing import Any


class SyncServerError(RuntimeError):
    """
    Deprecated legacy integration error.

    This module is intentionally disabled because Warehouse_web must not use:
    - legacy endpoints (/roles, /sites, /users)
    - device-auth headers
    - old integration layer
    """

    def __init__(self, message: str, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class SyncServerClient:
    """
    DEPRECATED.
    Use apps.sync_client.client.SyncServerClient and group APIs from apps.sync_client.* instead.
    """

    def __init__(self) -> None:
        raise SyncServerError(
            "apps.integration.syncserver_client is deprecated and must not be used. "
            "Migrate to apps.sync_client.client.SyncServerClient with service-auth."
        )