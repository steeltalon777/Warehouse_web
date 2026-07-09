"""
Review Items API client module for SyncServer review-items endpoints.

This module provides high-level methods for interacting with SyncServer
review-items API using the base SyncServerClient.

Review items are permanent catalog items (Item.requires_review=True) that were
fast-created from operations and need confirmation/fix by a responsible user.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.review_items_api import ReviewItemsAPI

    client = SyncServerClient(user_id="user-123", site_id="site-456")
    review_api = ReviewItemsAPI(client)

    # List review items
    items = review_api.list_review_items(filters={})

    # Get specific review item detail
    item = review_api.get_review_item(42)

    # Confirm review item
    result = review_api.confirm_review_item(42, {"name": "Fixed Name"})

    # Merge review item
    result = review_api.merge_review_item(42, {"target_item_id": 100})

    # Delete unused review item
    result = review_api.delete_review_item(42)
"""

from __future__ import annotations

import structlog
from typing import Any

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = structlog.get_logger()


class ReviewItemsAPI:
    """
    High-level client for SyncServer review-items API.

    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """

    def __init__(self, client: SyncServerClient) -> None:
        self.client = client

    def list_review_items(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        List review-required catalog items.

        Args:
            filters: Optional dict with keys:
                - search (str): Search by name/sku/description
                - review_status (str): Filter by review status
                - created_by_user_id (str): Filter by creator
                - page (int): Page number (default: 1)
                - page_size (int): Items per page (default: 50)

        Returns:
            List of review item dicts

        Raises:
            SyncServerAPIError: On API error
        """
        filters = filters or {}
        params = self._build_filter_params(filters)
        data = self.client.get("/review-items", params=params)
        return data.get("items", [])

    def list_review_items_page(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        List review-required catalog items with full pagination metadata.

        Args:
            filters: Optional dict with keys:
                - search (str): Search by name/sku/description
                - review_status (str): Filter by review status
                - created_by_user_id (str): Filter by creator
                - page (int): Page number (default: 1)
                - page_size (int): Items per page (default: 50)

        Returns:
            Dict with keys: items, total_count, page, page_size

        Raises:
            SyncServerAPIError: On API error
        """
        filters = filters or {}
        params = self._build_filter_params(filters)
        return self.client.get("/review-items", params=params)

    def get_review_item(self, item_id: int) -> dict[str, Any]:
        """
        Get review item detail including balances and operations count.

        Args:
            item_id: SyncServer catalog item ID

        Returns:
            Review item detail dict

        Raises:
            SyncServerAPIError: On API error or item not found
        """
        return self.client.get(f"/review-items/{item_id}")

    def list_review_item_operations(self, item_id: int, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        List operations where the review item was used.

        Args:
            item_id: SyncServer catalog item ID
            filters: Optional pagination params (page, page_size)

        Returns:
            Dict with items, total_count, page, page_size
        """
        filters = filters or {}
        params = self._build_filter_params(filters)
        return self.client.get(f"/review-items/{item_id}/operations", params=params)

    def confirm_review_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Confirm a review-required item: clear review flag after validation.

        Args:
            item_id: SyncServer catalog item ID
            payload: Dict with optional fields to update:
                - name (str): Item name
                - sku (str): Item SKU
                - category_id (int): Category ID
                - unit_id (int): Unit ID
                - description (str): Item description
                - hashtags (list[str]): Item hashtags

        Returns:
            Updated review item dict

        Raises:
            SyncServerAPIError: On validation error
        """
        return self.client.post(f"/review-items/{item_id}/confirm", json=payload)

    def merge_review_item(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Merge review item into an existing catalog item.

        Args:
            item_id: SyncServer catalog item ID to merge from
            payload: Dict with:
                - target_item_id (int): Target catalog item ID
                - comment (str, optional): Resolution note

        Returns:
            Updated review item dict

        Raises:
            SyncServerAPIError: On validation/conflict error
        """
        return self.client.post(f"/review-items/{item_id}/merge", json=payload)

    def delete_review_item(self, item_id: int) -> dict[str, Any]:
        """
        Delete an unused review-required item.

        Args:
            item_id: SyncServer catalog item ID

        Returns:
            Deleted review item dict

        Raises:
            SyncServerAPIError: On conflict (has balances/usage)
        """
        return self.client.delete(f"/review-items/{item_id}")

    @staticmethod
    def _build_filter_params(filters: dict[str, Any]) -> dict[str, str]:
        """Convert filter dict to HTTP query params."""
        params: dict[str, str] = {}
        filter_mapping = {
            "search": "search",
            "review_status": "review_status",
            "created_by_user_id": "created_by_user_id",
            "page": "page",
            "page_size": "page_size",
        }
        for key, param_name in filter_mapping.items():
            value = filters.get(key)
            if value is not None:
                params[param_name] = str(value)
        return params
