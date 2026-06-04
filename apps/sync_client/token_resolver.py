"""Canonical SyncServer identity resolver for Warehouse_web.

All active Django/BFF flows must use this module to resolve SyncServer
user tokens.  Direct token lookups in other modules are forbidden.

Policy:
- Django superusers: SYNC_ROOT_USER_TOKEN from env
- Normal users: binding token -> session token -> SyncIdentityNotBoundError
- force_root=True: SYNC_ROOT_USER_TOKEN (explicit admin/system flow)
- SYNC_DEVICE_TOKEN: optional audit context, never required for user-token calls
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import Literal

from django.conf import settings

from .exceptions import SyncAuthError

logger = structlog.get_logger()


class SyncIdentityNotBoundError(SyncAuthError):
    """Raised when an authenticated Django user has no SyncServer identity."""

    def __init__(self, user_id=None, username=None) -> None:
        self.user_id = user_id
        self.username = username
        msg = f"SyncServer identity not bound for user '{username or user_id}'."
        super().__init__(msg)


@dataclass(frozen=True)
class ResolvedSyncIdentity:
    user_token: str
    source: Literal["binding", "session", "root_explicit", "root_superuser"]
    is_root: bool


def resolve_sync_identity(
    request=None,
    *,
    force_root: bool = False,
    allow_session: bool = True,
) -> ResolvedSyncIdentity:
    """Resolve SyncServer identity for the current request.

    Args:
        request: Django HttpRequest (may have .user and .session).
        force_root: When True, use SYNC_ROOT_USER_TOKEN explicitly.
        allow_session: When True, fall back to session token if no binding.

    Returns:
        ResolvedSyncIdentity with user_token, source, is_root.

    Raises:
        SyncIdentityNotBoundError: No token found for a non-root flow.
        RuntimeError: Root flow but SYNC_ROOT_USER_TOKEN not configured.
    """
    if force_root:
        return _resolve_root_explicit()

    request_user = getattr(request, "user", None)
    is_authenticated = request_user is not None and getattr(
        request_user, "is_authenticated", False
    )

    if not is_authenticated:
        raise SyncIdentityNotBoundError()

    if getattr(request_user, "is_superuser", False):
        return _resolve_root_explicit(source="root_superuser")

    # Try binding token first
    binding_token = _get_binding_token(request_user)
    if binding_token:
        logger.info(
            "resolved_token_from_binding", username=request_user.username,
        )
        return ResolvedSyncIdentity(
            user_token=binding_token,
            source="binding",
            is_root=False,
        )

    # Try session token
    if allow_session:
        session_token = _get_session_token(request)
        if session_token:
            logger.info(
                "resolved_token_from_session", username=request_user.username,
            )
            return ResolvedSyncIdentity(
                user_token=session_token,
                source="session",
                is_root=False,
            )

    # No token found for a non-root user: raise controlled error.
    raise SyncIdentityNotBoundError(
        user_id=getattr(request_user, "id", None),
        username=getattr(request_user, "username", None),
    )


def _resolve_root_explicit(
    *,
    source: Literal["root_explicit", "root_superuser"] = "root_explicit",
) -> ResolvedSyncIdentity:
    root_token = getattr(settings, "SYNC_ROOT_USER_TOKEN", "").strip()
    if not root_token:
        raise RuntimeError(
            "SYNC_ROOT_USER_TOKEN is not configured for root flow."
        )
    return ResolvedSyncIdentity(
        user_token=root_token,
        source=source,
        is_root=True,
    )


def _get_binding_token(user) -> str:
    try:
        binding = user.sync_binding
    except Exception:
        return ""
    return (getattr(binding, "sync_user_token", None) or "").strip()


def _get_session_token(request) -> str:
    session = getattr(request, "session", None)
    if session is None:
        return ""
    return (session.get("sync_user_token") or "").strip()


def get_device_token() -> str:
    """Return SYNC_DEVICE_TOKEN if configured, empty string otherwise.

    Device token is optional audit context for web business calls.
    """
    return getattr(settings, "SYNC_DEVICE_TOKEN", "").strip()
