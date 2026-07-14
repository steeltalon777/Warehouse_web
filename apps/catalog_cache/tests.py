from __future__ import annotations

from unittest.mock import Mock, patch

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

    def test_search_returns_category_id_and_hashtags(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="104",
            name="Гвоздь 100",
            sku="NAIL-100",
            search_text="гвоздь 100 nail-100 крепеж #fastener",
            category_id="12",
            category_name="Крепеж",
            unit_symbol="кг",
            is_active=True,
            hashtags=["fastener", "nail"],
            source_updated_at=now,
            synced_at=now,
        )

        items = CatalogLookupService().search_items("гвоздь", limit=10)
        item = next((i for i in items if i["id"] == 104), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["category_id"], "12")
        self.assertEqual(item["hashtags"], ["fastener", "nail"])

    def test_search_matches_by_hashtag_text(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="105",
            name="Анкер",
            sku="ANCHOR-10",
            search_text="анкер anchor-10 крепеж #heavy",
            category_id="12",
            category_name="Крепеж",
            unit_symbol="шт",
            is_active=True,
            hashtags=["heavy", "metal"],
            source_updated_at=now,
            synced_at=now,
        )

        items = CatalogLookupService().search_items("heavy", limit=10)
        self.assertGreater(len(items), 0)
        self.assertIn(105, {i["id"] for i in items})

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

    def test_sync_items_records_unit_id_and_default_active(self) -> None:
        api = Mock()
        api.browse_items.side_effect = [
            {
                "items": [
                    {
                        "id": 701,
                        "name": "Саморез",
                        "sku": "SCR-77",
                        "category_id": 12,
                        "category_name": "Крепеж",
                        "unit_id": "5",
                        "unit_symbol": "кг",
                        "is_active": True,
                    }
                ],
                "total_count": 1,
                "page": 1,
                "page_size": 100,
            }
        ]
        service = CatalogCacheSyncService(client=Mock())
        service.catalog_api = api

        service.sync_items(page_size=100)

        cached = CatalogCacheItem.objects.get(sync_id="701")
        self.assertEqual(cached.unit_id, "5")
        self.assertEqual(cached.unit_symbol, "кг")
        self.assertTrue(cached.is_active)

    def test_sync_items_complete_success_deactivates_unseen(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="900",
            name="Устаревшая ТМЦ",
            search_text="устаревшая",
            is_active=True,
            synced_at=now,
        )
        api = Mock()
        api.browse_items.side_effect = [
            {
                "items": [
                    {
                        "id": 901,
                        "name": "Новая ТМЦ",
                        "is_active": True,
                    }
                ],
                "total_count": 1,
                "page": 1,
                "page_size": 100,
            }
        ]
        service = CatalogCacheSyncService(client=Mock())
        service.catalog_api = api

        stats = service.sync_items(page_size=100)

        self.assertTrue(stats.complete)
        self.assertIsNone(stats.aborted_reason)
        self.assertEqual(stats.deactivated, 1)
        unseen = CatalogCacheItem.objects.get(sync_id="900")
        self.assertFalse(unseen.is_active)

    def test_sync_items_partial_scan_does_not_deactivate(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="910",
            name="Конкурент",
            search_text="конкурент",
            is_active=True,
            synced_at=now,
        )
        api = Mock()
        api.browse_items.side_effect = [
            {
                "items": [
                    {
                        "id": 911,
                        "name": "Fresh",
                        "is_active": True,
                    }
                ],
                # intentionally inflated total_count to force partial
                "total_count": 999,
                "page": 1,
                "page_size": 100,
            },
            {"items": [], "total_count": 999, "page": 2, "page_size": 100},
        ]
        service = CatalogCacheSyncService(client=Mock())
        service.catalog_api = api

        # Guarantee loop exits after one page.
        stats = service.sync_items(page_size=100, max_pages=1)

        self.assertFalse(stats.complete)
        self.assertEqual(stats.deactivated, 0)
        self.assertEqual(CatalogCacheItem.objects.get(sync_id="910").is_active, True)

    def test_sync_items_count_mismatch_does_not_prune(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="920",
            name="Item-A",
            search_text="a",
            is_active=True,
            synced_at=now,
        )
        api = Mock()
        # Repo returns 1 item but claims total=2 — counts differ; no pruning.
        api.browse_items.side_effect = [
            {
                "items": [{"id": 921, "name": "Item-B", "is_active": True}],
                "total_count": 2,
                "page": 1,
                "page_size": 100,
            },
            {"items": [], "total_count": 2, "page": 2, "page_size": 100},
        ]
        service = CatalogCacheSyncService(client=Mock())
        service.catalog_api = api

        stats = service.sync_items(page_size=100)

        self.assertFalse(stats.complete)
        self.assertEqual(stats.aborted_reason, "count_mismatch")
        self.assertEqual(stats.deactivated, 0)
        self.assertEqual(CatalogCacheItem.objects.get(sync_id="920").is_active, True)

    def test_write_through_deactivate_item(self) -> None:
        CatalogCacheItem.objects.create(
            sync_id="42", name="Test", search_text="t", is_active=True,
            synced_at=timezone.now(),
        )
        service = CatalogCacheSyncService(client=Mock())
        updated = service.deactivate_item(42)
        self.assertEqual(updated, 1)
        cached = CatalogCacheItem.objects.get(sync_id="42")
        self.assertFalse(cached.is_active)

    def test_write_through_invalidate_by_category(self) -> None:
        CatalogCacheItem.objects.create(
            sync_id="44", name="A", search_text="a",
            category_id="12", category_name="Крепеж",
            is_active=True, synced_at=timezone.now(),
        )
        CatalogCacheItem.objects.create(
            sync_id="45", name="B", search_text="b",
            category_id="13", category_name="Другое",
            is_active=True, synced_at=timezone.now(),
        )
        service = CatalogCacheSyncService(client=Mock())
        updated = service.invalidate_by_category(12)
        self.assertEqual(updated, 1)
        self.assertFalse(CatalogCacheItem.objects.get(sync_id="44").is_active)
        self.assertTrue(CatalogCacheItem.objects.get(sync_id="45").is_active)

    def test_write_through_invalidate_by_unit(self) -> None:
        CatalogCacheItem.objects.create(
            sync_id="46", name="U1", search_text="u1",
            unit_id="5", unit_symbol="кг",
            is_active=True, synced_at=timezone.now(),
        )
        CatalogCacheItem.objects.create(
            sync_id="47", name="U2", search_text="u2",
            unit_id="6", unit_symbol="л",
            is_active=True, synced_at=timezone.now(),
        )
        service = CatalogCacheSyncService(client=Mock())
        updated = service.invalidate_by_unit(5)
        self.assertEqual(updated, 1)
        self.assertFalse(CatalogCacheItem.objects.get(sync_id="46").is_active)
        self.assertTrue(CatalogCacheItem.objects.get(sync_id="47").is_active)

    def test_write_through_category_rename_updates_snapshot(self) -> None:
        CatalogCacheItem.objects.create(
            sync_id="48", name="Renamed Cat", search_text="rc",
            category_id="22", category_name="Старая",
            is_active=True, synced_at=timezone.now(),
        )
        service = CatalogCacheSyncService(client=Mock())
        updated = service.invalidate_category_name(22, "Новая категория")
        self.assertEqual(updated, 1)
        self.assertEqual(
            CatalogCacheItem.objects.get(sync_id="48").category_name,
            "Новая категория",
        )

    def test_write_through_unit_rename_updates_symbol(self) -> None:
        CatalogCacheItem.objects.create(
            sync_id="49", name="Renamed Unit", search_text="ru",
            unit_id="9", unit_symbol="kg",
            is_active=True, synced_at=timezone.now(),
        )
        service = CatalogCacheSyncService(client=Mock())
        updated = service.invalidate_unit_symbol(9, "кг")
        self.assertEqual(updated, 1)
        self.assertEqual(
            CatalogCacheItem.objects.get(sync_id="49").unit_symbol,
            "кг",
        )

    def test_lookup_exposes_unit_id_field(self) -> None:
        now = timezone.now()
        CatalogCacheItem.objects.create(
            sync_id="50", name="Sample", search_text="sample",
            unit_id="8", unit_symbol="л",
            is_active=True, synced_at=now,
        )
        items = CatalogLookupService().search_items("sample", limit=10)
        self.assertEqual(items[0]["unit_id"], "8")
        self.assertEqual(items[0]["unit_symbol"], "л")


