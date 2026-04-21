from __future__ import annotations

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
from apps.sync_client.recipients_api import RecipientsAPI


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

    def test_recipients_crud_methods_use_api_map_paths(self) -> None:
        client = Mock()
        client.get.return_value = {"items": []}
        api = RecipientsAPI(client)

        api.list_recipients(filters={"search": "Ivan"})
        client.get.assert_called_with(
            "/recipients",
            params={"search": "Ivan"},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.create_recipient({"display_name": "Ivan"})
        client.post.assert_called_with(
            "/recipients",
            json={"display_name": "Ivan"},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.merge_recipients({"source_id": 1, "target_id": 2})
        client.post.assert_called_with(
            "/recipients/merge",
            json={"source_id": 1, "target_id": 2},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.get_recipient("3")
        client.get.assert_called_with(
            "/recipients/3",
            acting_user_id=None,
            acting_site_id=None,
        )

        api.update_recipient("3", {"is_active": False})
        client.patch.assert_called_with(
            "/recipients/3",
            json={"is_active": False},
            acting_user_id=None,
            acting_site_id=None,
        )

        api.delete_recipient("3")
        client.delete.assert_called_with(
            "/recipients/3",
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
