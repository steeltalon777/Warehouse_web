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
    deactivated: int = 0
    duration_ms: int = 0
    complete: bool = False
    aborted_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "fetched": self.fetched,
            "upserted": self.upserted,
            "skipped": self.skipped,
            "total_count": self.total_count,
            "deactivated": self.deactivated,
            "duration_ms": self.duration_ms,
            "complete": self.complete,
            "aborted_reason": self.aborted_reason,
        }


class CatalogCacheSyncService:
    def __init__(self, client: SyncServerClient | None = None) -> None:
        self.client = client or SyncServerClient(force_root=True)
        self.catalog_api = CatalogAPI(self.client)

    # ---------- Public write-through helpers (TZ C2) ----------

    def upsert_items(
        self,
        items: list[dict[str, Any]],
        *,
        synced_at=None,
    ) -> int:
        if synced_at is None:
            synced_at = timezone.now()
        return self._upsert_items(items, synced_at=synced_at)

    def upsert_item(
        self,
        item: dict[str, Any],
        *,
        synced_at=None,
    ) -> int:
        return self.upsert_items([item], synced_at=synced_at)

    def deactivate_item(self, item_id: str | int) -> int:
        """Mark cached item as inactive after SyncServer-side deactivation/delete/merge-source."""
        sync_id = self._normalize_id(item_id)
        if not sync_id:
            return 0
        return CatalogCacheItem.objects.filter(sync_id=sync_id).update(
            is_active=False,
            synced_at=timezone.now(),
        )

    def invalidate_by_category(self, category_id: str | int) -> int:
        """Mark cached items in a category inactive; safe-updating category name requires rebuild."""
        normalized = self._normalize_id(category_id)
        if not normalized:
            return 0
        return CatalogCacheItem.objects.filter(category_id=normalized).update(
            is_active=False,
            synced_at=timezone.now(),
        )

    def invalidate_by_unit(self, unit_id: str | int) -> int:
        """Mark cached items using a unit inactive; safe-updating unit name requires rebuild."""
        normalized = self._normalize_id(unit_id)
        if not normalized:
            return 0
        return CatalogCacheItem.objects.filter(unit_id=normalized).update(
            is_active=False,
            synced_at=timezone.now(),
        )

    def invalidate_category_name(self, category_id: str | int, name: str) -> int:
        """Update category_name for cached items when remote category was renamed."""
        normalized = self._normalize_id(category_id)
        new_name = self._normalize_str(name, limit=255) or None
        if not normalized or not new_name:
            return 0
        return CatalogCacheItem.objects.filter(category_id=normalized).update(
            category_name=new_name,
            synced_at=timezone.now(),
        )

    def invalidate_unit_symbol(self, unit_id: str | int, symbol: str) -> int:
        """Update unit_symbol for cached items when remote unit was renamed."""
        normalized = self._normalize_id(unit_id)
        new_symbol = self._normalize_str(symbol, limit=64) or None
        if not normalized or not new_symbol:
            return 0
        return CatalogCacheItem.objects.filter(unit_id=normalized).update(
            unit_symbol=new_symbol,
            synced_at=timezone.now(),
        )

    # ---------- Full reconciliation (TZ C3) ----------

    def sync_items(
        self,
        *,
        page_size: int = SYNC_SERVER_MAX_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> CatalogCacheSyncStats:
        """
        Full page-by-page reconciliation.

        Behaviour contract (TZ C3):
        - perform full active scan; admin action calls this with no ``max_pages``.
        - upsert pages as read into cache using a single ``reconciliation_started_at``
          as ``synced_at`` for all seen rows.
        - collect unique seen IDs in memory for completeness check; never use
          ``NOT IN (...)`` against large lists.
        - only after complete-success — seen count matches remote ``total_count`` —
          issue ONE bulk update ``is_active=False`` for active rows whose
          ``synced_at < reconciliation_started_at`` (strict ``<`` preserves the
          current scan rows, and never prunes fresher write-through snapshots).
        - failed/partial/count-mismatch scan does NOT prune, and records an
          ``aborted_reason`` for diagnostics.
        """
        import time as _time

        page_size = min(max(int(page_size or SYNC_SERVER_MAX_PAGE_SIZE), 1), SYNC_SERVER_MAX_PAGE_SIZE)
        stats = CatalogCacheSyncStats()
        reconciliation_started_at = timezone.now()
        t0 = _time.perf_counter()
        seen_ids: set[str] = set()
        page = 1
        scan_complete = False

        try:
            while True:
                try:
                    payload = self.catalog_api.browse_items(
                        filters={"page": page, "page_size": page_size}
                    )
                except Exception as exc:  # noqa: BLE001 — propagate but mark aborted
                    stats.aborted_reason = f"browse_failed:{exc.__class__.__name__}"
                    break

                if not isinstance(payload, dict):
                    stats.aborted_reason = "browse_returned_non_dict"
                    break

                items = payload.get("items") or []
                remote_total = payload.get("total_count")
                if isinstance(remote_total, int):
                    stats.total_count = remote_total

                if not items:
                    # No items on the page — scan is finished.
                    scan_complete = True
                    break

                stats.pages += 1
                stats.fetched += len(items)
                for item in items:
                    sid = self._normalize_id(item.get("id"))
                    if sid:
                        seen_ids.add(sid)

                batch_upserted = self._upsert_items(items, synced_at=reconciliation_started_at)
                stats.upserted += batch_upserted
                stats.skipped += max(len(items) - batch_upserted, 0)

                # Honor explicit guard for compatibility with the management command.
                if max_pages is not None and page >= max_pages:
                    stats.aborted_reason = "max_pages_reached"
                    break

                # Continuation conditions.
                if stats.total_count and page * page_size >= stats.total_count:
                    scan_complete = True
                    break
                if len(items) < page_size and not stats.total_count:
                    scan_complete = True
                    break

                page += 1

            if not scan_complete and not stats.aborted_reason:
                stats.aborted_reason = "scan_incomplete"

            # Completeness check: seen_ids must equal total_count to allow prune.
            if (
                scan_complete
                and not stats.aborted_reason
                and stats.total_count
                and len(seen_ids) != stats.total_count
            ):
                stats.aborted_reason = "count_mismatch"

            # Only when scan completed cleanly: single UPDATE deactivate unseen rows.
            if not stats.aborted_reason and scan_complete:
                stats.deactivated = CatalogCacheItem.objects.filter(
                    is_active=True,
                ).filter(
                    ~Q(sync_id__in=list(seen_ids)),
                ).filter(
                    synced_at__lt=reconciliation_started_at,
                ).update(
                    is_active=False,
                    synced_at=reconciliation_started_at,
                )
                stats.complete = True
        finally:
            stats.duration_ms = int((_time.perf_counter() - t0) * 1000)

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
            unit_id = self._normalize_id(item.get("unit_id"))
            unit_symbol = self._normalize_str(item.get("unit_symbol"), limit=64)
            hashtags = item.get("hashtags")
            if not isinstance(hashtags, list):
                hashtags = None
            search_text = self._build_search_text(
                sync_id=sync_id,
                name=name,
                sku=sku,
                category_name=category_name,
                unit_symbol=unit_symbol,
                hashtags=hashtags,
            )
            records.append(
                CatalogCacheItem(
                    sync_id=sync_id,
                    name=name,
                    sku=sku,
                    search_text=search_text,
                    category_id=category_id,
                    category_name=category_name,
                    unit_id=unit_id or None,
                    unit_symbol=unit_symbol,
                    is_active=bool(item.get("is_active", True)),
                    hashtags=hashtags,
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
                    "unit_id",
                    "unit_symbol",
                    "is_active",
                    "hashtags",
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
        hashtags: list[str] | None = None,
    ) -> str:
        parts = [name, sku, category_name, unit_symbol, sync_id]
        if hashtags:
            parts.extend(hashtags)
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
            "category_id": str(item.category_id) if item.category_id else "",
            "category_name": item.category_name,
            "unit_id": str(item.unit_id) if item.unit_id else "",
            "unit_symbol": item.unit_symbol,
            "hashtags": item.hashtags,
            "is_active": item.is_active,
        }

    @staticmethod
    def _normalize_query(value: Any) -> str:
        return " ".join(str(value or "").split()).strip().lower()

    @classmethod
    def _build_query_variants(cls, query: str) -> list[str]:
        variants: list[str] = []
        candidates = [query, cls._swap_keyboard_layout(query)]
        for candidate in candidates:
            normalized = cls._normalize_query(candidate)
            if normalized and normalized not in variants:
                variants.append(normalized)
            stripped = normalized.lstrip("#")
            if stripped and stripped != normalized and stripped not in variants:
                variants.append(stripped)
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
