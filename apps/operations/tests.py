from __future__ import annotations

from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from apps.catalog.services import ServiceResult
from apps.catalog_cache.models import CatalogCacheItem
from apps.operations.services import OperationPageService


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
