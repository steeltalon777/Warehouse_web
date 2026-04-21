from __future__ import annotations

from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils import timezone

from apps.catalog.services import ServiceResult
from apps.catalog_cache.models import CatalogCacheItem
from apps.operations.services import OperationPageService
from apps.operations.views import _build_create_payload


class OperationCreatePayloadQuantityTests(SimpleTestCase):
    def test_create_payload_accepts_decimal_quantity(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "RECEIVE",
                "site_id": 1,
                "items": [{"item_id": 10, "quantity": "1.250"}],
            },
            operate_site_ids={1},
        )

        self.assertEqual(payload["lines"][0]["qty"], "1.25")

    def test_create_payload_accepts_negative_decimal_for_adjustment(self) -> None:
        payload = _build_create_payload(
            {
                "operation_type": "ADJUSTMENT",
                "site_id": 1,
                "items": [{"item_id": 10, "quantity": "-0.125"}],
            },
            operate_site_ids={1},
        )

        self.assertEqual(payload["lines"][0]["qty"], "-0.125")

    def test_create_payload_rejects_more_than_three_decimal_places(self) -> None:
        with self.assertRaisesMessage(ValidationError, "точностью до 3 знаков"):
            _build_create_payload(
                {
                    "operation_type": "RECEIVE",
                    "site_id": 1,
                    "items": [{"item_id": 10, "quantity": "1.2345"}],
                },
                operate_site_ids={1},
            )


class OperationPageServiceSearchTests(TestCase):
    def test_search_items_supplements_cache_with_remote_results(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="101",
            name="Cable FTP",
            sku="FTP-1",
            search_text="cable ftp ftp-1 networking",
            category_id="10",
            category_name="Networking",
            unit_symbol="m",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )

        service = OperationPageService(client=Mock())
        service.catalog.browse_items = Mock(
            return_value=ServiceResult(
                ok=True,
                data={
                    "items": [
                        {
                            "id": 202,
                            "name": "Cable UTP",
                            "sku": "UTP-5E",
                            "category_id": 10,
                            "category_name": "Networking",
                            "unit_symbol": "m",
                            "is_active": True,
                        }
                    ]
                },
            )
        )

        items = service.search_items("cable", limit=10)

        self.assertEqual([item["id"] for item in items], [101, 202])
        cached = CatalogCacheItem.objects.get(sync_id="202")
        self.assertEqual(cached.name, "Cable UTP")
        self.assertEqual(cached.sku, "UTP-5E")

    def test_search_items_keeps_local_results_when_remote_lookup_fails(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="101",
            name="Cable FTP",
            sku="FTP-1",
            search_text="cable ftp ftp-1 networking",
            category_id="10",
            category_name="Networking",
            unit_symbol="m",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )

        service = OperationPageService(client=Mock())
        service.catalog.browse_items = Mock(return_value=ServiceResult(ok=False, form_error="sync failed"))

        items = service.search_items("cable", limit=10)

        self.assertEqual([item["id"] for item in items], [101])
