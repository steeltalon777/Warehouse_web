"""
Balances API client module for SyncServer balances endpoints.

This module provides high-level methods for interacting with SyncServer
balances API using the base SyncServerClient.

Balances represent current inventory quantities for items at specific sites.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.balances_api import BalancesAPI
    
    client = SyncServerClient(user_id="user-123", site_id="site-456")
    balances_api = BalancesAPI(client)
    
    # List balances with filters
    balances = balances_api.list_balances(filters={
        "item_id": "item-123",
        "site_id": "site-456",
        "min_quantity": 5
    })
    
    # Get balances summary
    summary = balances_api.get_balances_summary(filters={"site_id": "site-456"})
    
    # Get balances for specific item
    item_balances = balances_api.get_balances_by_item("item-123")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)


class BalancesAPI:
    """
    High-level client for SyncServer balances API.
    
    This class provides convenient methods for inventory balance queries
    including listing, summarization, and item-specific balances.
    
    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize BalancesAPI client.
        
        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("BalancesAPI client initialized")
    
    def list_balances(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of inventory balances with optional filtering.
        
        Endpoint: GET /balances
        
        Args:
            filters: Optional filters for balances (e.g., item_id, site_id, min_quantity, max_quantity)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of balance dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> balances_api = BalancesAPI()
            >>> # Get all balances for specific site
            >>> balances = balances_api.list_balances(filters={"site_id": "site-456"})
            >>> # Get balances for specific item
            >>> balances = balances_api.list_balances(filters={"item_id": "item-123"})
            >>> # Get low stock items (quantity < 10)
            >>> balances = balances_api.list_balances(filters={"max_quantity": 10})
            >>> # Get well-stocked items (quantity > 50)
            >>> balances = balances_api.list_balances(filters={"min_quantity": 50})
        """
        logger.debug(
            "Fetching balances list",
            extra={"filters": filters or {}}
        )
        
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/balances",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "balances" in response:
            return response["balances"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /balances",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def get_balances_summary(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get summary statistics for inventory balances.
        
        Endpoint: GET /balances/summary
        
        Args:
            filters: Optional filters for summary (e.g., site_id)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Balance summary information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> balances_api = BalancesAPI()
            >>> # Get overall summary
            >>> summary = balances_api.get_balances_summary()
            >>> # Get summary for specific site
            >>> summary = balances_api.get_balances_summary(filters={"site_id": "site-456"})
            >>> # Summary might include:
            >>> # {
            >>> #     "total_items": 150,
            >>> #     "total_quantity": 1250.5,
            >>> #     "low_stock_items": 12,
            >>> #     "out_of_stock_items": 3,
            >>> #     "by_site": {...}
            >>> # }
        """
        logger.debug(
            "Fetching balances summary",
            extra={"filters": filters or {}}
        )
        
        params = self._build_filter_params(filters)
        return self.client.get(
            "/balances/summary",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def get_balances_by_item(
        self,
        item_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get balances for specific item across all sites.
        
        Endpoint: GET /balances/items/{item_id}
        
        Args:
            item_id: Item identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of balance dictionaries for the item
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> balances_api = BalancesAPI()
            >>> # Get balances for specific item across all sites
            >>> item_balances = balances_api.get_balances_by_item("item-123")
            >>> for balance in item_balances:
            ...     print(f"Site: {balance['site_id']}, Quantity: {balance['quantity']}")
        """
        logger.debug("Fetching balances by item", extra={"item_id": item_id})
        response = self.client.get(
            f"/balances/items/{item_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "balances" in response:
            return response["balances"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                f"Unexpected response format from /balances/items/{item_id}",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    # ---------- HELPER METHODS ----------
    
    def _build_filter_params(self, filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        """
        Build query parameters from filters dictionary.
        
        Args:
            filters: Dictionary of filter criteria
            
        Returns:
            dict: Query parameters for HTTP request
        """
        if not filters:
            return {}
        
        params = {}
        for key, value in filters.items():
            if value is not None:
                params[key] = value
        
        return params


# Convenience function for quick usage
def get_balances_api(client: Optional[SyncServerClient] = None) -> BalancesAPI:
    """
    Get a BalancesAPI instance.
    
    Args:
        client: Optional SyncServerClient instance
        
    Returns:
        BalancesAPI instance
    """
    return BalancesAPI(client=client)