"""
Sites API client module for SyncServer admin sites endpoints.

This module provides high-level methods for interacting with SyncServer
admin sites API using the base SyncServerClient.

All methods require acting user and site context for service authentication.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.sites_api import SitesAPI
    
    client = SyncServerClient(user_id="admin", site_id="main")
    sites_api = SitesAPI(client)
    
    # List all sites
    sites = sites_api.list_sites()
    
    # Create new site
    new_site = sites_api.create_site({
        "name": "Warehouse 2",
        "code": "WH2",
        "description": "Secondary warehouse"
    })
    
    # Update site
    updated_site = sites_api.update_site("site-123", {
        "description": "Updated description"
    })
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)


class SitesAPI:
    """
    High-level client for SyncServer admin sites API.
    
    This class provides convenient methods for site management operations
    without mixing HTTP transport logic with business logic.
    
    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize SitesAPI client.
        
        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("SitesAPI client initialized")
    
    def list_sites(
        self,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of all sites from SyncServer.
        
        Endpoint: GET /admin/sites
        
        Args:
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of site dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> sites_api = SitesAPI()
            >>> sites = sites_api.list_sites()
            >>> for site in sites:
            ...     print(site["name"], site["code"], site["id"])
        """
        logger.debug("Fetching list of sites")
        response = self.client.get(
            "/admin/sites",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "sites" in response:
            return response["sites"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /admin/sites",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def create_site(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new site in SyncServer.
        
        Endpoint: POST /admin/sites
        
        Args:
            payload: Site creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created site information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> sites_api = SitesAPI()
            >>> new_site = sites_api.create_site({
            ...     "name": "Warehouse 2",
            ...     "code": "WH2",
            ...     "description": "Secondary warehouse",
            ...     "address": "123 Main St",
            ...     "timezone": "Europe/Moscow"
            ... })
            >>> print(new_site["id"])
        """
        logger.debug(
            "Creating site",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/admin/sites",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_site(
        self,
        site_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing site in SyncServer.
        
        Endpoint: PATCH /admin/sites/{site_id}
        
        Args:
            site_id: Site identifier to update
            payload: Site update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated site information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> sites_api = SitesAPI()
            >>> updated_site = sites_api.update_site("site-123", {
            ...     "description": "Updated warehouse description",
            ...     "address": "456 Updated St"
            ... })
            >>> print(updated_site["name"])
        """
        logger.debug(
            "Updating site",
            extra={"site_id": site_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/admin/sites/{site_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )


# Convenience function for quick usage
def get_sites_api(client: Optional[SyncServerClient] = None) -> SitesAPI:
    """
    Get a SitesAPI instance.
    
    Args:
        client: Optional SyncServerClient instance
        
    Returns:
        SitesAPI instance
    """
    return SitesAPI(client=client)