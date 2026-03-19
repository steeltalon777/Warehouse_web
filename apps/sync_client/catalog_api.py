"""
Catalog API client module for SyncServer catalog endpoints.

This module provides high-level methods for interacting with SyncServer
catalog API using the base SyncServerClient.

The module separates public read operations from admin write operations
and supports filtering for list methods.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.catalog_api import CatalogAPI
    
    client = SyncServerClient(user_id="user-123", site_id="site-456")
    catalog_api = CatalogAPI(client)
    
    # Public methods (read-only)
    items = catalog_api.list_items(filters={"category_id": "cat-123", "search": "widget"})
    categories = catalog_api.list_categories(filters={"is_active": True})
    tree = catalog_api.get_categories_tree()
    units = catalog_api.list_units(filters={"is_active": True})
    
    # Admin methods (write)
    new_item = catalog_api.create_item({
        "name": "New Widget",
        "code": "WIDGET-001",
        "category_id": "cat-123",
        "unit_id": "unit-456"
    })
    
    updated_item = catalog_api.update_item("item-789", {"name": "Updated Widget"})
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncAPIError

logger = logging.getLogger(__name__)


class CatalogAPI:
    """
    High-level client for SyncServer catalog API.
    
    This class provides convenient methods for catalog operations
    with clear separation between public read and admin write methods.
    
    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """
    
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize CatalogAPI client.
        
        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("CatalogAPI client initialized")
    
    # ---------- PUBLIC METHODS (READ-ONLY) ----------
    
    def list_items(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of catalog items with optional filtering.
        
        Endpoint: GET /catalog/items
        
        Args:
            filters: Optional filters for items (e.g., category_id, search, is_active)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of item dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> # Get all active items
            >>> items = catalog_api.list_items(filters={"is_active": True})
            >>> # Get items in specific category
            >>> items = catalog_api.list_items(filters={"category_id": "cat-123"})
            >>> # Search items
            >>> items = catalog_api.list_items(filters={"search": "widget"})
        """
        logger.debug(
            "Fetching catalog items",
            extra={"filters": filters or {}}
        )
        
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/catalog/items",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "items" in response:
            return response["items"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /catalog/items",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def list_categories(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of catalog categories with optional filtering.
        
        Endpoint: GET /catalog/categories
        
        Args:
            filters: Optional filters for categories (e.g., parent_id, is_active)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of category dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> # Get all active categories
            >>> categories = catalog_api.list_categories(filters={"is_active": True})
            >>> # Get subcategories of specific parent
            >>> categories = catalog_api.list_categories(filters={"parent_id": "cat-123"})
        """
        logger.debug(
            "Fetching catalog categories",
            extra={"filters": filters or {}}
        )
        
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/catalog/categories",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "categories" in response:
            return response["categories"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /catalog/categories",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    def get_categories_tree(
        self,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get hierarchical tree of catalog categories.
        
        Endpoint: GET /catalog/categories/tree
        
        Args:
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Hierarchical tree structure of categories
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> tree = catalog_api.get_categories_tree()
            >>> # Tree structure might look like:
            >>> # {
            >>> #     "id": "root",
            >>> #     "name": "Root",
            >>> #     "children": [...]
            >>> # }
        """
        logger.debug("Fetching categories tree")
        return self.client.get(
            "/catalog/categories/tree",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def list_units(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of measurement units with optional filtering.
        
        Endpoint: GET /catalog/units
        
        Args:
            filters: Optional filters for units (e.g., is_active)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            list: List of unit dictionaries
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> # Get all active units
            >>> units = catalog_api.list_units(filters={"is_active": True})
            >>> # Get specific unit types
            >>> units = catalog_api.list_units(filters={"type": "weight"})
        """
        logger.debug(
            "Fetching measurement units",
            extra={"filters": filters or {}}
        )
        
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/catalog/units",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        
        # Handle different response formats
        if isinstance(response, dict) and "units" in response:
            return response["units"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /catalog/units",
                extra={"response_type": type(response).__name__}
            )
            return []
    
    # ---------- ADMIN METHODS (WRITE) ----------
    
    def create_item(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new catalog item (admin only).
        
        Endpoint: POST /catalog/admin/items
        
        Args:
            payload: Item creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created item information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> new_item = catalog_api.create_item({
            ...     "name": "Widget X100",
            ...     "code": "WIDGET-X100",
            ...     "category_id": "cat-123",
            ...     "unit_id": "unit-456",
            ...     "description": "High-quality widget",
            ...     "is_active": True
            ... })
            >>> print(new_item["id"])
        """
        logger.debug(
            "Creating catalog item",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/catalog/admin/items",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_item(
        self,
        item_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing catalog item (admin only).
        
        Endpoint: PATCH /catalog/admin/items/{item_id}
        
        Args:
            item_id: Item identifier to update
            payload: Item update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated item information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> updated_item = catalog_api.update_item("item-789", {
            ...     "name": "Widget X100 Updated",
            ...     "description": "Updated description",
            ...     "is_active": False  # deactivate
            ... })
            >>> print(updated_item["name"])
        """
        logger.debug(
            "Updating catalog item",
            extra={"item_id": item_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/catalog/admin/items/{item_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def create_category(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new catalog category (admin only).
        
        Endpoint: POST /catalog/admin/categories
        
        Args:
            payload: Category creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created category information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> new_category = catalog_api.create_category({
            ...     "name": "Electronics",
            ...     "code": "ELEC",
            ...     "parent_id": None,  # root category
            ...     "sort_order": 10,
            ...     "is_active": True
            ... })
            >>> print(new_category["id"])
        """
        logger.debug(
            "Creating catalog category",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/catalog/admin/categories",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_category(
        self,
        category_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing catalog category (admin only).
        
        Endpoint: PATCH /catalog/admin/categories/{category_id}
        
        Args:
            category_id: Category identifier to update
            payload: Category update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated category information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> updated_category = catalog_api.update_category("cat-123", {
            ...     "name": "Electronics Updated",
            ...     "sort_order": 15,
            ...     "is_active": False  # deactivate
            ... })
            >>> print(updated_category["name"])
        """
        logger.debug(
            "Updating catalog category",
            extra={"category_id": category_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/catalog/admin/categories/{category_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def create_unit(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Create new measurement unit (admin only).
        
        Endpoint: POST /catalog/admin/units
        
        Args:
            payload: Unit creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Created unit information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> new_unit = catalog_api.create_unit({
            ...     "name": "Kilogram",
            ...     "code": "kg",
            ...     "symbol": "kg",
            ...     "is_active": True,
            ...     "is_base": True,
            ...     "conversion_factor": 1.0
            ... })
            >>> print(new_unit["id"])
        """
        logger.debug(
            "Creating measurement unit",
            extra={"payload_keys": list(payload.keys())}
        )
        return self.client.post(
            "/catalog/admin/units",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
    def update_unit(
        self,
        unit_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Update existing measurement unit (admin only).
        
        Endpoint: PATCH /catalog/admin/units/{unit_id}
        
        Args:
            unit_id: Unit identifier to update
            payload: Unit update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            
        Returns:
            dict: Updated unit information
            
        Raises:
            SyncAPIError: If the API request fails
            
        Example:
            >>> catalog_api = CatalogAPI()
            >>> updated_unit = catalog_api.update_unit("unit-456", {
            ...     "name": "Kilogram Updated",
            ...     "symbol": "KG",
            ...     "is_active": False  # deactivate
            ... })
            >>> print(updated_unit["name"])
        """
        logger.debug(
            "Updating measurement unit",
            extra={"unit_id": unit_id, "payload_keys": list(payload.keys())}
        )
        return self.client.patch(
            f"/catalog/admin/units/{unit_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
    
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
def get_catalog_api(client: Optional[SyncServerClient] = None) -> CatalogAPI:
    """
    Get a CatalogAPI instance.
    
    Args:
        client: Optional SyncServerClient instance
        
    Returns:
        CatalogAPI instance
    """
    return CatalogAPI(client=client)