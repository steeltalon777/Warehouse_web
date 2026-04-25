"""
Unit tests for sync_client API modules.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .client import SyncServerClient
from .temporary_items_api import TemporaryItemsAPI


class TemporaryItemsAPITests(SimpleTestCase):
    """Test cases for TemporaryItemsAPI."""

    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = TemporaryItemsAPI(client=self.mock_client)

    def test_init_without_client_creates_default(self) -> None:
        """TemporaryItemsAPI creates a default SyncServerClient when none provided."""
        with patch.object(SyncServerClient, "__init__", return_value=None) as mock_init:
            api = TemporaryItemsAPI()
            mock_init.assert_called_once()

    def test_list_temporary_items_calls_client_with_params(self) -> None:
        """list_temporary_items passes filters and returns items."""
        self.mock_client.get.return_value = {
            "items": [
                {"id": "temp-1", "name": "Item 1"},
                {"id": "temp-2", "name": "Item 2"},
            ]
        }

        result = self.api.list_temporary_items(
            filters={"site_id": "site-456", "status": "pending"},
            acting_user_id="user-123",
            acting_site_id="site-456",
        )

        self.mock_client.get.assert_called_once_with(
            "/temporary-items",
            params={"site_id": "site-456", "status": "pending"},
            acting_user_id="user-123",
            acting_site_id="site-456",
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "temp-1")

    def test_list_temporary_items_handles_list_response(self) -> None:
        """list_temporary_items handles direct list response."""
        self.mock_client.get.return_value = [
            {"id": "temp-1", "name": "Item 1"},
            {"id": "temp-2", "name": "Item 2"},
        ]

        result = self.api.list_temporary_items()
        self.assertEqual(len(result), 2)

    def test_list_temporary_items_handles_temporary_items_key(self) -> None:
        """list_temporary_items handles response with 'temporary_items' key."""
        self.mock_client.get.return_value = {
            "temporary_items": [{"id": "temp-1", "name": "Item 1"}]
        }

        result = self.api.list_temporary_items()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "temp-1")

    def test_list_temporary_items_handles_unexpected_format(self) -> None:
        """list_temporary_items returns empty list for unexpected format."""
        self.mock_client.get.return_value = {"data": []}

        result = self.api.list_temporary_items()
        self.assertEqual(result, [])

    def test_list_temporary_items_page_calls_client(self) -> None:
        """list_temporary_items_page returns paginated response."""
        self.mock_client.get.return_value = {
            "items": [{"id": "temp-1"}],
            "total_count": 1,
            "page": 1,
            "page_size": 20,
        }

        result = self.api.list_temporary_items_page(
            filters={"page": 2, "page_size": 10}
        )

        self.mock_client.get.assert_called_once_with(
            "/temporary-items",
            params={"page": 2, "page_size": 10},
            acting_user_id=None,
            acting_site_id=None,
        )
        self.assertEqual(result["items"][0]["id"], "temp-1")
        self.assertEqual(result["total_count"], 1)

    def test_list_temporary_items_page_handles_temporary_items_key(self) -> None:
        """list_temporary_items_page converts 'temporary_items' to 'items'."""
        self.mock_client.get.return_value = {
            "temporary_items": [{"id": "temp-1"}],
            "total_count": 5,
        }

        result = self.api.list_temporary_items_page()
        self.assertEqual(result["items"][0]["id"], "temp-1")
        self.assertEqual(result["total_count"], 5)

    def test_list_temporary_items_page_handles_list_response(self) -> None:
        """list_temporary_items_page builds paginated dict from list."""
        self.mock_client.get.return_value = [{"id": "temp-1"}, {"id": "temp-2"}]

        result = self.api.list_temporary_items_page(filters={"page_size": 10})
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 10)

    def test_get_temporary_item_calls_client_with_id(self) -> None:
        """get_temporary_item calls correct endpoint."""
        self.mock_client.get.return_value = {"id": "temp-123", "name": "Test Item"}

        result = self.api.get_temporary_item(
            "temp-123",
            acting_user_id="user-123",
            acting_site_id="site-456",
        )

        self.mock_client.get.assert_called_once_with(
            "/temporary-items/temp-123",
            acting_user_id="user-123",
            acting_site_id="site-456",
        )
        self.assertEqual(result["id"], "temp-123")

    def test_list_temporary_item_operations_calls_client(self) -> None:
        """list_temporary_item_operations calls correct endpoint."""
        self.mock_client.get.return_value = {
            "operations": [{"id": "op-1", "type": "RECEIVE"}]
        }

        result = self.api.list_temporary_item_operations(
            "temp-123",
            filters={"page": 1},
            acting_user_id="user-123",
        )

        self.mock_client.get.assert_called_once_with(
            "/temporary-items/temp-123/operations",
            params={"page": 1},
            acting_user_id="user-123",
            acting_site_id=None,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "RECEIVE")

    def test_approve_as_item_calls_client_post(self) -> None:
        """approve_as_item calls POST /temporary-items/{id}/approve."""
        self.mock_client.post.return_value = {
            "id": "item-456",
            "name": "Approved Item",
        }

        result = self.api.approve_as_item(
            "temp-123",
            acting_user_id="user-123",
            acting_site_id="site-456",
        )

        self.mock_client.post.assert_called_once_with(
            "/temporary-items/temp-123/approve",
            json={},
            acting_user_id="user-123",
            acting_site_id="site-456",
        )
        self.assertEqual(result["id"], "item-456")

    def test_merge_to_item_calls_client_with_payload(self) -> None:
        """merge_to_item calls POST /temporary-items/{id}/merge with payload."""
        payload = {
            "target_item_id": "item-789",
            "keep_temporary_name": True,
            "note": "Merged",
        }
        self.mock_client.post.return_value = {
            "id": "item-789",
            "name": "Merged Item",
        }

        result = self.api.merge_to_item(
            "temp-123",
            payload,
            acting_user_id="user-123",
        )

        self.mock_client.post.assert_called_once_with(
            "/temporary-items/temp-123/merge",
            json=payload,
            acting_user_id="user-123",
            acting_site_id=None,
        )
        self.assertEqual(result["id"], "item-789")

    def test_build_filter_params_removes_none(self) -> None:
        """_build_filter_params removes None values."""
        params = self.api._build_filter_params(
            {"site_id": "site-1", "status": None, "search": "test"}
        )
        self.assertEqual(params, {"site_id": "site-1", "search": "test"})

    def test_build_filter_params_converts_pagination(self) -> None:
        """_build_filter_params does NOT convert page and page_size to int (keeps original)."""
        params = self.api._build_filter_params(
            {"page": "2", "page_size": "10", "search": "test"}
        )
        self.assertEqual(params, {"page": "2", "page_size": "10", "search": "test"})

    def test_build_filter_params_empty(self) -> None:
        """_build_filter_params returns empty dict for None."""
        params = self.api._build_filter_params(None)
        self.assertEqual(params, {})

    def test_build_filter_params_empty_dict(self) -> None:
        """_build_filter_params returns empty dict for empty dict."""
        params = self.api._build_filter_params({})
        self.assertEqual(params, {})
