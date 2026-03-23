from __future__ import annotations

from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from apps.catalog_cache.models import CatalogCacheItem
from apps.catalog_cache.services import CatalogCacheSyncService, CatalogLookupService


class CatalogLookupServiceTests(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="101",
            name="Шуруп 5x50",
            sku="SCR-550",
            search_text="шуруп 5x50 scr-550 крепеж",
            category_id="12",
            category_name="Крепеж",
            unit_symbol="шт",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )
        CatalogCacheItem.objects.create(
            sync_id="102",
            name="Саморез 4x20",
            sku="SCR-420",
            search_text="саморез 4x20 scr-420 крепеж",
            category_id="12",
            category_name="Крепеж",
            unit_symbol="шт",
            is_active=False,
            source_updated_at=now,
            synced_at=now,
        )

    def test_search_returns_only_active_items(self) -> None:
        items = CatalogLookupService().search_items("scr", limit=10)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], 101)

    def test_search_matches_by_category_name_and_name(self) -> None:
        items = CatalogLookupService().search_items("крепеж шуруп", limit=10)

        self.assertEqual([item["id"] for item in items], [101])

    def test_search_matches_wrong_keyboard_layout(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="103",
            name="Коленвал",
            sku="12345",
            search_text="коленвал 12345 автозапчасти",
            category_id="77",
            category_name="Автозапчасти",
            unit_symbol="шт",
            is_active=True,
            source_updated_at=now,
            synced_at=now,
        )

        items = CatalogLookupService().search_items("rj", limit=10)

        self.assertEqual([item["id"] for item in items], [103])


class CatalogCacheSyncServiceTests(TestCase):
    def test_sync_items_upserts_pages(self) -> None:
        api = Mock()
        api.browse_items.side_effect = [
            {
                "items": [
                    {
                        "id": 501,
                        "name": "Кабель UTP",
                        "sku": "UTP-5E",
                        "category_id": 33,
                        "category_name": "Кабель",
                        "unit_symbol": "м",
                        "is_active": True,
                        "updated_at": "2026-03-22T10:15:00Z",
                    }
                ],
                "total_count": 1,
                "page": 1,
                "page_size": 250,
            }
        ]

        service = CatalogCacheSyncService(client=Mock())
        service.catalog_api = api

        stats = service.sync_items(page_size=250)

        self.assertEqual(stats.pages, 1)
        self.assertEqual(stats.fetched, 1)
        self.assertEqual(stats.upserted, 1)

        cached = CatalogCacheItem.objects.get(sync_id="501")
        self.assertEqual(cached.name, "Кабель UTP")
        self.assertEqual(cached.sku, "UTP-5E")
        self.assertEqual(cached.category_name, "Кабель")
