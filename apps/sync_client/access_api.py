"""
Access API client module for SyncServer admin access endpoints.

This module provides high-level methods for interacting with SyncServer
admin access API using the base SyncServerClient.

All methods require acting user and site context for service authentication.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.access_api import AccessAPI
    
    client = SyncServerClient(user_id="admin", site_id="main")
    access_api = AccessAPI(client)
    
    # List all access records
    access_records = access_api.list_access()
    
    # Create new access record
    new_access = access_api.create_access({
        "user_id": "user-123",
        "site_id": "site-456",
        "role": "storekeeper"
    })
    
    # Update access record
    updated_access = access_api.update_access("access-789", {
        "role": "chief"
    })
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncAPIError

logger = logging.getLogger(__name__)


class AccessAPI:
    """
    High-level client for SyncServer admin access API.
    
    This class provides convenient methods for user-site access management
    operations without mixing HTTP transport logic with business logic.
    
    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize AccessAPI client.
        
        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("AccessAPI client initialized")
    
    def list_access(
        self,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of all user-site access records from SyncServer.
        
        Endpoint: GET /admin/access/user-sites
        
        Args:
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of access record dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> access_api = AccessAPI()
            >>> access_records = access_api.list_access()
            >>> for record in access_records:
            ...     print(record["user_id"], record["site_id"], record["role"])
        """
        logger.debug("Fetching list of access records")
        response = self.client.get(
            "/admin/access/user-sites",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "access" in response:
            return response["access"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /admin/access/user-sites",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def create_access(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new user-site access record in SyncServer.
        
        Endpoint: POST /admin/access/user-sites
        
        Args:
            payload: Access creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created access record information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> access_api = AccessAPI()
            >>> new_access = access_api.create_access({
            ...     "user_id": "user-123",
            ...     "site_id": "site-456",
            ...     "role": "storekeeper",
            ...     "permissions": ["read", "write"]
            ... })
            >>> print(new_access["id"])
        """
        logger.debug(
            "Creating access record",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/admin/access/user-sites",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_access(
        self,
        access_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing user-site access record in SyncServer.
        
        Endpoint: PATCH /admin/access/user-sites/{access_id}
        
        Args:
            access_id: Access record identifier to update
            payload: Access update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated access record information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> access_api = AccessAPI()
            >>> updated_access = access_api.update_access("access-789", {
            ...     "role": "chief",
            ...     "permissions": ["read", "write", "admin"]
            ... })
            >>> print(updated_access["role"])
        """
        logger.debug(
            "Updating access record",
            extra={"access_id": access_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/admin/access/user-sites/{access_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )


# Convenience function for quick usage
def get_access_api(client: Optional[SyncServerClient] = None) -> AccessAPI:
    """
    Get an AccessAPI instance.
    
    Args:
        client: Optional SyncServerClient instance
        
    Returns:
        AccessAPI instance
    """
    return AccessAPI(client=client)