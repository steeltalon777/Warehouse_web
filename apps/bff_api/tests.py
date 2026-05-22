from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase


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
            "recipients",
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
        mock_api.submit_operation.return_value = {"id": "op1", "status": "submitted"}

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

    def test_operations_delete_supported(self) -> None:
        mock_api = Mock()
        mock_api.delete_operation.return_value = None

        with patch("apps.bff_api.operations_views._ops", return_value=mock_api):
            response = self.client.delete("/bff/api/v1/operations/op1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"deleted": True})

    def test_recipients_delete_supported(self) -> None:
        mock_api = Mock()
        mock_api.delete_recipient.return_value = None

        with patch("apps.bff_api.recipients_views._rec", return_value=mock_api):
            response = self.client.delete("/bff/api/v1/recipients/r1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"deleted": True})

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


class BffApiCatalogBatchTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.chief = user_model.objects.create_user(
            username="chief_user",
            password="pass12345",
            is_superuser=True,
            is_staff=True,
            is_active=True,
        )
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
        response = self.client.post("/bff/api/v1/catalog/admin/batch", data="{}", content_type="application/json")
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


class BffApiPublicEndpointsTests(TestCase):
    def test_public_health_uses_proxy_and_ok_wrapper(self) -> None:
        with patch("apps.bff_api.health_views._public_get", return_value={"status": "ok"}):
            response = self.client.get("/bff/api/v1/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"status": "ok"})
