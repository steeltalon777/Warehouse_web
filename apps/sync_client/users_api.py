"""
Users API client module for SyncServer admin users endpoints.

This module provides high-level methods for interacting with SyncServer
admin users API using the base SyncServerClient.

All methods require acting user and site context for service authentication.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.users_api import UsersAPI
    
    client = SyncServerClient(user_id="admin", site_id="main")
    users_api = UsersAPI(client)
    
    # List all users
    users = users_api.list_users()
    
    # Get specific user
    user = users_api.get_user("user-123")
    
    # Create new user
    new_user = users_api.create_user({
        "username": "john_doe",
        "email": "john@example.com",
        "full_name": "John Doe"
    })
    
    # Update user
    updated_user = users_api.update_user("user-123", {
        "full_name": "John Doe Updated"
    })
    
    # Delete user
    users_api.delete_user("user-123")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)


class UsersAPI:
    """
    High-level client for SyncServer admin users API.
    
    This class provides convenient methods for user management operations
    without mixing HTTP transport logic with business logic.
    
    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize UsersAPI client.
        
        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("UsersAPI client initialized")
    
    def list_users(
        self,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of all users from SyncServer.
        
        Endpoint: GET /admin/users
        
        Args:
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of user dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> users_api = UsersAPI()
            >>> users = users_api.list_users()
            >>> for user in users:
            ...     print(user["username"], user["id"])
        """
        logger.debug("Fetching list of users")
        response = self.client.get(
            "/admin/users",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "users" in response:
            return response["users"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /admin/users",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def get_user(
        self,
        user_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get specific user by ID from SyncServer.
        
        Endpoint: GET /admin/users/{user_id}
        
        Args:
            user_id: User identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: User information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> users_api = UsersAPI()
            >>> user = users_api.get_user("user-123")
            >>> print(user["username"], user["email"])
        """
        logger.debug("Fetching user", extra={"user_id": user_id})
        return self.client.get(
            f"/admin/users/{user_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def create_user(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new user in SyncServer.
        
        Endpoint: POST /admin/users
        
        Args:
            payload: User creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created user information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> users_api = UsersAPI()
            >>> new_user = users_api.create_user({
            ...     "username": "john_doe",
            ...     "email": "john@example.com",
            ...     "full_name": "John Doe",
            ...     "password": "secure_password"
            ... })
            >>> print(new_user["id"])
        """
        logger.debug(
            "Creating user",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/admin/users",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_user(
        self,
        user_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing user in SyncServer.
        
        Endpoint: PATCH /admin/users/{user_id}
        
        Args:
            user_id: User identifier to update
            payload: User update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated user information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> users_api = UsersAPI()
            >>> updated_user = users_api.update_user("user-123", {
            ...     "full_name": "John Doe Updated",
            ...     "email": "john.updated@example.com"
            ... })
            >>> print(updated_user["full_name"])
        """
        logger.debug(
            "Updating user",
            extra={"user_id": user_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/admin/users/{user_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def delete_user(
        self,
        user_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> None:
        """
        Delete user from SyncServer.
        
        Endpoint: DELETE /admin/users/{user_id}
        
        Args:
            user_id: User identifier to delete
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> users_api = UsersAPI()
            >>> users_api.delete_user("user-123")
        """
        logger.debug("Deleting user", extra={"user_id": user_id})
        self.client.delete(
            f"/admin/users/{user_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )


# Convenience function for quick usage
def get_users_api(client: Optional[SyncServerClient] = None) -> UsersAPI:
    """
    Get a UsersAPI instance.
    
    Args:
        client: Optional SyncServerClient instance
        
    Returns:
        UsersAPI instance
    """
    return UsersAPI(client=client)