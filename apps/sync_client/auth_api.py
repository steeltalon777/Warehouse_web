"""
Auth API client module for SyncServer authentication endpoints.

This module provides high-level methods for interacting with SyncServer
authentication API using the base SyncClient.

All methods require a Django HttpRequest object for authentication context,
but contain no Django-specific logic themselves.

Usage:
    from apps.sync_client.auth_api import AuthAPI
    
    auth_api = AuthAPI()
    user_info = auth_api.get_me(request)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .simple_client import SyncClient, SyncAPIError

logger = logging.getLogger(__name__)


class AuthAPI:
    """
    High-level client for SyncServer authentication API.
    
    This class provides convenient methods for authentication-related
    operations without mixing HTTP transport logic with business logic.
    
    Attributes:
        client (SyncClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncClient] = None) -> None:
        """
        Initialize AuthAPI client.
        
        Args:
            client: Optional SyncClient instance. If not provided,
                   a new instance will be created.
        """
        self.client = client or SyncClient()
        logger.debug("AuthAPI client initialized")
    
    def get_me(self, request) -> dict[str, Any]:
        """
        Get current user information from SyncServer.
        
        Endpoint: GET /auth/me
        
        Args:
            request: Django HttpRequest object for authentication context
            
        Returns:
            dict: User information from SyncServer
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> auth_api = AuthAPI()
            >>> user_info = auth_api.get_me(request)
            >>> print(user_info["username"])
        """
        logger.debug("Fetching current user info")
        return self.client.get("/auth/me", request=request)
    
    def get_context(self, request) -> dict[str, Any]:
        """
        Get authentication context (user + site info).
        
        Endpoint: GET /auth/context
        
        Args:
            request: Django HttpRequest object for authentication context
            
        Returns:
            dict: Authentication context including user and site information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> auth_api = AuthAPI()
            >>> context = auth_api.get_context(request)
            >>> print(context["user"]["id"], context["site"]["id"])
        """
        logger.debug("Fetching authentication context")
        return self.client.get("/auth/context", request=request)
    
    def get_sites(self, request) -> list[dict[str, Any]]:
        """
        Get list of sites available to the current user.
        
        Endpoint: GET /auth/sites
        
        Args:
            request: Django HttpRequest object for authentication context
            
        Returns:
            list: List of site dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> auth_api = AuthAPI()
            >>> sites = auth_api.get_sites(request)
            >>> for site in sites:
            ...     print(site["name"], site["id"])
        """
        logger.debug("Fetching available sites")
        return self.client.get("/auth/sites", request=request)
    
    def sync_user(self, request, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Synchronize user data with SyncServer.
        
        Endpoint: POST /auth/sync-user
        
        Args:
            request: Django HttpRequest object for authentication context
            payload: User data to synchronize
            
        Returns:
            dict: Synchronization result
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> auth_api = AuthAPI()
            >>> payload = {
            ...     "username": "john_doe",
            ...     "email": "john@example.com",
            ...     "full_name": "John Doe"
            ... }
            >>> result = auth_api.sync_user(request, payload)
            >>> print(result["user_id"])
        """
        logger.debug("Synchronizing user data", extra={"payload_keys": list(payload.keys())})
        return self.client.post("/auth/sync-user", request=request, json=payload)
    
    def validate_token(self, request) -> bool:
        """
        Validate current authentication token.
        
        This is a convenience method that uses get_me() to check
        if the current token is valid.
        
        Args:
            request: Django HttpRequest object for authentication context
            
        Returns:
            bool: True if token is valid, False otherwise
            
        Example:
            >>> auth_api = AuthAPI()
            >>> if auth_api.validate_token(request):
            ...     print("Token is valid")
            ... else:
            ...     print("Token is invalid")
        """
        try:
            self.get_me(request)
            return True
        except SyncAPIError as e:
            if e.status_code in (401, 403):
                return False
            # Re-raise other errors
            raise


# Convenience function for quick usage
def get_auth_api(client: Optional[SyncClient] = None) -> AuthAPI:
    """
    Get an AuthAPI instance.
    
    Args:
        client: Optional SyncClient instance
        
    Returns:
        AuthAPI instance
    """
    return AuthAPI(client=client)