from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class LegacyNomenclatureApiPermissionTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="catalog_plain_user",
            password="testpass123",
            is_active=True,
        )
        self.client.force_login(self.user)

    def _request(self, method: str, url: str, *, payload: dict | None = None):
        kwargs = {}
        if payload is not None:
            kwargs["data"] = json.dumps(payload)
            kwargs["content_type"] = "application/json"
        return getattr(self.client, method)(url, **kwargs)

    def test_non_manager_mutations_return_403_without_calling_catalog_api(self) -> None:
        scenarios = [
            ("post", reverse("nomenclature:api_category_tree"), {"name": "Test Category"}, "create_category"),
            (
                "patch",
                reverse("nomenclature:api_category_detail", kwargs={"pk": "cat-1"}),
                {"name": "Updated Category"},
                "update_category",
            ),
            ("delete", reverse("nomenclature:api_category_detail", kwargs={"pk": "cat-1"}), None, "delete_category"),
            ("post", reverse("nomenclature:api_items_list"), {"name": "Test Item"}, "create_item"),
            (
                "patch",
                reverse("nomenclature:api_item_detail", kwargs={"pk": "item-1"}),
                {"name": "Updated Item"},
                "update_item",
            ),
            ("delete", reverse("nomenclature:api_item_detail", kwargs={"pk": "item-1"}), None, "delete_item"),
            ("post", reverse("nomenclature:api_units_list"), {"name": "Test Unit"}, "create_unit"),
            (
                "patch",
                reverse("nomenclature:api_unit_detail", kwargs={"pk": "unit-1"}),
                {"name": "Updated Unit"},
                "update_unit",
            ),
            ("delete", reverse("nomenclature:api_unit_detail", kwargs={"pk": "unit-1"}), None, "delete_unit"),
        ]

        for method, url, payload, api_method in scenarios:
            service = Mock()
            with self.subTest(method=method, url=url):
                with patch("apps.catalog.api_views._build_service", return_value=service) as build_service:
                    response = self._request(method, url, payload=payload)

                self.assertEqual(response.status_code, 403)
                body = response.json()
                self.assertFalse(body["ok"])
                self.assertEqual(body["error"]["code"], "forbidden")
                build_service.assert_not_called()
                getattr(service, api_method).assert_not_called()

    def test_read_endpoints_remain_available_for_authenticated_user(self) -> None:
        service = Mock(
            get_categories_tree=Mock(return_value={"children": []}),
            browse_all_items=Mock(
                return_value={
                    "items": [],
                    "total_count": 0,
                    "loaded_count": 0,
                    "complete": True,
                }
            ),
            list_items=Mock(return_value=[]),
            list_units=Mock(return_value=[]),
        )
        endpoints = [
            reverse("nomenclature:api_bootstrap"),
            reverse("nomenclature:api_category_tree"),
            reverse("nomenclature:api_items_list"),
            reverse("nomenclature:api_units_list"),
        ]

        with patch("apps.catalog.api_views._build_service", return_value=service) as build_service:
            for url in endpoints:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()["ok"])

        self.assertEqual(build_service.call_count, len(endpoints))
