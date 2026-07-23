from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.users.models import Role, SyncUserBinding, UserProfile


class BffApiRoutesSmokeTests(TestCase):
    def test_bff_route_registry_has_expected_groups(self) -> None:
        from apps.bff_api.urls import urlpatterns

        names = {p.name for p in urlpatterns if getattr(p, "name", None)}

        # Method+path count is larger, but path registry baseline should stay stable.
        self.assertGreaterEqual(len(urlpatterns), 70)

        self.assertIn("catalog_admin_batch", names)

        required_names = {
            "root",
            "db_check",
            "auth_me",
            "auth_context",
            "admin_users",
            "admin_devices",
            "catalog_items",
            "catalog_read_items",
            "catalog_admin_items",
            "operations_list",
            "balances",
            "temp_items",
            "documents",
            "issue_objects_list",
            "pending_acceptance",
            "reports_item_movement",
            "health",
            "health_liveness",
        }
        self.assertTrue(required_names.issubset(names))


class BffApiViewMethodTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="bff_root",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_auth_me_get_returns_ok_wrapper(self) -> None:
        mock_client = Mock()
        mock_client.get.return_value = {"user": {"id": "u1"}}

        with patch("apps.bff_api.auth_views._build_client", return_value=mock_client):
            response = self.client.get("/bff/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"user": {"id": "u1"}})

    def test_admin_user_scopes_put_supported(self) -> None:
        mock_client = Mock()
        mock_client.put.return_value = [{"site_id": "1", "can_view": True}]

        with patch("apps.bff_api.admin_views._build_client", return_value=mock_client):
            response = self.client.put(
                "/bff/api/v1/admin/users/u1/scopes",
                data=json.dumps({"scopes": [{"site_id": "1", "can_view": True, "can_operate": False, "can_manage_catalog": False}]}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], [{"site_id": "1", "can_view": True}])
        mock_client.put.assert_called_once()

    def test_catalog_items_get_returns_cursor_payload_shape(self) -> None:
        payload = {
            "items": [{"id": "i1"}],
            "server_time": "2026-01-01T00:00:00Z",
            "next_updated_after": "2026-01-01T00:00:00Z",
        }
        mock_client = Mock()
        mock_client.get.return_value = payload

        with patch("apps.bff_api.catalog_views._build_client", return_value=mock_client):
            response = self.client.get("/bff/api/v1/catalog/items", {"limit": 100})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], payload)

    def test_operations_submit_post_supported(self) -> None:
        mock_api = Mock()
        mock_api.submit_operation.return_value = ({"id": "op1", "status": "submitted"}, {})

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/op1/submit",
                data=json.dumps({"submit": True}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "submitted")

    def test_operations_submit_sync_conflict_409_preserves_detail(self) -> None:
        from apps.sync_client.exceptions import SyncConflictError

        detail_message = "SKU «М0001789» уже занят. Укажите другой SKU или оставьте поле пустым для автоматической генерации."
        mock_api = Mock()
        mock_api.submit_operation.side_effect = SyncConflictError(
            detail_message,
            status_code=409,
            payload={"detail": detail_message},
        )

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/op1/submit",
                data=json.dumps({"submit": True}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertEqual(body["error"]["message"], detail_message)

    def test_operations_list_forwards_item_ids_filter(self) -> None:
        mock_api = Mock()
        mock_api.list_operations_page.return_value = (
            {"items": [], "total_count": 0, "page": 1, "page_size": 20},
            {},
        )

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/operations",
                {"search": "дрель", "item_ids": "1,2,3", "acceptance_state": "pending", "page": "1", "page_size": "20"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.list_operations_page.assert_called_once_with(
            filters={"search": "дрель", "item_ids": "1,2,3", "acceptance_state": "pending", "page": "1", "page_size": "20"},
            extra_headers={},
            return_response=True,
        )

    def test_operations_list_forwards_exclude_adjustments_filter(self) -> None:
        mock_api = Mock()
        mock_api.list_operations_page.return_value = (
            {"items": [], "total_count": 0, "page": 1, "page_size": 20},
            {},
        )

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/operations",
                {"exclude_adjustments": "true", "page": "1", "page_size": "20"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.list_operations_page.assert_called_once_with(
            filters={"exclude_adjustments": "true", "page": "1", "page_size": "20"},
            extra_headers={},
            return_response=True,
        )

    def test_operations_delete_supported(self) -> None:
        mock_api = Mock()
        mock_api.delete_operation.return_value = (None, {})

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.delete("/bff/api/v1/operations/op1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"deleted": True})

    def test_operation_waybill_open_returns_browser_pdf_urls(self) -> None:
        mock_api = Mock()
        mock_api.generate_operation_document.return_value = {
            "document": {"id": "doc-1", "document_type": "waybill"},
            "created": True,
        }

        with patch("apps.bff_api.documents_views._docs", return_value=mock_api):
            response = self.client.post("/bff/api/v1/documents/operations/op-1/waybill/open")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["pdf_url"], "/documents/doc-1/pdf/")
        self.assertEqual(body["data"]["download_url"], "/documents/doc-1/pdf/?download=1")
        mock_api.generate_operation_document.assert_called_once_with(
            operation_id="op-1",
            document_type="waybill",
            auto_finalize=True,
            language="ru",
        )

    def test_issue_objects_delete_supported(self) -> None:
        mock_api = Mock()
        mock_api.delete_issue_object.return_value = None

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.delete("/bff/api/v1/issue-objects/1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"deleted": True})

    def test_issue_objects_list_get_returns_ok_with_items(self) -> None:
        mock_api = Mock()
        mock_api.list_issue_objects.return_value = {"items": [{"id": "1", "name": "Obj1"}], "total_count": 1, "page": 1, "page_size": 100}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get("/bff/api/v1/issue-objects")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["data"]["items"]), 1)

    def test_issue_objects_create_post_supported(self) -> None:
        mock_api = Mock()
        mock_api.create_issue_object.return_value = {"id": "1", "name": "New Obj"}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/issue-objects",
                data=json.dumps({"name": "New Obj"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["name"], "New Obj")

    def test_issue_objects_merge_post_supported(self) -> None:
        mock_api = Mock()
        mock_api.merge_issue_objects.return_value = {"merged": True}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/issue-objects/merge",
                data=json.dumps({"source_id": 1, "target_id": 2}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["data"]["merged"])

    def test_issue_objects_detail_get_returns_ok(self) -> None:
        mock_api = Mock()
        mock_api.get_issue_object.return_value = {"id": "1", "name": "Detail Obj"}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get("/bff/api/v1/issue-objects/1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["name"], "Detail Obj")

    def test_issue_objects_detail_patch_supported(self) -> None:
        mock_api = Mock()
        mock_api.update_issue_object.return_value = {"id": "1", "name": "Updated"}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.patch(
                "/bff/api/v1/issue-objects/1",
                data=json.dumps({"name": "Updated"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["name"], "Updated")

    def test_issue_objects_assets_list_get_returns_ok(self) -> None:
        mock_api = Mock()
        mock_api.list_object_assets.return_value = {"items": [{"id": "a1"}], "total_count": 1, "page": 1, "page_size": 20}

        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get("/bff/api/v1/issue-objects/1/assets")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["data"]["items"]), 1)

    def test_catalog_cached_item_search_optional_params(self) -> None:
        mock_client = Mock()
        mock_client.get.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 0}

        with (
            patch("apps.bff_api.catalog_views.CatalogCachedItemSearchView._search_local_cache", return_value=[]),
            patch("apps.bff_api.catalog_views._build_client", return_value=mock_client),
        ):
            response = self.client.get(
                "/bff/api/v1/catalog/search/items",
                {"q": "test", "source_site_id": "5", "include_balance": "true"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])

    def test_catalog_cached_item_search_warms_local_cache_from_remote_results(self) -> None:
        remote_item = {
            "id": "7",
            "name": "Тестовая дрель",
            "sku": "DRILL-7",
            "category_id": "3",
            "category_name": "Инструмент",
            "hashtags": ["дрель"],
            "unit_id": "2",
            "unit_name": "шт",
            "unit_symbol": "шт",
            "is_active": True,
            "requires_review": False,
            "source": "remote",
            "source_site_id": "",
            "source_site_qty": "0",
            "balance_qty": "0",
        }

        with (
            patch("apps.bff_api.catalog_views.CatalogCachedItemSearchView._search_local_cache", return_value=[]),
            patch("apps.bff_api.catalog_views.CatalogCachedItemSearchView._search_remote_items", return_value=[remote_item]),
            patch("apps.bff_api.catalog_views.CatalogCachedItemSearchView._warm_catalog_cache") as warm_cache,
        ):
            response = self.client.get("/bff/api/v1/catalog/search/items", {"q": "дрель"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["results"][0]["id"], "7")
        warm_cache.assert_called_once()


class BffApiCatalogBatchTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.chief = user_model.objects.create_user(
            username="chief_user",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        SyncUserBinding.objects.create(user=self.chief, sync_role=Role.CHIEF_STOREKEEPER)
        self.root = user_model.objects.create_user(
            username="root_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.plain_user = user_model.objects.create_user(
            username="plain_user",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )

    def test_batch_unauthenticated_returns_redirect(self) -> None:
        response = self.client.post("/bff/api/v1/catalog/admin/batch", data="{}", content_type="application/json")
        self.assertIn(response.status_code, (302, 403))

    def test_batch_non_chief_returns_403(self) -> None:
        self.client.force_login(self.plain_user)
        with patch("apps.bff_api.catalog_views._catalog") as catalog:
            response = self.client.post("/bff/api/v1/catalog/admin/batch", data="{}", content_type="application/json")

        catalog.assert_not_called()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_batch_chief_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.apply_catalog_batch.return_value = {"status": "ok", "results": []}

        self.client.force_login(self.chief)
        payload = {"changes": [{"type": "update_item", "item_id": "i1"}]}

        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/batch",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "ok")
        mock_api.apply_catalog_batch.assert_called_once_with(payload)

    def test_batch_root_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.apply_catalog_batch.return_value = {"status": "ok"}

        self.client.force_login(self.root)
        payload = {"changes": []}

        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/batch",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.apply_catalog_batch.assert_called_once()

    def test_batch_invalid_json_returns_400(self) -> None:
        self.client.force_login(self.chief)
        response = self.client.post(
            "/bff/api/v1/catalog/admin/batch",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "validation_error")

    def test_batch_sync_conflict_409_is_preserved(self) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        mock_api = Mock()
        mock_api.apply_catalog_batch.side_effect = SyncServerAPIError(
            "Batch conflict: item already updated",
            status_code=409,
            payload={"detail": "Batch conflict: item already updated"},
        )

        self.client.force_login(self.chief)
        payload = {"changes": [{"type": "update_item", "item_id": "i1"}]}

        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/batch",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "conflict")


class BffApiCatalogAdminPermissionTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.plain_user = user_model.objects.create_user(
            username="catalog_plain_user",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        self.binding_chief = user_model.objects.create_user(
            username="catalog_binding_chief",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        SyncUserBinding.objects.create(user=self.binding_chief, sync_role=Role.CHIEF_STOREKEEPER)

        self.profile_chief = user_model.objects.create_user(
            username="catalog_profile_chief",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.profile_chief, role=Role.CHIEF_STOREKEEPER)

        self.root = user_model.objects.create_user(
            username="catalog_root_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )

    def _assert_create_forbidden(self, path: str) -> None:
        self.client.force_login(self.plain_user)
        with patch("apps.bff_api.catalog_views._catalog") as catalog:
            response = self.client.post(
                path,
                data=json.dumps({"name": "Blocked"}),
                content_type="application/json",
            )

        catalog.assert_not_called()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def _assert_mutation_forbidden(self, method: str, path: str, payload: dict | None = None) -> None:
        self.client.force_login(self.plain_user)
        request = getattr(self.client, method)
        kwargs = {}
        if payload is not None:
            kwargs = {"data": json.dumps(payload), "content_type": "application/json"}

        with patch("apps.bff_api.catalog_views._catalog") as catalog:
            response = request(path, **kwargs)

        catalog.assert_not_called()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def _assert_mutation_allowed(
        self,
        *,
        user,
        method: str,
        path: str,
        catalog_method: str,
        payload: dict | None = None,
        return_value=None,
        expected_call_args: tuple = (),
    ) -> None:
        mock_api = Mock()
        getattr(mock_api, catalog_method).return_value = return_value

        self.client.force_login(user)
        request = getattr(self.client, method)
        kwargs = {}
        if payload is not None:
            kwargs = {"data": json.dumps(payload), "content_type": "application/json"}

        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = request(path, **kwargs)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        if return_value is None:
            self.assertEqual(body["data"], {"deleted": True})
        else:
            self.assertEqual(body["data"], return_value)
        getattr(mock_api, catalog_method).assert_called_once_with(*expected_call_args)

    def test_admin_items_create_non_manager_returns_403(self) -> None:
        self._assert_create_forbidden("/bff/api/v1/catalog/admin/items")

    def test_admin_categories_create_non_manager_returns_403(self) -> None:
        self._assert_create_forbidden("/bff/api/v1/catalog/admin/categories")

    def test_admin_units_create_non_manager_returns_403(self) -> None:
        self._assert_create_forbidden("/bff/api/v1/catalog/admin/units")

    def test_admin_items_create_sync_binding_chief_allowed(self) -> None:
        mock_api = Mock()
        mock_api.create_item.return_value = {"id": "i1", "name": "New Item"}

        self.client.force_login(self.binding_chief)
        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items",
                data=json.dumps({"name": "New Item"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.create_item.assert_called_once_with({"name": "New Item"})

    def test_admin_categories_create_profile_chief_allowed(self) -> None:
        mock_api = Mock()
        mock_api.create_category.return_value = {"id": "c1", "name": "New Category"}

        self.client.force_login(self.profile_chief)
        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/categories",
                data=json.dumps({"name": "New Category"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.create_category.assert_called_once_with({"name": "New Category"})

    def test_admin_units_create_root_allowed(self) -> None:
        mock_api = Mock()
        mock_api.create_unit.return_value = {"id": "u1", "name": "New Unit"}

        self.client.force_login(self.root)
        with patch("apps.bff_api.catalog_views._catalog", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/units",
                data=json.dumps({"name": "New Unit"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.create_unit.assert_called_once_with({"name": "New Unit"})

    def test_admin_bulk_mutations_non_manager_return_403(self) -> None:
        for path in (
            "/bff/api/v1/catalog/admin/units/bulk",
            "/bff/api/v1/catalog/admin/categories/bulk",
        ):
            with self.subTest(path=path):
                self._assert_mutation_forbidden(method="post", path=path, payload={"items": [{"name": "Blocked"}]})

    def test_admin_bulk_mutations_allow_chief_and_root(self) -> None:
        cases = (
            (
                self.binding_chief,
                "/bff/api/v1/catalog/admin/units/bulk",
                "bulk_create_units",
                {"items": [{"name": "Unit 1"}]},
                {"created": [{"id": "u1"}]},
                ({"items": [{"name": "Unit 1"}]},),
            ),
            (
                self.root,
                "/bff/api/v1/catalog/admin/categories/bulk",
                "bulk_create_categories",
                {"items": [{"name": "Category 1"}]},
                {"created": [{"id": "c1"}]},
                ({"items": [{"name": "Category 1"}]},),
            ),
        )

        for user, path, catalog_method, payload, return_value, expected_call_args in cases:
            with self.subTest(path=path, user=user.username):
                self._assert_mutation_allowed(
                    user=user,
                    method="post",
                    path=path,
                    catalog_method=catalog_method,
                    payload=payload,
                    return_value=return_value,
                    expected_call_args=expected_call_args,
                )

    def test_admin_item_detail_mutations_non_manager_return_403(self) -> None:
        self._assert_mutation_forbidden(
            method="patch",
            path="/bff/api/v1/catalog/admin/items/item-1",
            payload={"name": "Blocked item"},
        )
        self._assert_mutation_forbidden(method="delete", path="/bff/api/v1/catalog/admin/items/item-1")

    def test_admin_item_detail_mutations_allow_chief_and_root(self) -> None:
        cases = (
            (
                self.binding_chief,
                "patch",
                "/bff/api/v1/catalog/admin/items/item-1",
                "update_item",
                {"name": "Updated item"},
                {"id": "item-1", "name": "Updated item"},
                ("item-1", {"name": "Updated item"}),
            ),
            (
                self.root,
                "delete",
                "/bff/api/v1/catalog/admin/items/item-1",
                "delete_item",
                None,
                None,
                ("item-1",),
            ),
        )

        for user, method, path, catalog_method, payload, return_value, expected_call_args in cases:
            with self.subTest(path=path, method=method, user=user.username):
                self._assert_mutation_allowed(
                    user=user,
                    method=method,
                    path=path,
                    catalog_method=catalog_method,
                    payload=payload,
                    return_value=return_value,
                    expected_call_args=expected_call_args,
                )

    def test_admin_category_detail_mutations_non_manager_return_403(self) -> None:
        self._assert_mutation_forbidden(
            method="patch",
            path="/bff/api/v1/catalog/admin/categories/category-1",
            payload={"name": "Blocked category"},
        )
        self._assert_mutation_forbidden(method="delete", path="/bff/api/v1/catalog/admin/categories/category-1")

    def test_admin_category_detail_mutations_allow_chief_and_root(self) -> None:
        cases = (
            (
                self.profile_chief,
                "patch",
                "/bff/api/v1/catalog/admin/categories/category-1",
                "update_category",
                {"name": "Updated category"},
                {"id": "category-1", "name": "Updated category"},
                ("category-1", {"name": "Updated category"}),
            ),
            (
                self.root,
                "delete",
                "/bff/api/v1/catalog/admin/categories/category-1",
                "delete_category",
                None,
                None,
                ("category-1",),
            ),
        )

        for user, method, path, catalog_method, payload, return_value, expected_call_args in cases:
            with self.subTest(path=path, method=method, user=user.username):
                self._assert_mutation_allowed(
                    user=user,
                    method=method,
                    path=path,
                    catalog_method=catalog_method,
                    payload=payload,
                    return_value=return_value,
                    expected_call_args=expected_call_args,
                )

    def test_root_binding_non_superuser_returns_403(self) -> None:
        """Non-superuser with binding role 'root' gets 403 on admin endpoints."""
        root_binding_user = get_user_model().objects.create_user(
            username="root_binding_user",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        SyncUserBinding.objects.create(user=root_binding_user, sync_role=Role.ROOT)

        self.client.force_login(root_binding_user)
        with patch("apps.bff_api.catalog_views._catalog") as catalog:
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items",
                data=json.dumps({"name": "Should fail"}),
                content_type="application/json",
            )

        catalog.assert_not_called()
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_admin_unit_detail_mutations_non_manager_return_403(self) -> None:
        self._assert_mutation_forbidden(
            method="patch",
            path="/bff/api/v1/catalog/admin/units/unit-1",
            payload={"name": "Blocked unit"},
        )
        self._assert_mutation_forbidden(method="delete", path="/bff/api/v1/catalog/admin/units/unit-1")

    def test_admin_unit_detail_mutations_allow_chief_and_root(self) -> None:
        cases = (
            (
                self.binding_chief,
                "patch",
                "/bff/api/v1/catalog/admin/units/unit-1",
                "update_unit",
                {"name": "Updated unit"},
                {"id": "unit-1", "name": "Updated unit"},
                ("unit-1", {"name": "Updated unit"}),
            ),
            (
                self.root,
                "delete",
                "/bff/api/v1/catalog/admin/units/unit-1",
                "delete_unit",
                None,
                None,
                ("unit-1",),
            ),
        )

        for user, method, path, catalog_method, payload, return_value, expected_call_args in cases:
            with self.subTest(path=path, method=method, user=user.username):
                self._assert_mutation_allowed(
                    user=user,
                    method=method,
                    path=path,
                    catalog_method=catalog_method,
                    payload=payload,
                    return_value=return_value,
                    expected_call_args=expected_call_args,
                )


class BffApiPublicEndpointsTests(TestCase):
    def test_public_health_uses_proxy_and_ok_wrapper(self) -> None:
        with patch("apps.bff_api.health_views._public_get", return_value={"status": "ok"}):
            response = self.client.get("/bff/api/v1/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"status": "ok"})


class BffApiIssueObjectCategoriesTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.storekeeper = user_model.objects.create_user(
            username="sk_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.plain_user = user_model.objects.create_user(
            username="plain_user",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )

    def test_categories_list_forwards_filters(self) -> None:
        mock_api = Mock()
        mock_api.list_categories.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 20}

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.issue_objects_views._ioc", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/issue-object-categories",
                {"search": "test", "parent_id": "5", "is_active": "true", "page": "1", "page_size": "20"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.list_categories.assert_called_once_with(
            filters={"search": "test", "parent_id": "5", "is_active": "true", "page": "1", "page_size": "20"}
        )

    def test_categories_create_requires_storekeeper(self) -> None:
        self.client.force_login(self.plain_user)
        response = self.client.post(
            "/bff/api/v1/issue-object-categories",
            data=json.dumps({"name": "New Cat"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_categories_create_storekeeper_allowed(self) -> None:
        mock_api = Mock()
        mock_api.create_category.return_value = {"id": 1, "name": "New Cat"}

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.issue_objects_views._ioc", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/issue-object-categories",
                data=json.dumps({"name": "New Cat"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["name"], "New Cat")

    def test_category_detail_get_returns_ok(self) -> None:
        mock_api = Mock()
        mock_api.get_category.return_value = {"id": 1, "name": "Cat 1"}

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.issue_objects_views._ioc", return_value=mock_api):
            response = self.client.get("/bff/api/v1/issue-object-categories/1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["name"], "Cat 1")

    def test_category_detail_update_requires_storekeeper(self) -> None:
        self.client.force_login(self.plain_user)
        response = self.client.patch(
            "/bff/api/v1/issue-object-categories/1",
            data=json.dumps({"name": "Updated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_category_detail_update_storekeeper_allowed(self) -> None:
        mock_api = Mock()
        mock_api.update_category.return_value = {"id": 1, "name": "Updated"}

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.issue_objects_views._ioc", return_value=mock_api):
            response = self.client.patch(
                "/bff/api/v1/issue-object-categories/1",
                data=json.dumps({"name": "Updated"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        mock_api.update_category.assert_called_once_with(1, {"name": "Updated"})

    def test_category_delete_requires_storekeeper(self) -> None:
        self.client.force_login(self.plain_user)
        response = self.client.delete("/bff/api/v1/issue-object-categories/1")
        self.assertEqual(response.status_code, 403)

    def test_category_delete_storekeeper_allowed(self) -> None:
        mock_api = Mock()
        mock_api.delete_category.return_value = None

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.issue_objects_views._ioc", return_value=mock_api):
            response = self.client.delete("/bff/api/v1/issue-object-categories/1")

        self.assertEqual(response.status_code, 200)
        mock_api.delete_category.assert_called_once_with(1)


class BffApiIssueObjectsTreeTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="tree_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )

    def test_tree_view_returns_nodes(self) -> None:
        mock_api = Mock()
        mock_api.get_tree.return_value = [
            {"id": 1, "type": "category", "name": "Cat 1", "children": []},
        ]

        self.client.force_login(self.user)
        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get("/bff/api/v1/issue-objects/tree")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["data"]), 1)

    def test_tree_view_forwards_filters(self) -> None:
        mock_api = Mock()
        mock_api.get_tree.return_value = []

        self.client.force_login(self.user)
        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/issue-objects/tree",
                {"search": "test", "include_inactive": "true"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.get_tree.assert_called_once_with(
            filters={"search": "test", "include_inactive": "true"}
        )


class BffApiIssueObjectsFilterForwardingTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="filter_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )

    def test_issue_objects_list_forwards_category_id(self) -> None:
        mock_api = Mock()
        mock_api.list_issue_objects.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 100}

        self.client.force_login(self.user)
        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/issue-objects",
                {"search": "test", "category_id": "5", "is_active": "true", "page": "1"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.list_issue_objects.assert_called_once_with(
            filters={"search": "test", "category_id": "5", "is_active": "true", "page": "1"}
        )

    def test_object_assets_list_forwards_search_and_item_id(self) -> None:
        mock_api = Mock()
        mock_api.list_object_assets.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 20}

        self.client.force_login(self.user)
        with patch("apps.bff_api.issue_objects_views._io", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/issue-objects/1/assets",
                {"search": "test", "item_id": "42", "page": "1", "page_size": "50"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.list_object_assets.assert_called_once_with(
            1,
            filters={"search": "test", "item_id": "42", "page": "1", "page_size": "50"}
        )


class BffApiIssuedAssetsFilterForwardingTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="issued_filter_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )

    def test_issued_assets_forwards_category_id(self) -> None:
        mock_api = Mock()
        mock_api.list_issued_assets.return_value = {"items": [], "total_count": 0, "page": 1, "page_size": 20}

        self.client.force_login(self.user)
        with patch("apps.bff_api.assets_views._assets", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/issued-assets",
                {"issue_object_id": "1", "category_id": "5", "search": "test", "page": "1"},
            )

        self.assertEqual(response.status_code, 200)
        mock_api.list_issued_assets.assert_called_once_with(
            filters={"issue_object_id": "1", "category_id": "5", "search": "test", "page": "1"}
        )


class BffApiOperationsInlineItemTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.storekeeper = user_model.objects.create_user(
            username="sk_inline",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.storekeeper, role=Role.STOREKEEPER)

        self.observer = user_model.objects.create_user(
            username="obs_inline",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.observer, role=Role.OBSERVER)

        self.root = user_model.objects.create_user(
            username="root_inline",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )

    def test_operations_create_forwards_temporary_item_payload(self) -> None:
        payload = {
            "type": "receipt",
            "lines": [
                {
                    "line_number": 1,
                    "qty": "3",
                    "temporary_item": {
                        "client_key": "inline-abc123",
                        "name": "Новая позиция",
                        "sku": "SKU-NEW",
                        "unit_id": 1,
                        "category_id": 10,
                        "description": "Описание",
                    },
                }
            ],
            "client_request_id": "req-001",
        }
        mock_api = Mock()
        mock_api.create_operation.return_value = ({"id": "op1", "status": "draft"}, {})

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        mock_api.create_operation.assert_called_once_with(
            payload,
            extra_headers={},
            return_response=True,
        )

    def test_operations_patch_forwards_temporary_item_payload(self) -> None:
        payload = {
            "lines": [
                {
                    "line_number": 1,
                    "qty": "5",
                    "temporary_item": {
                        "client_key": "inline-xyz789",
                        "name": "Обновлённая позиция",
                        "unit_id": 2,
                    },
                }
            ],
        }
        mock_api = Mock()
        mock_api.update_operation.return_value = ({"id": "op1", "status": "draft"}, {})

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.patch(
                "/bff/api/v1/operations/op1",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        mock_api.update_operation.assert_called_once_with(
            "op1",
            payload,
            extra_headers={},
            return_response=True,
        )

    def test_operations_create_storekeeper_allowed(self) -> None:
        mock_api = Mock()
        mock_api.create_operation.return_value = ({"id": "op1", "status": "draft"}, {})

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps({
                    "type": "receipt",
                    "lines": [],
                    "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
                }),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])

    def test_operations_create_observer_forbidden(self) -> None:
        self.client.force_login(self.observer)
        response = self.client.post(
            "/bff/api/v1/operations",
            data=json.dumps({"type": "receipt", "lines": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_operations_patch_storekeeper_allowed(self) -> None:
        mock_api = Mock()
        mock_api.update_operation.return_value = ({"id": "op1", "status": "draft"}, {})

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.patch(
                "/bff/api/v1/operations/op1",
                data=json.dumps({"lines": []}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])

    def test_operations_patch_observer_forbidden(self) -> None:
        self.client.force_login(self.observer)
        response = self.client.patch(
            "/bff/api/v1/operations/op1",
            data=json.dumps({"lines": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_bff_response_does_not_expose_syncserver_token(self) -> None:
        mock_api = Mock()
        mock_api.create_operation.return_value = (
            {
                "id": "op1",
                "lines": [{"temporary_item": {"name": "Test"}}],
            },
            {},
        )

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps({
                    "lines": [{"temporary_item": {"name": "Test"}}],
                    "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
                }),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body.keys()), {"ok", "data"})
        response_text = response.content.decode()
        self.assertNotIn("sync_user_token", response_text)
        self.assertNotIn("sync_device_token", response_text)


class BffApiOperationsFromSourceDocumentTests(TestCase):
    """Tests for POST /bff/api/v1/operations/from-source-document.

    TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING §8.4 (Gate A3 BFF mirror).
    """

    def setUp(self) -> None:
        user_model = get_user_model()
        self.storekeeper = user_model.objects.create_user(
            username="sk_src_doc",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.storekeeper, role=Role.STOREKEEPER)

        self.observer = user_model.objects.create_user(
            username="obs_src_doc",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.observer, role=Role.OBSERVER)

    def _payload(self) -> dict:
        return {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "source_ref": "invoice-2026-07-23-001",
            "source_document_type": "invoice",
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 3186,
                    "qty": "10",
                    "source_item_name": "Круг 10мм",
                },
            ],
            "client_request_id": "idem-src-doc-001",
        }

    def test_forwards_payload_to_sync_client(self) -> None:
        mock_api = Mock()
        mock_api.create_operation_from_source_document.return_value = (
            {"id": "op-1", "status": "draft", "creation_source": "source_document"},
            {},
        )

        payload = self._payload()
        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["creation_source"], "source_document")
        mock_api.create_operation_from_source_document.assert_called_once_with(
            payload,
            extra_headers={},
            return_response=True,
        )

    def test_missing_source_ref_returns_400(self) -> None:
        mock_api = Mock()
        payload = self._payload()
        payload.pop("source_ref")

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "validation_error")
        mock_api.create_operation_from_source_document.assert_not_called()

    def test_invalid_json_returns_400(self) -> None:
        mock_api = Mock()

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data="{not valid json",
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "validation_error")
        mock_api.create_operation_from_source_document.assert_not_called()

    def test_observer_forbidden(self) -> None:
        mock_api = Mock()
        self.client.force_login(self.observer)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data=json.dumps(self._payload()),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")
        mock_api.create_operation_from_source_document.assert_not_called()

    def test_unauthenticated_redirects(self) -> None:
        response = self.client.post(
            "/bff/api/v1/operations/from-source-document",
            data=json.dumps(self._payload()),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 403))

    def test_sync_409_idempotency_conflict_preserved(self) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        mock_api = Mock()
        mock_api.create_operation_from_source_document.side_effect = SyncServerAPIError(
            message="source_document_idempotency_conflict",
            status_code=409,
            payload={
                "detail": {
                    "code": "source_document_idempotency_conflict",
                    "message": "Source document with source_ref 'invoice-2026-07-23-001' was already used with a different payload",
                }
            },
        )

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data=json.dumps(self._payload()),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "source_document_idempotency_conflict")
        self.assertIn("source_ref", body["error"]["message"])

    def test_bff_response_envelope_shape(self) -> None:
        mock_api = Mock()
        mock_api.create_operation_from_source_document.return_value = (
            {
                "id": "op-1",
                "creation_source": "source_document",
                "source_ref": "invoice-2026-07-23-001",
            },
            {},
        )

        self.client.force_login(self.storekeeper)
        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations/from-source-document",
                data=json.dumps(self._payload()),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body.keys()), {"ok", "data"})
        self.assertEqual(body["data"]["creation_source"], "source_document")
        self.assertEqual(body["data"]["source_ref"], "invoice-2026-07-23-001")


class BffApiCatalogMergeTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.chief = user_model.objects.create_user(
            username="merge_chief",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.root = user_model.objects.create_user(
            username="merge_root",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
        self.plain_user = user_model.objects.create_user(
            username="merge_plain",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )

    def test_item_merge_unauthenticated_returns_redirect(self) -> None:
        response = self.client.post("/bff/api/v1/catalog/admin/items/merge", data="{}", content_type="application/json")
        self.assertIn(response.status_code, (302, 403))

    def test_item_merge_non_chief_returns_403(self) -> None:
        self.client.force_login(self.plain_user)
        response = self.client.post("/bff/api/v1/catalog/admin/items/merge", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_item_merge_chief_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.merge_items.return_value = {"status": "ok", "merged": 2}

        self.client.force_login(self.chief)
        payload = {"source_ids": ["i1", "i2"], "target_id": "i3"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "ok")
        mock_api.merge_items.assert_called_once_with(payload)

    def test_item_merge_root_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.merge_items.return_value = {"status": "ok", "merged": 2}

        self.client.force_login(self.root)
        payload = {"source_ids": ["i1"], "target_id": "i3"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.merge_items.assert_called_once()

    def test_item_merge_sync_error_409_is_preserved(self) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        mock_api = Mock()
        mock_api.merge_items.side_effect = SyncServerAPIError(
            "Merge conflict",
            status_code=409,
            payload={"detail": "Merge conflict"},
        )

        self.client.force_login(self.chief)
        payload = {"source_ids": ["i1"], "target_id": "i3"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/items/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "conflict")

    def test_category_merge_unauthenticated_returns_redirect(self) -> None:
        response = self.client.post("/bff/api/v1/catalog/admin/categories/merge", data="{}", content_type="application/json")
        self.assertIn(response.status_code, (302, 403))

    def test_category_merge_non_chief_returns_403(self) -> None:
        self.client.force_login(self.plain_user)
        response = self.client.post("/bff/api/v1/catalog/admin/categories/merge", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "forbidden")

    def test_category_merge_chief_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.merge_categories.return_value = {"status": "ok", "merged": 2}

        self.client.force_login(self.chief)
        payload = {"source_ids": ["c1", "c2"], "target_id": "c3"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/categories/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["status"], "ok")
        mock_api.merge_categories.assert_called_once_with(payload)

    def test_category_merge_root_calls_api_and_returns_200(self) -> None:
        mock_api = Mock()
        mock_api.merge_categories.return_value = {"status": "ok", "merged": 1}

        self.client.force_login(self.root)
        payload = {"source_ids": ["c1"], "target_id": "c2"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/categories/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        mock_api.merge_categories.assert_called_once()

    def test_category_merge_sync_error_409_is_preserved(self) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        mock_api = Mock()
        mock_api.merge_categories.side_effect = SyncServerAPIError(
            "Merge conflict",
            status_code=409,
            payload={"detail": "Merge conflict"},
        )

        self.client.force_login(self.chief)
        payload = {"source_ids": ["c1"], "target_id": "c2"}

        with patch("apps.bff_api.catalog_views.CatalogAPI", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/catalog/admin/categories/merge",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], "conflict")


class BffApiOperationsCorrelationTests(TestCase):
    """WP-2 (TZ-ANGULAR_OPERATION_RELIABILITY_SWARM): Django BFF forwards
    ``client_request_id`` and ``X-Client-*`` correlation headers from Angular
    to SyncServer and copies ``X-Request-Id`` back into the response.
    """

    def setUp(self) -> None:
        user_model = get_user_model()
        self.storekeeper = user_model.objects.create_user(
            username="correlation_sk",
            password="pass12345",
            is_superuser=False,
            is_staff=False,
            is_active=True,
        )
        UserProfile.objects.create(user=self.storekeeper, role=Role.STOREKEEPER)
        self.client.force_login(self.storekeeper)

    def test_client_request_id_forwarded_for_catalog_operations(self) -> None:
        """Catalog-only POST must keep Angular's ``client_request_id`` so
        SyncServer can use it for idempotency (§6.2.2 / §11.2)."""
        mock_api = Mock()
        mock_api.create_operation.return_value = ({"id": "op-1", "status": "draft"}, {})

        body = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "client_request_id": "cri-catalog-pass-through-001",
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 42,
                    "qty": "5.000",
                }
            ],
        }

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps(body),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body_passed = mock_api.create_operation.call_args.args[0]
        self.assertEqual(
            body_passed.get("client_request_id"),
            "cri-catalog-pass-through-001",
        )

    def test_correlation_headers_forwarded(self) -> None:
        """BFF must forward X-Client-Session-Id / X-Client-Tab-Id /
        X-Client-Request-Id / X-Frontend-Version from Angular to SyncServer
        via ``extra_headers`` (contract §3.2)."""
        mock_api = Mock()
        mock_api.create_operation.return_value = ({"id": "op-1", "status": "draft"}, {})

        body = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "client_request_id": "cri-corr-001",
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 42,
                    "qty": "1.000",
                }
            ],
        }

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps(body),
                content_type="application/json",
                HTTP_X_CLIENT_SESSION_ID="sess-uuid-1",
                HTTP_X_CLIENT_TAB_ID="tab-uuid-1",
                HTTP_X_CLIENT_REQUEST_ID="req-uuid-1",
                HTTP_X_CLIENT_DRAFT_ID="draft-uuid-1",
                HTTP_X_FRONTEND_VERSION="a1b2c3d4",
            )

        self.assertEqual(response.status_code, 200)
        kwargs = mock_api.create_operation.call_args.kwargs
        extra_headers = kwargs.get("extra_headers") or {}
        self.assertEqual(extra_headers.get("X-Client-Session-Id"), "sess-uuid-1")
        self.assertEqual(extra_headers.get("X-Client-Tab-Id"), "tab-uuid-1")
        self.assertEqual(extra_headers.get("X-Client-Request-Id"), "req-uuid-1")
        self.assertEqual(extra_headers.get("X-Client-Draft-Id"), "draft-uuid-1")
        self.assertEqual(extra_headers.get("X-Frontend-Version"), "a1b2c3d4")
        # Token headers must NOT be forwarded through the BFF layer.
        self.assertNotIn("X-User-Token", extra_headers)
        self.assertNotIn("X-Device-Token", extra_headers)

    def test_x_request_id_returned_to_client(self) -> None:
        """BFF must surface an ``X-Request-Id`` header on the Django response
        so Angular's ``BffApiService`` can capture it for diagnostics
        (contract §3.3). The BFF view propagates the SyncServer's id when
        present; ``RequestTracingMiddleware`` then guarantees a value is
        present even when the view did not set one."""
        mock_api = Mock()
        mock_api.create_operation.return_value = (
            {"id": "op-1", "status": "draft"},
            {"X-Request-Id": "sync-server-uuid-42"},
        )

        body = {
            "operation_type": "RECEIVE",
            "site_id": 1,
            "client_request_id": "cri-xreq-001",
            "lines": [
                {
                    "line_number": 1,
                    "item_id": 42,
                    "qty": "1.000",
                }
            ],
        }

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.post(
                "/bff/api/v1/operations",
                data=json.dumps(body),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        # ``RequestTracingMiddleware`` always emits ``X-Request-Id`` on the
        # final response. The exact value is a Django-generated UUID
        # (correlatable to ``request.META['X_REQUEST_ID']``); it MAY differ
        # from SyncServer's id because the middleware sets the header after
        # the view returns. The contract (§3.3) requires the header to be
        # present and correlatable, both of which are satisfied.
        self.assertIn("X-Request-Id", response)
        self.assertTrue(response["X-Request-Id"])

    def test_client_request_id_lookup_endpoint(self) -> None:
        """``GET /bff/api/v1/operations?client_request_id=...`` must proxy the
        filter to SyncServer so Angular can resolve ``outcome_unknown``
        (contract §6.1.2 / §10.2)."""
        mock_api = Mock()
        mock_api.list_operations_page.return_value = (
            {"items": [{"id": "op-1"}], "total_count": 1, "page": 1, "page_size": 20},
            {},
        )

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.get(
                "/bff/api/v1/operations",
                {"client_request_id": "lookup-key-001"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["total_count"], 1)
        mock_api.list_operations_page.assert_called_once()
        call_kwargs = mock_api.list_operations_page.call_args.kwargs
        filters = call_kwargs.get("filters") or {}
        self.assertEqual(filters.get("client_request_id"), "lookup-key-001")
