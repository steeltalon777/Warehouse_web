from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.catalog.forms import CategoryForm, ItemForm
from apps.catalog.services import CatalogService, ServiceResult
from apps.catalog.tree import build_category_item_tree
from apps.catalog_cache.services import CatalogCacheSyncStats
from apps.common.templatetags.permission_tags import can_manage_catalog_filter
from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.issue_objects_api import IssueObjectsAPI


class NomenclatureHomeViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="chief_redirect",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    def test_home_redirects_to_tree_page(self, _can_manage_catalog: Mock) -> None:
        response = self.client.get(reverse("nomenclature:home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("nomenclature:tree"))


class NomenclatureTreeViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="chief_tree",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_tree_page_renders_tree_and_sync_button(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        build_catalog_service.return_value = SimpleNamespace(
            browse_all_items=Mock(return_value=ServiceResult(ok=True, data=[{"id": 101, "name": "Кабель", "category_id": 1}])),
            list_admin_categories=Mock(return_value=ServiceResult(ok=True, data=[{"id": 1, "name": "Электрика", "is_active": True}])),
        )

        response = self.client.get(reverse("nomenclature:tree"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дерево номенклатуры")
        self.assertContains(response, "Обновить кэш поиска операций")

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_tree_delete_forms_include_csrf_token(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        build_catalog_service.return_value = SimpleNamespace(
            browse_all_items=Mock(return_value=ServiceResult(ok=True, data=[{"id": 101, "name": "Кабель", "category_id": 1}])),
            list_admin_categories=Mock(return_value=ServiceResult(ok=True, data=[{"id": 1, "name": "Электрика", "is_active": True}])),
        )

        response = self.client.get(reverse("nomenclature:tree"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "action=\"/nomenclature/ssr/categories/1/delete/\"", html=False)
        self.assertContains(response, 'name="csrfmiddlewaretoken"', html=False)


class CategoryListViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="chief",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_category_list_filters_by_name_and_paginates(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        build_catalog_service.return_value = SimpleNamespace(
            browse_all_items=Mock(return_value=ServiceResult(ok=True, data=[])),
            list_items=Mock(return_value=ServiceResult(ok=True, data=[])),
            list_admin_categories=Mock(
                return_value=ServiceResult(
                    ok=True,
                    data=[
                        {"id": 1, "name": "Auto Parts", "is_active": True},
                        {"id": 2, "name": "Auto Relay", "is_active": True},
                        {"id": 3, "name": "Auto Sensor", "is_active": True},
                        {"id": 4, "name": "Bearings", "is_active": True},
                    ],
                )
            )
        )

        response = self.client.get(
            reverse("nomenclature:category_list"),
            {"search": "auto", "page_size": 2, "page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [category["name"] for category in response.context["flat_categories"]],
            ["Auto Sensor"],
        )
        self.assertEqual(response.context["pagination"]["total_count"], 3)
        self.assertEqual(response.context["pagination"]["total_pages"], 2)
        self.assertEqual(response.context["pagination"]["page"], 2)


class CatalogCacheSyncViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="root_like",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    @patch("apps.catalog.views.CatalogCacheSyncService.sync_items")
    def test_cache_sync_view_runs_sync_and_redirects_back(
        self,
        sync_items: Mock,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        build_catalog_service.return_value = SimpleNamespace(
            browse_all_items=Mock(return_value=ServiceResult(ok=True, data=[])),
            list_categories=Mock(return_value=ServiceResult(ok=True, data=[])),
            list_admin_categories=Mock(return_value=ServiceResult(ok=True, data=[])),
            list_items=Mock(return_value=ServiceResult(ok=True, data=[])),
        )
        sync_items.return_value = CatalogCacheSyncStats(pages=2, fetched=40, upserted=40, skipped=0, total_count=40)

        response = self.client.post(
            reverse("nomenclature:cache_sync"),
            {"next": reverse("nomenclature:category_list")},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[-1][0], reverse("nomenclature:category_list"))
        self.assertEqual(sync_items.call_count, 1)

        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("40" in message for message in messages))


class ItemListViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="chief_items",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_item_list_filters_by_name_or_sku(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        build_catalog_service.return_value = SimpleNamespace(
            list_admin_items=Mock(
                return_value=ServiceResult(
                    ok=True,
                    data=[
                        {"id": 1, "name": "Кабель ВВГ", "sku": "VVG-3X1", "category_id": 10},
                        {"id": 2, "name": "Автомат", "sku": "AUTO-25", "category_id": 11},
                    ],
                )
            ),
            list_admin_categories=Mock(
                return_value=ServiceResult(
                    ok=True,
                    data=[
                        {"id": 10, "name": "Кабели", "is_active": True},
                        {"id": 11, "name": "Автоматы", "is_active": True},
                    ],
                )
            ),
        )

        response = self.client.get(reverse("nomenclature:item_list"), {"search": "AUTO-25"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.context["items"]], ["2"])


class NomenclatureDeleteViewTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="chief_delete",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_category_delete_uses_delete_endpoint(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        service = SimpleNamespace(
            get_category=Mock(return_value=ServiceResult(ok=True, data={"id": 1, "name": "Tools"})),
            delete_category=Mock(return_value=ServiceResult(ok=True)),
        )
        build_catalog_service.return_value = service

        response = self.client.post(reverse("nomenclature:category_delete", kwargs={"pk": 1}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("nomenclature:category_list"))
        service.delete_category.assert_called_once_with("1")

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_category_delete_confirm_for_root_mentions_uncategorized(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        service = SimpleNamespace(
            get_category=Mock(return_value=ServiceResult(ok=True, data={"id": 1, "name": "Root", "parent_id": None})),
            delete_category=Mock(return_value=ServiceResult(ok=True)),
        )
        build_catalog_service.return_value = service

        response = self.client.get(reverse("nomenclature:category_delete", kwargs={"pk": 1}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "корневой категории будут перенесены в системную категорию")
        self.assertContains(response, "Без категории")

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_category_delete_confirm_for_nested_mentions_parent_transfer(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        service = SimpleNamespace(
            get_category=Mock(return_value=ServiceResult(ok=True, data={"id": 2, "name": "Child", "parent_id": 1})),
            delete_category=Mock(return_value=ServiceResult(ok=True)),
        )
        build_catalog_service.return_value = service

        response = self.client.get(reverse("nomenclature:category_delete", kwargs={"pk": 2}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "будут перенесены в родительскую категорию")

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_unit_delete_uses_delete_endpoint(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        service = SimpleNamespace(delete_unit=Mock(return_value=ServiceResult(ok=True)))
        build_catalog_service.return_value = service

        response = self.client.post(reverse("nomenclature:unit_delete", kwargs={"pk": 7}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("nomenclature:unit_list"))
        service.delete_unit.assert_called_once_with("7")

    @patch("apps.catalog.views.can_manage_catalog", return_value=True)
    @patch("apps.catalog.views.can_use_client", return_value=True)
    @patch("apps.catalog.views._build_catalog_service")
    def test_item_delete_uses_delete_endpoint(
        self,
        build_catalog_service: Mock,
        _can_use_client: Mock,
        _can_manage_catalog: Mock,
    ) -> None:
        service = SimpleNamespace(delete_item=Mock(return_value=ServiceResult(ok=True)))
        build_catalog_service.return_value = service

        response = self.client.post(reverse("nomenclature:item_delete", kwargs={"pk": 12}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("nomenclature:item_list"))
        service.delete_item.assert_called_once_with("12")


class SearchableSelectFormTests(SimpleTestCase):
    def test_forms_mark_large_reference_selects_as_searchable(self) -> None:
        category_form = CategoryForm(category_choices=[{"id": 1, "name": "Инструмент"}])
        item_form = ItemForm(
            categories=[{"id": 1, "name": "Инструмент"}],
            units=[{"id": 7, "name": "Штука", "symbol": "шт"}],
        )

        self.assertEqual(category_form.fields["parent_id"].widget.attrs["data-searchable-select"], "true")
        self.assertEqual(item_form.fields["category_id"].widget.attrs["data-searchable-select"], "true")
        self.assertEqual(item_form.fields["unit_id"].widget.attrs["data-searchable-select"], "true")


class CategoryItemTreeTests(SimpleTestCase):
    def test_tree_keeps_items_visible_when_category_is_hidden_from_navigation(self) -> None:
        tree_nodes = build_category_item_tree(
            categories=[{"id": "1", "name": "Кабель"}],
            items=[
                {"id": "101", "name": "Кабель ВВГ", "category_id": "1"},
                {"id": "202", "name": "Товар без дерева", "category_id": "999"},
            ],
            category_url_builder=lambda category: f"/categories/{category['id']}/",
            item_url_builder=lambda item: f"/items/{item['id']}/",
            selected_kind="item",
            selected_id="202",
        )

        self.assertEqual(tree_nodes[0]["node_type"], "category")
        self.assertTrue(any(node["node_type"] == "item" and node["id"] == "202" for node in tree_nodes))
        self.assertTrue(any(node["selected"] for node in tree_nodes if node["id"] == "202"))


class CatalogServiceBrowseTests(SimpleTestCase):
    def test_browse_all_items_collects_all_pages(self) -> None:
        service = CatalogService(client=Mock())
        service.catalog_api = Mock()
        service.catalog_api.browse_items.side_effect = [
            {"items": [{"id": 1, "name": "A"}], "page": 1, "page_size": 1, "total_count": 2},
            {"items": [{"id": 2, "name": "B"}], "page": 2, "page_size": 1, "total_count": 2},
        ]

        result = service.browse_all_items(page_size=1)

        self.assertTrue(result.ok)
        self.assertEqual([item["id"] for item in result.data], [1, 2])

    def test_get_item_uses_admin_detail_endpoint(self) -> None:
        service = CatalogService(client=Mock())
        service.catalog_api = Mock()
        service.catalog_api.get_item.return_value = {"id": 2, "name": "B"}

        result = service.get_item("2")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["id"], 2)
        service.catalog_api.get_item.assert_called_once_with("2")

    def test_admin_list_collects_all_pages(self) -> None:
        service = CatalogService(client=Mock())
        service.catalog_api = Mock()
        service.catalog_api.list_admin_units.side_effect = [
            {"items": [{"id": 1}], "page": 1, "page_size": 1, "total_count": 2},
            {"items": [{"id": 2}], "page": 2, "page_size": 1, "total_count": 2},
        ]

        result = service.list_admin_units(page_size=1)

        self.assertTrue(result.ok)
        self.assertEqual([unit["id"] for unit in result.data], [1, 2])


class SyncReferenceAPIEndpointTests(SimpleTestCase):
    def test_catalog_admin_crud_methods_use_api_map_paths(self) -> None:
        client = Mock()
        client.get.return_value = {"items": []}
        api = CatalogAPI(client)

        api.list_admin_categories(filters={"page": 1})
        client.get.assert_called_with(
            "/catalog/admin/categories",
            params={"page": 1},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.get_category("5")
        client.get.assert_called_with(
            "/catalog/admin/categories/5",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.delete_category("5")
        client.delete.assert_called_with(
            "/catalog/admin/categories/5",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.get_item("9")
        client.get.assert_called_with(
            "/catalog/admin/items/9",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.delete_item("9")
        client.delete.assert_called_with(
            "/catalog/admin/items/9",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.get_unit("2")
        client.get.assert_called_with(
            "/catalog/admin/units/2",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.delete_unit("2")
        client.delete.assert_called_with(
            "/catalog/admin/units/2",
            acting_user_id=None,
            acting_site_id=None,
        )

    def test_issue_objects_crud_methods_use_api_map_paths(self) -> None:
        client = Mock()
        client.get.return_value = {"items": []}
        api = IssueObjectsAPI(client)

        api.list_issue_objects(filters={"search": "Test"})
        client.get.assert_called_with(
            "/issue-objects",
            params={"search": "Test"},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.create_issue_object({"display_name": "Test"})
        client.post.assert_called_with(
            "/issue-objects",
            json={"display_name": "Test"},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.merge_issue_objects({"source_id": 1, "target_id": 2})
        client.post.assert_called_with(
            "/issue-objects/merge",
            json={"source_id": 1, "target_id": 2},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.get_issue_object("3")
        client.get.assert_called_with(
            "/issue-objects/3",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.update_issue_object("3", {"is_active": False})
        client.patch.assert_called_with(
            "/issue-objects/3",
            json={"is_active": False},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.delete_issue_object("3")
        client.delete.assert_called_with(
            "/issue-objects/3",
            acting_user_id=None,
            acting_site_id=None,
        )


class PermissionTemplateFilterTests(SimpleTestCase):
    def test_nomenclature_menu_visible_only_for_catalog_managers(self) -> None:
        chief_user = SimpleNamespace(
            is_superuser=False,
            is_authenticated=True,
            sync_binding=SimpleNamespace(sync_role="chief_storekeeper"),
        )
        storekeeper_user = SimpleNamespace(
            is_superuser=False,
            is_authenticated=True,
            sync_binding=SimpleNamespace(sync_role="storekeeper"),
        )
        observer_user = SimpleNamespace(
            is_superuser=False,
            is_authenticated=True,
            sync_binding=SimpleNamespace(sync_role="observer"),
        )

        self.assertTrue(can_manage_catalog_filter(chief_user))
        self.assertFalse(can_manage_catalog_filter(storekeeper_user))
        self.assertFalse(can_manage_catalog_filter(observer_user))


# ---------------------------------------------------------------------------
# Nomenclature SPA / BFF authentication and error-handling tests (TZ-2)
# ---------------------------------------------------------------------------

class NomenclatureSPAAuthTests(TestCase):
    """Tests for NomenclatureSPAView login requirement."""

    def test_anonymous_redirected_to_login(self) -> None:
        """Anonymous GET /nomenclature/ redirects to the login page."""
        response = self.client.get(reverse("nomenclature:spa_home"))

        self.assertEqual(response.status_code, 302)
        # Django redirects to LOGIN_URL with ?next= appended
        self.assertIn("/login/", response["Location"])

    def test_authenticated_user_gets_spa_shell(self) -> None:
        """Authenticated GET /nomenclature/ returns 200 (SPA index.html served)."""
        user = get_user_model().objects.create_user(
            username="spa_user",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("nomenclature:spa_home"))

        # 200 if the Angular build dist exists, 404 if it does not — both
        # are acceptable; the important thing is no redirect to login.
        self.assertIn(response.status_code, (200, 404))


class BootstrapViewAuthTests(TestCase):
    """Tests for BootstrapView login requirement and SyncServer error mapping."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="bootstrap_user",
            password="secret123",
            is_active=True,
        )

    def test_anonymous_redirected_to_login(self) -> None:
        """Anonymous GET /nomenclature/api/bootstrap/ redirects to login."""
        response = self.client.get(reverse("nomenclature:api_bootstrap"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    @patch("apps.catalog.api_views._build_service")
    def test_authenticated_gets_bootstrap_json(self, build_service: Mock) -> None:
        """Authenticated GET /nomenclature/api/bootstrap/ returns 200 with expected keys."""
        build_service.return_value = Mock(
            get_categories_tree=Mock(return_value={"children": []}),
            browse_all_items=Mock(return_value={
                "items": [],
                "total_count": 0,
                "loaded_count": 0,
                "complete": True,
            }),
            list_units=Mock(return_value=[]),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("nomenclature:api_bootstrap"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("categories_tree", data["data"])
        self.assertIn("items", data["data"])
        self.assertIn("items_total", data["data"])
        self.assertIn("items_loaded", data["data"])
        self.assertIn("items_complete", data["data"])
        self.assertTrue(data["data"]["items_complete"])
        self.assertIn("units", data["data"])
        self.assertIn("user", data["data"])
        self.assertIn("permissions", data["data"])
        self.assertEqual(data["data"]["user"]["username"], "bootstrap_user")

    @patch("apps.catalog.api_views._build_service")
    def test_syncserver_error_maps_to_502(self, build_service: Mock) -> None:
        """When SyncServerClient raises SyncServerAPIError, bootstrap returns 502 JSON error."""
        from apps.sync_client.exceptions import SyncServerAPIError

        build_service.return_value = Mock(
            get_categories_tree=Mock(
                side_effect=SyncServerAPIError("SyncServer недоступен", status_code=502),
            ),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("nomenclature:api_bootstrap"))

        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "sync_error")
        self.assertIn("SyncServer недоступен", data["error"]["message"])

    @patch("apps.catalog.api_views._build_service")
    def test_syncserver_error_without_status_defaults_to_502(self, build_service: Mock) -> None:
        """SyncServerAPIError with no status_code still maps to 502."""
        from apps.sync_client.exceptions import SyncServerAPIError

        build_service.return_value = Mock(
            get_categories_tree=Mock(
                side_effect=SyncServerAPIError("Неизвестная ошибка"),
            ),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("nomenclature:api_bootstrap"))

        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# Catalog API mutation tests — POST / PATCH for categories, items, units
# ---------------------------------------------------------------------------

class CatalogApiCategoryMutationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="api_chief",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)
        self._perm_patcher = patch("apps.catalog.api_views._require_catalog_manager", return_value=None)
        self._perm_patcher.start()

    def tearDown(self) -> None:
        self._perm_patcher.stop()
        super().tearDown()

    @patch("apps.catalog.api_views._build_service")
    def test_post_categories_creates_category(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            create_category=Mock(return_value={"id": "7", "name": "New Category", "is_active": True}),
        )

        response = self.client.post(
            reverse("nomenclature:api_category_tree"),
            data=b'{"name":"New Category","parent_id":1}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["name"], "New Category")
        build_service.return_value.create_category.assert_called_once_with({"name": "New Category", "parent_id": 1})

    @patch("apps.catalog.api_views._build_service")
    def test_patch_category_updates_category(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            update_category=Mock(return_value={"id": "7", "name": "Updated Category", "is_active": True}),
        )

        response = self.client.patch(
            reverse("nomenclature:api_category_detail", kwargs={"pk": "7"}),
            data=b'{"name":"Updated Category"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["name"], "Updated Category")
        build_service.return_value.update_category.assert_called_once_with("7", {"name": "Updated Category"})

    @patch("apps.catalog.api_views._build_service")
    def test_post_category_sync_error_returns_envelope(self, build_service: Mock) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        build_service.return_value = Mock(
            create_category=Mock(side_effect=SyncServerAPIError("Name already exists", status_code=409)),
        )

        response = self.client.post(
            reverse("nomenclature:api_category_tree"),
            data=b'{"name":"Duplicate"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "sync_error")


class CatalogApiItemMutationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="api_items_chief",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)
        self._perm_patcher = patch("apps.catalog.api_views._require_catalog_manager", return_value=None)
        self._perm_patcher.start()

    def tearDown(self) -> None:
        self._perm_patcher.stop()
        super().tearDown()

    @patch("apps.catalog.api_views._build_service")
    def test_post_items_creates_item(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            create_item=Mock(return_value={"id": "42", "name": "New Item", "sku": "SKU-42", "category_id": "1"}),
        )

        response = self.client.post(
            reverse("nomenclature:api_items_list"),
            data=b'{"name":"New Item","sku":"SKU-42","category_id":"1"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["sku"], "SKU-42")
        build_service.return_value.create_item.assert_called_once_with({"name": "New Item", "sku": "SKU-42", "category_id": "1"})

    @patch("apps.catalog.api_views._build_service")
    def test_patch_item_updates_item(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            update_item=Mock(return_value={"id": "42", "name": "Updated Item", "sku": "SKU-42"}),
        )

        response = self.client.patch(
            reverse("nomenclature:api_item_detail", kwargs={"pk": "42"}),
            data=b'{"name":"Updated Item"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["name"], "Updated Item")
        build_service.return_value.update_item.assert_called_once_with("42", {"name": "Updated Item"})

    @patch("apps.catalog.api_views._build_service")
    def test_post_item_sync_error_returns_envelope(self, build_service: Mock) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        build_service.return_value = Mock(
            create_item=Mock(side_effect=SyncServerAPIError("Invalid SKU", status_code=400)),
        )

        response = self.client.post(
            reverse("nomenclature:api_items_list"),
            data=b'{"name":"Bad","sku":""}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "sync_error")


class CatalogApiUnitMutationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="api_units_chief",
            password="secret123",
            is_active=True,
        )
        self.client.force_login(self.user)
        self._perm_patcher = patch("apps.catalog.api_views._require_catalog_manager", return_value=None)
        self._perm_patcher.start()

    def tearDown(self) -> None:
        self._perm_patcher.stop()
        super().tearDown()

    @patch("apps.catalog.api_views._build_service")
    def test_post_units_creates_unit(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            create_unit=Mock(return_value={"id": "5", "name": "Meter", "symbol": "m"}),
        )

        response = self.client.post(
            reverse("nomenclature:api_units_list"),
            data=b'{"name":"Meter","symbol":"m"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["symbol"], "m")
        build_service.return_value.create_unit.assert_called_once_with({"name": "Meter", "symbol": "m"})

    @patch("apps.catalog.api_views._build_service")
    def test_patch_unit_updates_unit(self, build_service: Mock) -> None:
        build_service.return_value = Mock(
            update_unit=Mock(return_value={"id": "5", "name": "Kilogram", "symbol": "kg"}),
        )

        response = self.client.patch(
            reverse("nomenclature:api_unit_detail", kwargs={"pk": "5"}),
            data=b'{"name":"Kilogram","symbol":"kg"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["symbol"], "kg")
        build_service.return_value.update_unit.assert_called_once_with("5", {"name": "Kilogram", "symbol": "kg"})

    @patch("apps.catalog.api_views._build_service")
    def test_post_unit_sync_error_returns_envelope(self, build_service: Mock) -> None:
        from apps.sync_client.exceptions import SyncServerAPIError

        build_service.return_value = Mock(
            create_unit=Mock(side_effect=SyncServerAPIError("Duplicate symbol", status_code=409)),
        )

        response = self.client.post(
            reverse("nomenclature:api_units_list"),
            data=b'{"name":"Duplicate","symbol":"m"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "sync_error")


class CatalogAPIBrowseAllItemsTests(SimpleTestCase):
    """Tests for CatalogAPI.browse_all_items() pagination loop."""

    def test_collects_single_page_when_all_fit(self) -> None:
        """When total_count <= page_size, browse_all_items collects in one request."""
        api = CatalogAPI(client=Mock())
        api.browse_items = Mock(return_value={
            "items": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
            "total_count": 2,
            "page": 1,
            "page_size": 1000,
        })

        result = api.browse_all_items()

        api.browse_items.assert_called_once()
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["loaded_count"], 2)
        self.assertTrue(result["complete"])

    def test_collects_multiple_pages(self) -> None:
        """When total_count > page_size, browse_all_items loops through pages."""
        api = CatalogAPI(client=Mock())
        api.browse_items = Mock(side_effect=[
            {
                "items": [{"id": i, "name": f"Item {i}"} for i in range(1000)],
                "total_count": 1600,
                "page": 1,
                "page_size": 1000,
            },
            {
                "items": [{"id": i, "name": f"Item {i}"} for i in range(1000, 1600)],
                "total_count": 1600,
                "page": 2,
                "page_size": 1000,
            },
        ])

        result = api.browse_all_items()

        self.assertEqual(api.browse_items.call_count, 2)
        self.assertEqual(len(result["items"]), 1600)
        self.assertEqual(result["total_count"], 1600)
        self.assertEqual(result["loaded_count"], 1600)
        self.assertTrue(result["complete"])

    def test_stops_on_empty_page(self) -> None:
        """When a page returns empty items, loop stops even without total_count."""
        api = CatalogAPI(client=Mock())
        api.browse_items = Mock(side_effect=[
            {"items": [{"id": 1}], "page": 1, "page_size": 1000},
            {"items": [], "page": 2, "page_size": 1000},
        ])

        result = api.browse_all_items()

        self.assertEqual(api.browse_items.call_count, 2)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["loaded_count"], 1)
        self.assertFalse(result["complete"])  # no total_count -> incomplete

    def test_returns_complete_false_when_total_count_not_reached(self) -> None:
        """When second page returns empty items but total_count > loaded, complete=False."""
        api = CatalogAPI(client=Mock())
        api.browse_items = Mock(side_effect=[
            {"items": [{"id": 1}], "total_count": 10, "page": 1, "page_size": 1000},
            {"items": [], "total_count": 10, "page": 2, "page_size": 1000},
        ])

        result = api.browse_all_items()

        self.assertEqual(result["loaded_count"], 1)
        self.assertEqual(result["total_count"], 10)
        self.assertFalse(result["complete"])

    def test_hashtags_preserved_beyond_first_page(self) -> None:
        """Items on page 2 retain their hashtags."""
        page1_items = [{"id": i, "name": f"Item {i}", "hashtags": ["page1"]} for i in range(1000)]
        page2_items = [
            {"id": 1000, "name": "TaggedBeyond1000", "hashtags": ["rare", "vip"]},
        ]

        api = CatalogAPI(client=Mock())
        api.browse_items = Mock(side_effect=[
            {"items": page1_items, "total_count": 1001, "page": 1, "page_size": 1000},
            {"items": page2_items, "total_count": 1001, "page": 2, "page_size": 1000},
        ])

        result = api.browse_all_items()

        self.assertEqual(api.browse_items.call_count, 2)
        self.assertEqual(len(result["items"]), 1001)
        self.assertTrue(result["complete"])

        tagged = next(item for item in result["items"] if item["name"] == "TaggedBeyond1000")
        self.assertEqual(tagged["hashtags"], ["rare", "vip"])


# ---------------------------------------------------------------------------
# Permission hardening tests (Stage 1C)
# ---------------------------------------------------------------------------


class NomenclatureApiPermissionTest(TestCase):
    """Tests that mutation endpoints return 403 for non-manager users."""

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="plain_user",
            password="testpass123",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )
        self.client.force_login(self.user)

    def test_bootstrap_get_ok(self):
        response = self.client.get(reverse("nomenclature:api_bootstrap"))
        self.assertNotEqual(response.status_code, 403)

    def test_create_category_forbidden(self):
        response = self.client.post(
            reverse("nomenclature:api_category_tree"),
            data=json.dumps({"name": "Test"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_update_category_forbidden(self):
        response = self.client.patch(
            reverse("nomenclature:api_category_detail", kwargs={"pk": 1}),
            data=json.dumps({"name": "Updated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_category_forbidden(self):
        response = self.client.delete(
            reverse("nomenclature:api_category_detail", kwargs={"pk": 1}),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_item_forbidden(self):
        response = self.client.post(
            reverse("nomenclature:api_items_list"),
            data=json.dumps({"name": "Test Item"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_update_item_forbidden(self):
        response = self.client.patch(
            reverse("nomenclature:api_item_detail", kwargs={"pk": 1}),
            data=json.dumps({"name": "Updated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_item_forbidden(self):
        response = self.client.delete(
            reverse("nomenclature:api_item_detail", kwargs={"pk": 1}),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_unit_forbidden(self):
        response = self.client.post(
            reverse("nomenclature:api_units_list"),
            data=json.dumps({"name": "Test Unit"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_update_unit_forbidden(self):
        response = self.client.patch(
            reverse("nomenclature:api_unit_detail", kwargs={"pk": 1}),
            data=json.dumps({"name": "Updated"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_unit_forbidden(self):
        response = self.client.delete(
            reverse("nomenclature:api_unit_detail", kwargs={"pk": 1}),
        )
        self.assertEqual(response.status_code, 403)

    def test_read_endpoints_accessible(self):
        endpoints = [
            reverse("nomenclature:api_bootstrap"),
            reverse("nomenclature:api_category_tree"),
            reverse("nomenclature:api_items_list"),
            reverse("nomenclature:api_units_list"),
        ]
        for url in endpoints:
            response = self.client.get(url)
            self.assertNotEqual(response.status_code, 403, f"GET {url} returned 403")
