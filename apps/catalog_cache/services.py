from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog_cache.models import CatalogCacheItem
from apps.sync_client.catalog_api import CatalogAPI
from apps.sync_client.client import SyncServerClient

SYNC_SERVER_MAX_PAGE_SIZE = 100
LATIN_LAYOUT_CHARS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"
CYRILLIC_LAYOUT_CHARS = "ёйцукенгшщзхъфывапролджэячсмитьбю."
KEYBOARD_LAYOUT_TRANSLATION = str.maketrans(
    LATIN_LAYOUT_CHARS + CYRILLIC_LAYOUT_CHARS,
    CYRILLIC_LAYOUT_CHARS + LATIN_LAYOUT_CHARS,
)


@dataclass
class CatalogCacheSyncStats:
    pages: int = 0
    fetched: int = 0
    upserted: int = 0
    skipped: int = 0
    total_count: int = 0


class CatalogCacheSyncService:
    def __init__(self, client: SyncServerClient | None = None) -> None:
        self.client = client or SyncServerClient(force_root=True)
        self.catalog_api = CatalogAPI(self.client)

    def upsert_items(
        self,
        items: list[dict[str, Any]],
        *,
        synced_at=None,
    ) -> int:
        if synced_at is None:
            synced_at = timezone.now()
        return self._upsert_items(items, synced_at=synced_at)

    def sync_items(
        self,
        *,
        page_size: int = SYNC_SERVER_MAX_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> CatalogCacheSyncStats:
        page_size = min(max(int(page_size or SYNC_SERVER_MAX_PAGE_SIZE), 1), SYNC_SERVER_MAX_PAGE_SIZE)
        stats = CatalogCacheSyncStats()
        synced_at = timezone.now()
        page = 1

        while True:
            payload = self.catalog_api.browse_items(filters={"page": page, "page_size": page_size})
            items = payload.get("items", []) if isinstance(payload, dict) else []
            stats.total_count = int(payload.get("total_count") or stats.total_count or 0) if isinstance(payload, dict) else 0

            if not items:
                break

            stats.pages += 1
            stats.fetched += len(items)
            batch_upserted = self.upsert_items(items, synced_at=synced_at)
            stats.upserted += batch_upserted
            stats.skipped += max(len(items) - batch_upserted, 0)

            if max_pages is not None and page >= max_pages:
                break
            if stats.total_count and page * page_size >= stats.total_count:
                break
            if len(items) < page_size and not stats.total_count:
                break

            page += 1

        return stats

    def _upsert_items(self, items: list[dict[str, Any]], *, synced_at) -> int:
        records: list[CatalogCacheItem] = []
        for item in items:
            sync_id = self._normalize_id(item.get("id"))
            if not sync_id:
                continue

            name = self._normalize_str(item.get("name") or item.get("sku") or sync_id, limit=255)
            sku = self._normalize_str(item.get("sku"), limit=120)
            category_id = self._normalize_id(item.get("category_id"))
            category_name = self._normalize_str(item.get("category_name"), limit=255)
            unit_symbol = self._normalize_str(item.get("unit_symbol"), limit=64)
            search_text = self._build_search_text(
                sync_id=sync_id,
                name=name,
                sku=sku,
                category_name=category_name,
                unit_symbol=unit_symbol,
            )
            records.append(
                CatalogCacheItem(
                    sync_id=sync_id,
                    name=name,
                    sku=sku,
                    search_text=search_text,
                    category_id=category_id,
                    category_name=category_name,
                    unit_symbol=unit_symbol,
                    is_active=bool(item.get("is_active", True)),
                    source_updated_at=self._parse_remote_datetime(
                        item.get("updated_at") or item.get("source_updated_at")
                    ),
                    synced_at=synced_at,
                )
            )

        if not records:
            return 0

        with transaction.atomic():
            CatalogCacheItem.objects.bulk_create(
                records,
                batch_size=500,
                update_conflicts=True,
                update_fields=[
                    "name",
                    "sku",
                    "search_text",
                    "category_id",
                    "category_name",
                    "unit_symbol",
                    "is_active",
                    "source_updated_at",
                    "synced_at",
                ],
                unique_fields=["sync_id"],
            )

        return len(records)

    @staticmethod
    def _normalize_str(value: Any, *, limit: int | None = None) -> str:
        normalized = str(value or "").strip()
        if limit is None:
            return normalized
        return normalized[:limit]

    @staticmethod
    def _normalize_id(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _parse_remote_datetime(value: Any):
        if isinstance(value, str):
            parsed = parse_datetime(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _build_search_text(
        *,
        sync_id: str,
        name: str,
        sku: str,
        category_name: str,
        unit_symbol: str,
    ) -> str:
        parts = [name, sku, category_name, unit_symbol, sync_id]
        normalized_parts = [part.strip().lower() for part in parts if part and part.strip()]
        return " ".join(normalized_parts)


class CatalogLookupService:
    def search_items(self, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
        normalized_query = self._normalize_query(query)
        if len(normalized_query) < 2:
            return []

        query_variants = self._build_query_variants(normalized_query)
        queryset = CatalogCacheItem.objects.filter(is_active=True).filter(
            self._build_search_filter(query_variants)
        )

        queryset = queryset.annotate(
            exact_sku_rank=Case(
                *[
                    When(sku__iexact=variant, then=Value(rank))
                    for rank, variant in enumerate(query_variants)
                ],
                default=Value(len(query_variants) + 1),
                output_field=IntegerField(),
            ),
            prefix_rank=Case(
                *self._build_prefix_rank_cases(query_variants),
                default=Value(len(query_variants) * 2 + 1),
                output_field=IntegerField(),
            ),
        ).order_by("exact_sku_rank", "prefix_rank", "name", "sync_id")

        items: list[dict[str, Any]] = []
        for item in queryset[:limit]:
            serialized = self._serialize_item(item)
            if serialized is not None:
                items.append(serialized)
        return items

    @staticmethod
    def _serialize_item(item: CatalogCacheItem) -> dict[str, Any] | None:
        try:
            item_id = int(item.sync_id)
        except (TypeError, ValueError):
            return None

        return {
            "id": item_id,
            "name": item.name,
            "sku": item.sku,
            "unit_symbol": item.unit_symbol,
            "category_name": item.category_name,
            "is_active": item.is_active,
        }

    @staticmethod
    def _normalize_query(value: Any) -> str:
        return " ".join(str(value or "").split()).strip().lower()

    @classmethod
    def _build_query_variants(cls, query: str) -> list[str]:
        variants: list[str] = []
        for candidate in (query, cls._swap_keyboard_layout(query)):
            normalized = cls._normalize_query(candidate)
            if normalized and normalized not in variants:
                variants.append(normalized)
        return variants

    @classmethod
    def _build_search_filter(cls, query_variants: list[str]) -> Q:
        combined = Q()
        for variant in query_variants:
            variant_filter = Q()
            for token in variant.split():
                variant_filter &= (
                    Q(sku__icontains=token)
                    | Q(name__icontains=token)
                    | Q(search_text__icontains=token)
                )
            combined |= variant_filter
        return combined

    @staticmethod
    def _build_prefix_rank_cases(query_variants: list[str]) -> list[When]:
        cases: list[When] = []
        for rank, variant in enumerate(query_variants):
            priority = rank * 2
            cases.append(When(sku__istartswith=variant, then=Value(priority)))
            cases.append(When(name__istartswith=variant, then=Value(priority + 1)))
        return cases

    @staticmethod
    def _swap_keyboard_layout(value: str) -> str:
        return str(value or "").translate(KEYBOARD_LAYOUT_TRANSLATION)
