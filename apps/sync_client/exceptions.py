from __future__ import annotations

from typing import Any


class SyncServerAPIError(Exception):
    """
    Base exception for all SyncServer integration failures.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        payload: dict[str, Any] | None = None,
        *,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.method = method
        self.path = path


class SyncBackendUnavailable(SyncServerAPIError):
    """
    Network/DNS/timeout/connectivity failure.
    """
    pass


class SyncAuthError(SyncServerAPIError):
    """
    401 Unauthorized
    """
    pass


class SyncForbiddenError(SyncServerAPIError):
    """
    403 Forbidden
    """
    pass


class SyncNotFoundError(SyncServerAPIError):
    """
    404 Wrong endpoint or entity not found.
    """
    pass


class SyncValidationError(SyncServerAPIError):
    """
    400/422 validation or malformed request.
    """
    pass


class SyncConflictError(SyncServerAPIError):
    """
    409 business conflict.
    """
    pass


class SyncServerInternalError(SyncServerAPIError):
    """
    5xx SyncServer-side failure.
    """
    pass


# -------------------------------------------------------------------
# Compatibility aliases for old imports in current codebase.
# This lets you migrate call-sites gradually without mass breakage.
# -------------------------------------------------------------------
ValidationError = SyncValidationError
PermissionDenied = SyncForbiddenError
ConflictError = SyncConflictError