class CatalogCacheRebuildActionTests(TestCase):
    """The SSR admin button now reports fetched/upserted/deactivated/duration."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from apps.users.models import Role, SyncUserBinding

        user_model = get_user_model()
        self.chief = user_model.objects.create_user(
            username="chief", password="pass12345",
            is_staff=False, is_active=True,
        )
        SyncUserBinding.objects.create(user=self.chief, sync_role=Role.CHIEF_STOREKEEPER)
        self.client.force_login(self.chief)

    def test_rebuild_stats_in_messages_on_success(self) -> None:
        from apps.catalog_cache.services import CatalogCacheSyncStats

        stats = CatalogCacheSyncStats(
            pages=2,
            fetched=10,
            upserted=10,
            skipped=0,
            total_count=10,
            deactivated=2,
            duration_ms=1200,
            complete=True,
        )
        with patch(
            "apps.catalog.views.CatalogCacheSyncService.sync_items",
            return_value=stats,
        ):
            response = self.client.post(
                "/nomenclature/ssr/cache/sync/", follow=True,
            )
        self.assertEqual(response.status_code, 200)
        # Convert messages into a single body string for assertions.
        joined = " | ".join(
            f"({m.tags}) {str(m.message)}" for m in response.context["messages"]
        )
        self.assertIn("загружено 10", joined)
        self.assertIn("деактивировано 2", joined)
        self.assertIn("1.2", joined)

    def test_rebuild_stats_warns_on_aborted_scan(self) -> None:
        from apps.catalog_cache.services import CatalogCacheSyncStats

        stats = CatalogCacheSyncStats(
            pages=1, fetched=5, upserted=5, skipped=0,
            total_count=99, deactivated=0, duration_ms=400,
            complete=False, aborted_reason="count_mismatch",
        )
        with patch(
            "apps.catalog.views.CatalogCacheSyncService.sync_items",
            return_value=stats,
        ):
            response = self.client.post(
                "/nomenclature/ssr/cache/sync/", follow=True,
            )
        self.assertEqual(response.status_code, 200)
        joined = " | ".join(str(m.message) for m in response.context["messages"])
        self.assertIn("не завершилась", joined)
        self.assertIn("count_mismatch", joined)
