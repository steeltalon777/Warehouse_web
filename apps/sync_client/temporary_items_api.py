"""
Temporary Items API client module for SyncServer temporary items endpoints.

This module provides high-level methods for interacting with SyncServer
temporary items API using the base SyncServerClient.

Temporary items are provisional catalog entries created during operations
that can later be approved as permanent catalog items or merged with existing items.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.temporary_items_api import TemporaryItemsAPI

    client = SyncServerClient(user_id="user-123", site_id="site-456")
    temp_api = TemporaryItemsAPI(client)

    # List temporary items
    items = temp_api.list_temporary_items(filters={"site_id": "site-456"})

    # Get specific temporary item
    item = temp_api.get_temporary_item("temp-123")

    # Approve temporary item as permanent catalog item
    approved = temp_api.approve_as_item("temp-123")

    # Merge temporary item with existing catalog item
    merged = temp_api.merge_to_item("temp-123", {"target_item_id": "item-456"})
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)


class TemporaryItemsAPI:
    """
    High-level client for SyncServer temporary items API.

    This class provides convenient methods for temporary item management
    including listing, retrieval, approval, and merging.

    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize TemporaryItemsAPI client.

        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("TemporaryItemsAPI client initialized")

    # ------------------------------------------------------------------
    # List and retrieve
    # ------------------------------------------------------------------

    def list_temporary_items(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of temporary items with optional filtering.

        Endpoint: GET /temporary-items

        Args:
            filters: Optional filters for temporary items
                (e.g., site_id, status, search, created_after, created_before)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            list: List of temporary item dictionaries

        Raises:
            SyncServerAPIError: If the API request fails

        Example:
            >>> temp_api = TemporaryItemsAPI()
            >>> # Get all temporary items for a site
            >>> items = temp_api.list_temporary_items(filters={"site_id": "site-456"})
            >>> # Get pending temporary items
            >>> items = temp_api.list_temporary_items(filters={"status": "pending"})
            >>> # Search temporary items
            >>> items = temp_api.list_temporary_items(filters={"search": "cable"})
        """
        logger.debug(
            "Fetching temporary items list",
            extra={"filters": filters or {}}
        )

        params = self._build_filter_params(filters)
        response = self.client.get(
            "/temporary-items",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        # Handle different response formats
        if isinstance(response, dict) and "items" in response:
            return response["items"]
        elif isinstance(response, dict) and "temporary_items" in response:
            return response["temporary_items"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /temporary-items",
                extra={"response_type": type(response).__name__}
            )
            return []

    def list_temporary_items_page(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a paginated page of temporary items.

        Endpoint: GET /temporary-items

        Args:
            filters: Optional filters including pagination (page, page_size)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Paginated response with keys:
                items (list): List of temporary items
                total_count (int): Total number of items
                page (int): Current page number
                page_size (int): Page size used
        """
        logger.debug(
            "Fetching temporary items page",
            extra={"filters": filters or {}}
        )

        params = self._build_filter_params(filters)
        response = self.client.get(
            "/temporary-items",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        if isinstance(response, dict):
            if "temporary_items" in response and "items" not in response:
                response = {**response, "items": response.get("temporary_items", [])}
            response.setdefault("items", [])
            response.setdefault("total_count", len(response.get("items", [])))
            response.setdefault("page", params.get("page", 1))
            response.setdefault("page_size", params.get("page_size", len(response.get("items", [])) or 20))
            return response

        if isinstance(response, list):
            return {
                "items": response,
                "total_count": len(response),
                "page": params.get("page", 1),
                "page_size": params.get("page_size", len(response) or 20),
            }

        logger.warning(
            "Unexpected response format from /temporary-items",
            extra={"response_type": type(response).__name__}
        )
        return {"items": [], "total_count": 0, "page": 1, "page_size": params.get("page_size", 20)}

    def get_temporary_item(
        self,
        temporary_item_id: str | int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a single temporary item by ID.

        Endpoint: GET /temporary-items/{temporary_item_id}

        Args:
            temporary_item_id: Temporary item identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Temporary item detail

        Raises:
            SyncServerAPIError: If the API request fails
            SyncNotFoundError: If the temporary item does not exist
        """
        logger.debug(
            "Fetching temporary item",
            extra={"temporary_item_id": temporary_item_id}
        )

        return self.client.get(
            f"/temporary-items/{temporary_item_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def list_temporary_item_operations(
        self,
        temporary_item_id: str | int,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of operations that reference a temporary item.

        Endpoint: GET /temporary-items/{temporary_item_id}/operations

        Args:
            temporary_item_id: Temporary item identifier
            filters: Optional filters for operations (e.g., page, page_size, type, status)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            list: List of operation dictionaries

        Raises:
            SyncServerAPIError: If the API request fails
        """
        logger.debug(
            "Fetching operations for temporary item",
            extra={"temporary_item_id": temporary_item_id}
        )

        params = self._build_filter_params(filters)
        response = self.client.get(
            f"/temporary-items/{temporary_item_id}/operations",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        if isinstance(response, dict) and "items" in response:
            return response["items"]
        elif isinstance(response, dict) and "operations" in response:
            return response["operations"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "Unexpected response format from /temporary-items/{temporary_item_id}/operations",
                extra={"response_type": type(response).__name__}
            )
            return []

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def approve_as_item(
        self,
        temporary_item_id: str | int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Approve a temporary item as a permanent catalog item.

        Endpoint: POST /temporary-items/{temporary_item_id}/approve

        Args:
            temporary_item_id: Temporary item identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Created catalog item detail

        Raises:
            SyncServerAPIError: If the API request fails
            SyncValidationError: If the temporary item cannot be approved
            SyncConflictError: If a catalog item with similar attributes already exists
        """
        logger.info(
            "Approving temporary item as catalog item",
            extra={"temporary_item_id": temporary_item_id}
        )

        return self.client.post(
            f"/temporary-items/{temporary_item_id}/approve-as-item",
            json={},
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def merge_to_item(
        self,
        temporary_item_id: str | int,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Merge a temporary item with an existing catalog item.

        Endpoint: POST /temporary-items/{temporary_item_id}/merge

        Args:
            temporary_item_id: Temporary item identifier
            payload: Merge payload with keys:
                - target_item_id (str | int): ID of the catalog item to merge into
                - keep_temporary_name (bool, optional): Whether to keep the temporary item's name
                - keep_temporary_sku (bool, optional): Whether to keep the temporary item's SKU
                - note (str, optional): Merge comment
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Updated catalog item detail

        Raises:
            SyncServerAPIError: If the API request fails
            SyncValidationError: If the merge cannot be performed
            SyncNotFoundError: If the target item does not exist
        """
        logger.info(
            "Merging temporary item with catalog item",
            extra={
                "temporary_item_id": temporary_item_id,
                "target_item_id": payload.get("target_item_id")
            }
        )

        return self.client.post(
            f"/temporary-items/{temporary_item_id}/merge",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def delete_temporary_item(
        self,
        temporary_item_id: str | int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Soft-delete a temporary item.

        Endpoint: DELETE /temporary-items/{temporary_item_id}

        Args:
            temporary_item_id: Temporary item identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Deletion result

        Raises:
            SyncServerAPIError: If the API request fails
            SyncNotFoundError: If the temporary item does not exist
            SyncValidationError: If the temporary item cannot be deleted
                (e.g., non-pending status, non-zero balance, active registers)
        """
        logger.info(
            "Deleting temporary item",
            extra={"temporary_item_id": temporary_item_id}
        )

        return self.client.delete(
            f"/temporary-items/{temporary_item_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _build_filter_params(self, filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
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
