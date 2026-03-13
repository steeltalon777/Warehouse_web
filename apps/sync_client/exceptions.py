from __future__ import annotations

from typing import Any


class SyncServerAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class ValidationError(SyncServerAPIError):
    pass


class PermissionDenied(SyncServerAPIError):
    pass


class ConflictError(SyncServerAPIError):
    pass
