"""
Unit tests for sync_client API modules.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import httpx
from django.test import SimpleTestCase

from .assets_api import AssetsAPI
from .client import SyncServerClient
from .exceptions import (
    SyncConflictError,
    SyncForbiddenError,
    SyncValidationError,
)
from .issue_objects_api import IssueObjectsAPI
from .issue_object_categories_api import IssueObjectCategoriesAPI
from .operations_api import OperationsAPI
from .temporary_items_api import TemporaryItemsAPI


class OperationsAPITests(SimpleTestCase):
    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = OperationsAPI(client=self.mock_client)

    def test_accept_operation_lines_uses_base_relative_path(self) -> None:
        payload = {"lines": [{"line_id": 10, "accepted_qty": "1", "lost_qty": "0"}]}

        self.api.accept_operation_lines("op-1", payload)

        self.mock_client.post.assert_called_once_with(
            "/operations/op-1/accept-lines",
            json=payload,
            acting_user_id=None,
            acting_site_id=None,
            extra_headers=None,
            return_response=False,
        )


    def test_delete_operation_calls_client_delete(self) -> None:
        self.api.delete_operation("op-1")

        self.mock_client.delete.assert_called_once_with(
            "/operations/op-1",
            acting_user_id=None,
            acting_site_id=None,
            extra_headers=None,
            return_response=False,
        )

    def test_create_operation_from_source_document_uses_base_relative_path(self) -> None:
        payload = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "source_ref": "invoice-2026-07-23-001",
            "source_document_type": "invoice",
            "lines": [
                {"line_number": 1, "item_id": 3186, "qty": "10"},
            ],
        }

        self.api.create_operation_from_source_document(payload)

        self.mock_client.post.assert_called_once_with(
            "/operations/from-source-document",
            json=payload,
            acting_user_id=None,
            acting_site_id=None,
            extra_headers=None,
            return_response=False,
        )

    def test_create_operation_from_source_document_propagates_extra_headers(self) -> None:
        payload = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "source_ref": "invoice-x",
            "source_document_type": "ocr_scan",
            "lines": [{"line_number": 1, "item_id": 100, "qty": "5"}],
        }
        headers = {"X-Request-Id": "abc-123"}

        self.api.create_operation_from_source_document(
            payload, extra_headers=headers,
        )

        self.mock_client.post.assert_called_once_with(
            "/operations/from-source-document",
            json=payload,
            acting_user_id=None,
            acting_site_id=None,
            extra_headers=headers,
            return_response=False,
        )

    def test_create_operation_from_source_document_return_response_tuple(self) -> None:
        self.mock_client.post.return_value = ({"id": "op-1"}, {"X-Request-Id": "rid-1"})
        payload = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "source_ref": "invoice-rt",
            "source_document_type": "invoice",
            "lines": [{"line_number": 1, "item_id": 1, "qty": "1"}],
        }

        result = self.api.create_operation_from_source_document(
            payload, return_response=True,
        )

        self.assertEqual(result, ({"id": "op-1"}, {"X-Request-Id": "rid-1"}))
        self.mock_client.post.assert_called_once_with(
            "/operations/from-source-document",
            json=payload,
            acting_user_id=None,
            acting_site_id=None,
            extra_headers=None,
            return_response=True,
        )


class AssetsAPITests(SimpleTestCase):
    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = AssetsAPI(client=self.mock_client)

    def test_list_issued_assets_calls_correct_path(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_issued_assets(filters={"issue_object_id": "1", "page": "1"})

        self.mock_client.get.assert_called_once_with(
            "/issued-assets",
            params={"issue_object_id": "1", "page": "1"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_issued_assets_normalises_response(self) -> None:
        self.mock_client.get.return_value = [{"id": "a1"}]

        result = self.api.list_issued_assets()

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["items"]), 1)

    def test_lost_assets_paths_are_base_relative(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_lost_assets()
        self.api.get_lost_asset(5)
        self.api.resolve_lost_asset(5, {"action": "write_off", "qty": "1"})

        self.assertEqual(self.mock_client.get.call_args_list[0].args[0], "/lost-assets")
        self.assertEqual(self.mock_client.get.call_args_list[1].args[0], "/lost-assets/5")
        self.assertEqual(self.mock_client.post.call_args.args[0], "/lost-assets/5/resolve")


class IssueObjectsAPITests(SimpleTestCase):
    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = IssueObjectsAPI(client=self.mock_client)

    def test_list_issue_objects_passes_params(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_issue_objects(filters={"search": "Test", "page": "1"})

        self.mock_client.get.assert_called_once_with(
            "/issue-objects",
            params={"search": "Test", "page": "1"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_issue_objects_normalises_list_response(self) -> None:
        self.mock_client.get.return_value = [{"id": "1"}, {"id": "2"}]

        result = self.api.list_issue_objects()

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(len(result["items"]), 2)

    def test_create_issue_object_posts_payload(self) -> None:
        self.mock_client.post.return_value = {"id": "1"}

        self.api.create_issue_object({"name": "Test"})

        self.mock_client.post.assert_called_once_with(
            "/issue-objects",
            json={"name": "Test"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_get_issue_object_calls_correct_path(self) -> None:
        self.mock_client.get.return_value = {"id": "1"}

        self.api.get_issue_object("1")

        self.mock_client.get.assert_called_once_with(
            "/issue-objects/1",
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_update_issue_object_patches_payload(self) -> None:
        self.mock_client.patch.return_value = {"id": "1", "name": "Updated"}

        self.api.update_issue_object("1", {"name": "Updated"})

        self.mock_client.patch.assert_called_once_with(
            "/issue-objects/1",
            json={"name": "Updated"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_delete_issue_object_calls_delete(self) -> None:
        self.mock_client.delete.return_value = None

        self.api.delete_issue_object("1")

        self.mock_client.delete.assert_called_once_with(
            "/issue-objects/1",
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_merge_issue_objects_posts_merge(self) -> None:
        self.mock_client.post.return_value = {"merged": True}

        self.api.merge_issue_objects({"source_id": 1, "target_id": 2})

        self.mock_client.post.assert_called_once_with(
            "/issue-objects/merge",
            json={"source_id": 1, "target_id": 2},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_object_assets_passes_params(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_object_assets("1", filters={"page": "1"})

        self.mock_client.get.assert_called_once_with(
            "/issue-objects/1/assets",
            params={"page": "1"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_object_assets_normalises_list_response(self) -> None:
        self.mock_client.get.return_value = [{"id": "a1"}]

        result = self.api.list_object_assets("1")

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["items"]), 1)

    def test_list_issue_objects_handles_unexpected_format(self) -> None:
        self.mock_client.get.return_value = {"data": []}

        result = self.api.list_issue_objects()

        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_count"], 0)


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
        """approve_as_item calls POST /temporary-items/{id}/approve-as-item."""
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
            "/temporary-items/temp-123/approve-as-item",
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


class IssueObjectCategoriesAPITests(SimpleTestCase):
    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = IssueObjectCategoriesAPI(client=self.mock_client)

    def test_list_categories_passes_params(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_categories(filters={"search": "Test", "page": "1"})

        self.mock_client.get.assert_called_once_with(
            "/issue-object-categories",
            params={"search": "Test", "page": "1"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_categories_normalises_list_response(self) -> None:
        self.mock_client.get.return_value = [{"id": "1"}, {"id": "2"}]

        result = self.api.list_categories()

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(len(result["items"]), 2)

    def test_list_categories_normalises_dict_response(self) -> None:
        self.mock_client.get.return_value = {
            "items": [{"id": "1"}],
            "total_count": 1,
        }

        result = self.api.list_categories()

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["items"]), 1)

    def test_list_categories_handles_unexpected_format(self) -> None:
        self.mock_client.get.return_value = {"data": []}

        result = self.api.list_categories()

        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_count"], 0)

    def test_create_category_posts_payload(self) -> None:
        self.mock_client.post.return_value = {"id": "1"}

        self.api.create_category({"name": "Test Category"})

        self.mock_client.post.assert_called_once_with(
            "/issue-object-categories",
            json={"name": "Test Category"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_get_category_calls_correct_path(self) -> None:
        self.mock_client.get.return_value = {"id": 1}

        self.api.get_category(1)

        self.mock_client.get.assert_called_once_with(
            "/issue-object-categories/1",
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_update_category_patches_payload(self) -> None:
        self.mock_client.patch.return_value = {"id": 1, "name": "Updated"}

        self.api.update_category(1, {"name": "Updated"})

        self.mock_client.patch.assert_called_once_with(
            "/issue-object-categories/1",
            json={"name": "Updated"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_delete_category_calls_delete(self) -> None:
        self.mock_client.delete.return_value = None

        self.api.delete_category(1)

        self.mock_client.delete.assert_called_once_with(
            "/issue-object-categories/1",
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_list_categories_filters_propagates_filters(self) -> None:
        self.mock_client.get.return_value = {"items": []}

        self.api.list_categories(
            filters={
                "search": "test",
                "parent_id": "5",
                "is_active": "true",
                "include_deleted": "false",
                "page": "2",
                "page_size": "50",
            }
        )

        self.mock_client.get.assert_called_once_with(
            "/issue-object-categories",
            params={
                "search": "test",
                "parent_id": "5",
                "is_active": "true",
                "include_deleted": "false",
                "page": "2",
                "page_size": "50",
            },
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_delete_category_returns_none_on_204(self) -> None:
        self.mock_client.delete.return_value = None

        result = self.api.delete_category(1)

        self.assertIsNone(result)


class IssueObjectsTreeAPITests(SimpleTestCase):
    def setUp(self) -> None:
        self.mock_client = Mock(spec=SyncServerClient)
        self.api = IssueObjectsAPI(client=self.mock_client)

    def test_get_tree_calls_correct_path(self) -> None:
        self.mock_client.get.return_value = []

        self.api.get_tree()

        self.mock_client.get.assert_called_once_with(
            "/issue-objects/tree",
            params={},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_get_tree_passes_filters(self) -> None:
        self.mock_client.get.return_value = []

        self.api.get_tree(filters={"search": "test", "include_inactive": "true", "include_deleted": "false"})

        self.mock_client.get.assert_called_once_with(
            "/issue-objects/tree",
            params={"search": "test", "include_inactive": "true", "include_deleted": "false"},
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_get_tree_returns_list(self) -> None:
        nodes = [
            {"id": 1, "type": "category", "name": "Cat 1", "children": []},
            {"id": 2, "type": "object", "name": "Obj 1", "category_id": 1},
        ]
        self.mock_client.get.return_value = nodes

        result = self.api.get_tree()

        self.assertEqual(result, nodes)
        self.assertEqual(len(result), 2)

    def test_get_tree_handles_unexpected_format(self) -> None:
        self.mock_client.get.return_value = {"data": []}

        result = self.api.get_tree()

        self.assertEqual(result, [])


class SyncServerClientRaiseForResponseTests(SimpleTestCase):
    """Tests for ``SyncServerClient._raise_for_response`` message extraction.

    TZ-OPERATION_CANCEL_DOMAIN_ERRORS §7.3: dict ``detail`` (SyncServer problem
    envelope) must be unwrapped into a readable ``exc.message`` instead of a
    Python-repr of the whole dict. ``exc.payload`` keeps the full sanitized body.
    """

    def setUp(self) -> None:
        self.client = SyncServerClient.__new__(SyncServerClient)

    @staticmethod
    def _response(status_code: int, body: dict) -> httpx.Response:
        return httpx.Response(
            status_code,
            json=body,
            request=httpx.Request("POST", "http://sync.test/api/v1/operations/op1/cancel"),
        )

    def test_dict_detail_message_used_as_exc_message(self) -> None:
        body = {
            "detail": {
                "message": "Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 2, на складе 0.",
                "code": "operation_cancel_rejected",
            }
        }

        with self.assertRaises(SyncConflictError) as ctx:
            self.client._raise_for_response(
                self._response(409, body), method="POST", path="/operations/op1/cancel"
            )

        exc = ctx.exception
        self.assertEqual(str(exc), "Недостаточно товара: Кабель ВВГ 3×2.5 — запрошено 2, на складе 0.")
        self.assertNotEqual(str(exc), str(body.get("detail")))
        self.assertEqual(exc.status_code, 409)
        self.assertEqual(exc.payload, body)

    def test_dict_detail_without_message_falls_back_to_nested_detail(self) -> None:
        body = {
            "detail": {
                "detail": "Недостаточно товара на складе 0",
                "code": "operation_cancel_rejected",
            }
        }

        with self.assertRaises(SyncConflictError) as ctx:
            self.client._raise_for_response(
                self._response(409, body), method="POST", path="/operations/op1/cancel"
            )

        exc = ctx.exception
        self.assertEqual(str(exc), "Недостаточно товара на складе 0")
        self.assertEqual(exc.payload, body)

    def test_dict_detail_without_message_or_detail_keeps_full_payload(self) -> None:
        body = {"detail": {"code": "operation_cancel_rejected"}}

        with self.assertRaises(SyncConflictError) as ctx:
            self.client._raise_for_response(
                self._response(409, body), method="POST", path="/operations/op1/cancel"
            )

        exc = ctx.exception
        self.assertEqual(exc.payload, body)
        self.assertTrue(str(exc))

    def test_string_detail_keeps_plain_message(self) -> None:
        body = {"detail": "operation is already cancelled"}

        with self.assertRaises(SyncConflictError) as ctx:
            self.client._raise_for_response(
                self._response(409, body), method="POST", path="/operations/op1/cancel"
            )

        exc = ctx.exception
        self.assertEqual(str(exc), "operation is already cancelled")
        self.assertEqual(exc.payload, body)

    def test_dict_detail_forbidden_maps_to_sync_forbidden(self) -> None:
        body = {"detail": {"message": "Доступ запрещён.", "code": "role_not_permitted"}}

        with self.assertRaises(SyncForbiddenError) as ctx:
            self.client._raise_for_response(
                self._response(403, body), method="POST", path="/operations/op1/cancel"
            )

        self.assertEqual(str(ctx.exception), "Доступ запрещён.")
        self.assertEqual(ctx.exception.payload, body)

    def test_dict_detail_validation_error_maps_to_sync_validation(self) -> None:
        body = {"detail": {"message": "cancel must be true"}}

        with self.assertRaises(SyncValidationError) as ctx:
            self.client._raise_for_response(
                self._response(422, body), method="POST", path="/operations/op1/cancel"
            )

        self.assertEqual(str(ctx.exception), "cancel must be true")
        self.assertEqual(ctx.exception.payload, body)
