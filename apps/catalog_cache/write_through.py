"""
Write-through cache facade for catalog admin operations (TZ-V3.2 stage C2).

Wraps successful SyncServer admin mutations with single-pass local cache
coherence:

- create / update / activate target → upsert snapshot via SyncServer's read model
- deactivate / delete / merge source → mark local row ``is_active=False``
- merge target → upsert target snapshot
- category delete / deactivate / merge → invalidate dependent ``category_id``
  rows (rename updates ``category_name`` snapshots in-place)
- unit delete / deactivate → invalidate dependent ``unit_id`` rows
  (rename updates ``unit_symbol`` snapshots in-place)

Failures of the authoritative SyncServer write do NOT change the cache.
"""
from __future__ import annotations

from typing import Any

import structlog

from apps.catalog_cache.services import CatalogCacheSyncService
from apps.sync_client.client import SyncServerClient

logger = structlog.get_logger()


def _coerce_id(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _safe_fetch(client: SyncServerClient, method: str, path: str) -> dict[str, Any] | None:
    """Best-effort SyncServer GET used to build a write-through snapshot.

    Returns ``None`` on any transport / parse error — by design, since the
    authoritative SyncServer mutation has already succeeded and cache freshness
    is best-effort until the next admin rebuild.
    """
    try:
        response = client.request(method, path)
    except Exception:
        logger.warning("catalog_cache_write_through_fetch_failed", path=path, exc_info=True)
        return None
    if isinstance(response, dict):
        return response
    return None


def apply_item_write_through(
    *,
    service: CatalogCacheSyncService,
    client: SyncServerClient,
    response: dict[str, Any],
    operation: str,
    target_item_id: str | int | None = None,
    source_item_ids: list[str | int] | None = None,
) -> None:
    """Update local cache after a SyncServer admin item mutation.

    ``operation`` is one of ``"create"``, ``"update"``, ``"activate"``,
    ``"deactivate"``, ``"delete"``, ``"merge"``.
    """
    if operation == "merge":
        # merge: deactivate source row(s), upsert target row
        for sid in source_item_ids or []:
            service.deactivate_item(sid)
        target_id = _coerce_id(target_item_id or response.get("id"))
        if target_id:
            snapshot = _safe_fetch(client, "GET", f"/catalog/read/items/{target_id}")
            if snapshot:
                try:
                    service.upsert_item(snapshot)
                except Exception:
                    logger.warning(
                        "catalog_cache_merge_target_upsert_failed",
                        target_id=target_id,
                        exc_info=True,
                    )
        return

    if operation in ("deactivate", "delete"):
        service.deactivate_item(target_item_id or response.get("id") or "")
        return

    if operation in ("create", "update", "activate"):
        target_id = _coerce_id(target_item_id or response.get("id"))
        if not target_id:
            return
        snapshot = (
            response
            if operation == "create" and all(
                k in response for k in ("name", "category_name", "unit_symbol")
            )
            else _safe_fetch(client, "GET", f"/catalog/read/items/{target_id}")
        )
        if snapshot:
            try:
                service.upsert_item(snapshot)
            except Exception:
                logger.warning(
                    "catalog_cache_item_upsert_failed",
                    target_id=target_id,
                    operation=operation,
                    exc_info=True,
                )


def apply_category_write_through(
    *,
    service: CatalogCacheSyncService,
    response: dict[str, Any],
    operation: str,
    previous_name: str | None = None,
    target_category_id: str | int | None = None,
    source_category_ids: list[str | int] | None = None,
) -> None:
    """Update local cache after a SyncServer admin category mutation.

    ``operation`` is one of ``"create"``, ``"update"``, ``"deactivate"``,
    ``"delete"``, ``"merge"``.
    """
    category_id = _coerce_id(target_category_id or response.get("id"))
    new_name = (
        response.get("name") if isinstance(response, dict) else None
    )

    if operation == "merge":
        for sid in source_category_ids or []:
            service.invalidate_by_category(sid)
        # merge target stays — items visible under new category will be refreshed
        # on next admin rebuild.
        if category_id and new_name:
            service.invalidate_category_name(category_id, new_name)
        return

    if operation in ("deactivate", "delete"):
        service.invalidate_by_category(category_id)
        return

    if operation in ("create", "update", "activate"):
        if category_id and new_name and new_name != previous_name:
            service.invalidate_category_name(category_id, new_name)
        return


def apply_unit_write_through(
    *,
    service: CatalogCacheSyncService,
    response: dict[str, Any],
    operation: str,
    previous_symbol: str | None = None,
    target_unit_id: str | int | None = None,
) -> None:
    """Update local cache after a SyncServer admin unit mutation.

    ``operation`` is one of ``"create"``, ``"update"``, ``"deactivate"``,
    ``"delete"``.
    """
    unit_id = _coerce_id(target_unit_id or response.get("id"))
    new_symbol = (
        response.get("symbol") if isinstance(response, dict) else None
    )

    if operation in ("deactivate", "delete"):
        service.invalidate_by_unit(unit_id)
        return

    if operation in ("create", "update", "activate"):
        if unit_id and new_symbol and new_symbol != previous_symbol:
            service.invalidate_unit_symbol(unit_id, new_symbol)
        return
