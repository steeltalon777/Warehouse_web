"""Auth API client module for SyncServer authentication endpoints.

Uses the canonical SyncServerClient for all requests.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SyncServerClient
from .exceptions import SyncAuthError, SyncServerAPIError

logger = logging.getLogger(__name__)


class AuthAPI:
    """High-level client for SyncServer authentication API."""

    def __init__(self, request=None) -> None:
        self.request = request
        logger.debug("AuthAPI client initialized")

    def _get_client(self, *, force_root: bool = False) -> SyncServerClient:
        return SyncServerClient(request=self.request, force_root=force_root)

    def get_me(self, request=None) -> dict[str, Any]:
        """Get current user information from SyncServer.

        Endpoint: GET /auth/me
        """
        logger.debug("Fetching current user info")
        client = SyncServerClient(request=request or self.request)
        return client.get("/auth/me")

    def get_context(self, request=None) -> dict[str, Any]:
        """Get authentication context (user + site info).

        Endpoint: GET /auth/context
        """
        logger.debug("Fetching authentication context")
        client = SyncServerClient(request=request or self.request)
        return client.get("/auth/context")

    def get_sites(self, request=None) -> list[dict[str, Any]]:
        """Get list of sites available to the current user.

        Endpoint: GET /auth/sites
        """
        logger.debug("Fetching available sites")
        client = SyncServerClient(request=request or self.request)
        return client.get("/auth/sites")

    def sync_user(self, request=None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Synchronize user data with SyncServer.

        Endpoint: POST /auth/sync-user
        """
        logger.debug("Synchronizing user data")
        client = SyncServerClient(request=request or self.request)
        return client.post("/auth/sync-user", json=payload or {})

    def validate_token(self, request=None) -> bool:
        """Validate current authentication token.

        Uses get_me() to check if the current token is valid.
        """
        try:
            self.get_me(request=request or self.request)
            return True
        except SyncServerAPIError as e:
            if e.status_code in (401, 403):
                return False
            raise


def get_auth_api(request=None) -> AuthAPI:
    """Get an AuthAPI instance."""
    return AuthAPI(request=request)
