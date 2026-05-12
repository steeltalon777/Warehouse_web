from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db.utils import DatabaseError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog_cache.services import CatalogCacheSyncService, CatalogLookupService
from apps.catalog.services import CatalogService
from apps.common.permissions import get_user_role, is_observer
from apps.operations.constants import OPERATION_STATUS_META, OPERATION_TYPE_LABELS, OPERATION_TYPE_META
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)

QTY_SCALE = Decimal("0.001")
ACCEPTANCE_STATE_META = {
    "not_required": {"label": "Не требуется", "tone": "muted"},
    "pending": {"label": "Ожидает приёмки", "tone": "warning"},
    "in_progress": {"label": "Приёмка в процессе", "tone": "info"},
    "resolved": {"label": "Приёмка завершена", "tone": "success"},
}


def _format_copy_datetime(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return "-"

    parsed = parse_datetime(raw_value)
    if parsed is None:
        return raw_value
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return timezone.localtime(parsed).strftime("%d.%m.%Y %H:%M")


def build_operation_copy_document(operation: dict[str, Any]) -> str:
    """Build a minimal operation document text for manual copy/paste."""
    operation_type = str(operation.get("type_label") or operation.get("operation_type") or "Операция")
    operation_id = str(operation.get("id") or "-")
    author = str(operation.get("author_label") or operation.get("created_by_user_id") or "-")

    lines = [
        "Документ по складской операции",
        f"Операция: {operation_id}",
        f"Дата операции: {_format_copy_datetime(operation.get('effective_at'))}",
        f"Тип операции: {operation_type}",
    ]

    if str(operation.get("operation_type") or "").upper() == "MOVE":
        lines.extend(
            [
                f"Склад-источник: {operation.get('source_site_name') or '-'}",
                f"Склад-получатель: {operation.get('destination_site_name') or '-'}",
            ]
        )
    else:
        lines.append(f"Склад: {operation.get('site_name') or '-'}")

    lines.append(f"Запрос на создание отправил: {author}")
    return "\n".join(lines)


class OperationPageService:
    def __init__(self, client: SyncServerClient, *, request=None) -> None:
        self.client = client
        self.request = request
        self.catalog = CatalogService(client)
        self.catalog_lookup = CatalogLookupService()

    def get_available_sites(self) -> list[dict[str, Any]]:
        response = self.client.get("/auth/sites")
        sites = response.get("available_sites", []) if isinstance(response, dict) else []
        return self._normalize_sites(sites)

    def get_all_sites(self) -> list[dict[str, Any]]:
        try:
            root_client = SyncServerClient(request=self.request, force_root=True)
            response = root_client.get("/catalog/sites")
            sites = response.get("sites", []) if isinstance(response, dict) else []
            return self._normalize_sites(sites)
        except Exception:
            logger.exception("Failed to load global site names, falling back to accessible sites.")
            return self.get_available_sites()

    @staticmethod
    def _normalize_sites(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for site in sites:
            permissions = site.get("permissions") or {}
            try:
                site_id = int(site.get("site_id"))
            except (TypeError, ValueError):
                continue
            normalized.append(
                {
                    "id": site_id,
                    "site_id": site_id,
                    "name": str(site.get("name") or site.get("code") or site_id),
                    "code": str(site.get("code") or ""),
                    "can_operate": bool(permissions.get("can_operate")),
                    "can_view": bool(permissions.get("can_view", True)),
                }
            )
        normalized.sort(key=lambda site: site["name"].lower())
        return normalized

    def get_operate_sites(self) -> list[dict[str, Any]]:
        return [site for site in self.get_available_sites() if site["can_operate"]]

    def get_current_role(self) -> str:
        request_user = getattr(self.request, "user", None)
        if request_user is not None and getattr(request_user, "is_superuser", False):
            return "root"
        return str(get_user_role(request_user) or "")

    def get_fixed_operating_site_id(self) -> int | None:
        role = self.get_current_role()
        if role != "storekeeper":
            return None

        try:
            default_site_id = getattr(self.request.user.sync_binding, "default_site_id", "")
        except Exception:
            return None
        return self._to_int(default_site_id)

    def can_choose_source_site(self) -> bool:
        return self.get_current_role() in {"root", "chief_storekeeper"}

    def search_items(self, query: str, *, limit: int = 12) -> list[dict[str, Any]]:
        normalized_limit = max(int(limit or 12), 1)
        try:
            cached_items = self.catalog_lookup.search_items(query, limit=normalized_limit)
        except DatabaseError:
            logger.warning("Local catalog cache unavailable, falling back to remote search")
            cached_items = []

        if len(cached_items) >= normalized_limit:
            return cached_items

        try:
            remote_items = self._search_remote_items(query, limit=normalized_limit)
        except SyncServerAPIError:
            logger.warning("Remote catalog search unavailable, using local catalog cache results only")
            remote_items = []
        if remote_items:
            self._warm_catalog_cache(remote_items)

        return self._merge_search_items(cached_items, remote_items, limit=normalized_limit)

    def get_items_index(self) -> dict[int, dict[str, Any]]:
        result = self.catalog.list_items()
        if not result.ok:
            return {}

        index: dict[int, dict[str, Any]] = {}
        for item in result.data or []:
            item_id = self._to_int(item.get("id"))
            if item_id is None:
                continue
            index[item_id] = {
                "id": item_id,
                "name": str(item.get("name") or item.get("sku") or item_id),
                "sku": str(item.get("sku") or ""),
                "unit_symbol": str(item.get("unit_symbol") or item.get("unit") or ""),
            }
        return index

    def get_sites_index(self) -> dict[int, dict[str, Any]]:
        return {int(site["site_id"]): site for site in self.get_all_sites()}

    def present_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()
        user_labels = self._get_local_user_labels([operation.get("created_by_user_id")])
        return self._present_operation(
            operation,
            items_index=items_index,
            sites_index=sites_index,
            user_labels=user_labels,
        )

    def present_operations(self, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()
        user_labels = self._get_local_user_labels(
            [operation.get("created_by_user_id") for operation in operations]
        )
        return [
            self._present_operation(
                operation,
                items_index=items_index,
                sites_index=sites_index,
                user_labels=user_labels,
            )
            for operation in operations
        ]

    @classmethod
    def present_search_item(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        return cls._serialize_search_item(item)

    def _search_remote_items(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        result = self.catalog.browse_items(search=query, page=1, page_size=max(limit, 25))
        if not result.ok:
            return []

        payload = result.data if isinstance(result.data, dict) else {}
        items = payload.get("items", []) if isinstance(payload, dict) else []
        serialized_items: list[dict[str, Any]] = []
        for item in items:
            serialized = self._serialize_search_item(item)
            if serialized is None or not serialized["is_active"]:
                continue
            serialized_items.append(serialized)
            if len(serialized_items) >= limit:
                break
        return serialized_items

    def _warm_catalog_cache(self, items: list[dict[str, Any]]) -> None:
        try:
            CatalogCacheSyncService(client=self.client).upsert_items(items)
        except Exception:
            logger.exception("Failed to warm local catalog cache from remote item search results.")

    @classmethod
    def _merge_search_items(
        cls,
        cached_items: list[dict[str, Any]],
        remote_items: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for item in [*cached_items, *remote_items]:
            item_id = cls._to_int(item.get("id") or item.get("item_id"))
            if item_id is None or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    @classmethod
    def _serialize_search_item(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        item_id = cls._to_int(item.get("id") or item.get("item_id"))
        if item_id is None:
            return None

        return {
            "id": item_id,
            "name": str(item.get("name") or item.get("sku") or item_id),
            "sku": str(item.get("sku") or ""),
            "unit_symbol": str(item.get("unit_symbol") or item.get("unit_name") or item.get("unit") or ""),
            "category_name": str(item.get("category_name") or ""),
            "category_id": str(item.get("category_id") or ""),
            "is_active": bool(item.get("is_active", True)),
        }

    def _present_operation(
        self,
        operation: dict[str, Any],
        *,
        items_index: dict[int, dict[str, Any]],
        sites_index: dict[int, dict[str, Any]],
        user_labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        status = str(operation.get("status") or "draft")
        status_meta = OPERATION_STATUS_META.get(status, {"label": status, "tone": "muted"})
        operation_type = str(operation.get("operation_type") or operation.get("type") or "")
        site_id = self._to_int(operation.get("site_id"))
        source_site_id = self._to_int(operation.get("source_site_id"))
        destination_site_id = self._to_int(operation.get("destination_site_id") or operation.get("target_site_id"))

        lines: list[dict[str, Any]] = []
        for line in operation.get("lines") or []:
            item_id = self._to_int(line.get("item_id"))
            item = items_index.get(item_id or -1, {})
            quantity = line.get("qty", line.get("quantity"))

            # Используем snapshot-поля, если они есть
            item_name_snapshot = line.get("item_name_snapshot")
            item_sku_snapshot = line.get("item_sku_snapshot")
            unit_symbol_snapshot = line.get("unit_symbol_snapshot")

            item_name = item_name_snapshot or item.get("name") or f"ТМЦ #{item_id}"
            sku = item_sku_snapshot or item.get("sku") or "—"
            unit_symbol = unit_symbol_snapshot or item.get("unit_symbol") or "—"

            temporary_item_id = self._to_int(line.get("temporary_item_id"))
            resolved_item_id = self._to_int(line.get("resolved_item_id"))
            resolved_item_name = line.get("resolved_item_name")
            is_draft_temporary = bool(line.get("is_draft_temporary", False))

            lines.append(
                {
                    "line_number": line.get("line_number"),
                    "item_id": item_id,
                    "item_name": item_name,
                    "sku": sku,
                    "unit_symbol": unit_symbol,
                    "quantity": quantity,
                    "comment": line.get("comment") or line.get("notes") or "",
                    "is_temporary": temporary_item_id is not None or is_draft_temporary,
                    "temporary_item_id": temporary_item_id,
                    "temporary_item_status": line.get("temporary_item_status"),
                    "resolved_item_id": resolved_item_id,
                    "resolved_item_name": resolved_item_name,
                    "item_name_snapshot": item_name_snapshot,
                    "item_sku_snapshot": item_sku_snapshot,
                    "unit_symbol_snapshot": unit_symbol_snapshot,
                    "is_draft_temporary": is_draft_temporary,
                }
            )

        line_preview = [f"{line['item_name']} x {line['quantity']}" for line in lines[:2]]
        created_by_user_id = operation.get("created_by_user_id")
        author_label = self._user_label(created_by_user_id, user_labels=user_labels)

        role = self.get_current_role()
        request_user = getattr(self.request, "user", None)
        can_submit = status in {"draft", "created"} and role != "observer"
        can_cancel = (
            status in {"draft", "created", "pending", "submitted"}
            and (request_user is None or not is_observer(request_user))
        )
        can_accept = status in {"submitted", "pending"} and role not in {"observer"}
        logger.info(
            "Operation buttons: id=%s status=%s role=%s submit=%s cancel=%s accept=%s",
            operation.get("id"), status, role, can_submit, can_cancel, can_accept,
        )
        acceptance_state = str(operation.get("acceptance_state") or "not_required")
        acceptance_meta = ACCEPTANCE_STATE_META.get(
            acceptance_state,
            {"label": acceptance_state or "—", "tone": "muted"},
        )

        return {
            **operation,
            "type_label": OPERATION_TYPE_LABELS.get(operation_type, operation_type or "Операция"),
            "status_label": str(status_meta["label"]),
            "status_tone": str(status_meta["tone"]),
            "acceptance_state_label": str(acceptance_meta["label"]),
            "acceptance_state_tone": str(acceptance_meta["tone"]),
            "effective_at": operation.get("effective_at"),
            "site_name": self._site_name(sites_index, site_id),
            "source_site_name": self._site_name(sites_index, source_site_id),
            "destination_site_name": self._site_name(sites_index, destination_site_id),
            "lines": lines,
            "line_count": len(lines),
            "line_preview": ", ".join(line_preview),
            "author_label": author_label,
            "can_submit": can_submit,
            "can_cancel": can_cancel,
            "can_accept": can_accept,
            "copy_document_text": build_operation_copy_document(
                {
                    **operation,
                    "operation_type": operation_type,
                    "type_label": OPERATION_TYPE_LABELS.get(operation_type, operation_type or "Операция"),
                    "effective_at": operation.get("effective_at"),
                    "site_name": self._site_name(sites_index, site_id),
                    "source_site_name": self._site_name(sites_index, source_site_id),
                    "destination_site_name": self._site_name(sites_index, destination_site_id),
                    "author_label": author_label,
                }
            ),
        }

    @staticmethod
    def operation_type_options() -> list[dict[str, Any]]:
        return [dict(item) for item in OPERATION_TYPE_META]

    def _get_local_user_labels(self, user_ids: list[Any]) -> dict[str, str]:
        normalized_ids = {str(user_id) for user_id in user_ids if user_id}
        if not normalized_ids:
            return {}

        try:
            User = get_user_model()
            rows = list(User.objects.filter(
                sync_binding__syncserver_user_id__in=normalized_ids
            ).values(
                "sync_binding__syncserver_user_id",
                "first_name",
                "last_name",
                "username",
            ))
        except Exception:
            logger.exception("Failed to resolve operation authors from local Django users.")
            return {}

        labels: dict[str, str] = {}
        for row in rows:
            sync_id = row.get("sync_binding__syncserver_user_id")
            if not sync_id:
                continue
            full_name = " ".join(
                part
                for part in [
                    str(row.get("first_name") or "").strip(),
                    str(row.get("last_name") or "").strip(),
                ]
                if part
            )
            username = str(row.get("username") or "").strip()
            labels[str(sync_id)] = full_name or username or str(sync_id)
        return labels

    def _user_label(self, user_id: Any, *, user_labels: dict[str, str] | None = None) -> str:
        if not user_id:
            return "—"

        normalized_id = str(user_id)
        if user_labels and normalized_id in user_labels:
            return user_labels[normalized_id]

        try:
            request_user = self.request.user
            sync_id = getattr(request_user.sync_binding, "syncserver_user_id", None)
            if sync_id and str(sync_id) == normalized_id:
                full_name = " ".join(
                    part
                    for part in [
                        str(getattr(request_user, "first_name", "") or "").strip(),
                        str(getattr(request_user, "last_name", "") or "").strip(),
                    ]
                    if part
                )
                username = str(getattr(request_user, "username", "") or "").strip()
                return full_name or username or normalized_id
        except Exception:
            pass

        return normalized_id

    @staticmethod
    def _site_name(sites_index: dict[int, dict[str, Any]], site_id: int | None) -> str:
        if site_id is None:
            return "—"
        site = sites_index.get(site_id)
        if not site:
            return str(site_id)
        return str(site.get("name") or site.get("code") or site_id)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value)).quantize(QTY_SCALE)
        except Exception:
            return None

    @staticmethod
    def _serialize_decimal(value: Decimal) -> str:
        return format(value.normalize(), "f")

    # ------------------------------------------------------------------
    # Pending acceptance grouping
    # ------------------------------------------------------------------

    def group_pending_rows(
        self,
        pending_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Group line-level pending-acceptance rows into operation-level list.

        Each group computes:
        - operation_id, operation_type (MOVE if any row has source_site_id else RECEIVE)
        - destination_site_name, source_site_name
        - line_count, total_expected_qty
        - line_preview (first 2 items)
        - updated_at_max
        """
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in pending_rows:
            op_id = str(row.get("operation_id") or "")
            if op_id:
                groups[op_id].append(row)

        sites_index = self.get_sites_index()
        items_index = self.get_items_index()
        result: list[dict[str, Any]] = []

        for operation_id, rows in groups.items():
            has_source = any(row.get("source_site_id") is not None for row in rows)
            op_type = "MOVE" if has_source else "RECEIVE"

            dest_site_id = self._to_int(rows[0].get("destination_site_id") or rows[0].get("site_id"))
            source_site_id = self._to_int(rows[0].get("source_site_id"))

            total_expected = sum(
                self._to_decimal(row.get("qty") or row.get("expected_qty") or 0) or Decimal("0")
                for row in rows
            )

            preview_items: list[str] = []
            for row in rows[:2]:
                item_id = self._to_int(row.get("item_id"))
                item = items_index.get(item_id or -1, {})
                # Используем snapshot-поля, если они есть
                item_name_snapshot = row.get("item_name_snapshot")
                item_name = item_name_snapshot or item.get("name") or f"ТМЦ #{item_id}"
                qty = self._to_decimal(row.get("qty") or row.get("expected_qty") or 0)
                qty_str = self._serialize_decimal(qty) if qty else "0"
                preview_items.append(f"{item_name} x {qty_str}")

            updated_ats = [
                row.get("updated_at") or row.get("created_at") or ""
                for row in rows
                if row.get("updated_at") or row.get("created_at")
            ]
            updated_at_max = max(updated_ats) if updated_ats else ""

            result.append({
                "operation_id": operation_id,
                "operation_type": op_type,
                "type_label": OPERATION_TYPE_LABELS.get(op_type, op_type),
                "destination_site_name": self._site_name(sites_index, dest_site_id),
                "source_site_name": self._site_name(sites_index, source_site_id),
                "line_count": len(rows),
                "total_expected_qty": self._serialize_decimal(total_expected),
                "line_preview": ", ".join(preview_items),
                "updated_at": updated_at_max,
            })

        result.sort(key=lambda op: op["updated_at"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    def compute_pending_summary(
        self,
        pending_rows: list[dict[str, Any]],
        *,
        truncated: bool = False,
    ) -> dict[str, Any]:
        """
        Compute dashboard summary from pending-acceptance rows.

        Returns dict with:
        - operation_count (unique operation_ids)
        - line_count (total rows)
        - by_destination_site: list of {site_id, site_name, count}
        - by_operation_type: list of {type, label, count}
        - truncated: bool
        """
        sites_index = self.get_sites_index()
        unique_ops: set[str] = set()
        site_counter: dict[int, int] = defaultdict(int)
        type_counter: dict[str, int] = defaultdict(int)

        for row in pending_rows:
            op_id = str(row.get("operation_id") or "")
            if op_id:
                unique_ops.add(op_id)

            dest_site_id = self._to_int(row.get("destination_site_id") or row.get("site_id"))
            if dest_site_id is not None:
                site_counter[dest_site_id] += 1

            has_source = row.get("source_site_id") is not None
            op_type = "MOVE" if has_source else "RECEIVE"
            type_counter[op_type] += 1

        by_site = [
            {
                "site_id": site_id,
                "site_name": self._site_name(sites_index, site_id),
                "count": count,
            }
            for site_id, count in sorted(site_counter.items(), key=lambda x: -x[1])
        ]

        by_type = [
            {
                "type": t,
                "label": OPERATION_TYPE_LABELS.get(t, t),
                "count": count,
            }
            for t, count in sorted(type_counter.items(), key=lambda x: -x[1])
        ]

        return {
            "operation_count": len(unique_ops),
            "line_count": len(pending_rows),
            "by_destination_site": by_site,
            "by_operation_type": by_type,
            "truncated": truncated,
        }

    # ------------------------------------------------------------------
    # Acceptance detail presenter
    # ------------------------------------------------------------------

    def present_acceptance_detail(
        self,
        operation: dict[str, Any],
        pending_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Build view-model for the acceptance detail screen.

        Args:
            operation: Full operation dict from OperationsAPI.get_operation.
            pending_rows: Pending-acceptance lines for this operation.

        Returns:
            Dict with header info and acceptance lines.
        """
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()

        status = str(operation.get("status") or "draft")
        status_meta = OPERATION_STATUS_META.get(status, {"label": status, "tone": "muted"})
        operation_type = str(operation.get("operation_type") or operation.get("type") or "")
        site_id = self._to_int(operation.get("site_id"))
        source_site_id = self._to_int(operation.get("source_site_id"))
        destination_site_id = self._to_int(
            operation.get("destination_site_id") or operation.get("target_site_id")
        )

        acceptance_state = operation.get("acceptance_state") or "pending"
        has_lost = any(
            self._to_decimal(row.get("lost_qty") or 0) or Decimal("0") > Decimal("0")
            for row in pending_rows
        )
        remaining_exists = any(
            (self._to_decimal(row.get("remaining_qty") or row.get("qty") or 0) or Decimal("0"))
            > Decimal("0")
            for row in pending_rows
        )

        if acceptance_state == "resolved":
            flow_state = "resolved"
        elif remaining_exists:
            flow_state = "in_progress"
        else:
            flow_state = "resolved"

        lines: list[dict[str, Any]] = []
        for row in pending_rows:
            operation_line_id = row.get("operation_line_id") or row.get("id")
            item_id = self._to_int(row.get("item_id"))
            item = items_index.get(item_id or -1, {})
            expected_qty = self._to_decimal(row.get("qty") or row.get("expected_qty") or 0) or Decimal("0")
            accepted_qty = self._to_decimal(row.get("accepted_qty") or 0) or Decimal("0")
            lost_qty = self._to_decimal(row.get("lost_qty") or 0) or Decimal("0")
            remaining_qty = self._to_decimal(row.get("remaining_qty") or expected_qty - accepted_qty - lost_qty) or Decimal("0")

            lines.append({
                "line_number": row.get("line_number") or operation_line_id,
                "operation_line_id": operation_line_id,
                "item_id": item_id,
                "item_name": item.get("name") or f"ТМЦ #{item_id}",
                "sku": item.get("sku") or "—",
                "unit_symbol": item.get("unit_symbol") or "—",
                "expected_qty": self._serialize_decimal(expected_qty),
                "accepted_qty": self._serialize_decimal(accepted_qty),
                "lost_qty": self._serialize_decimal(lost_qty),
                "remaining_qty": self._serialize_decimal(remaining_qty),
                "can_accept": remaining_qty > Decimal("0"),
            })

        header = {
            "operation_id": operation.get("id"),
            "document_number": operation.get("document_number") or operation.get("number") or operation.get("id"),
            "operation_type": operation_type,
            "contractor_name": operation.get("counterparty_name") or operation.get("recipient_name") or "",
            "effective_at": operation.get("effective_at"),
            "source_site_name": self._site_name(sites_index, source_site_id),
            "destination_site_name": self._site_name(sites_index, destination_site_id),
        }

        return {
            "operation_id": operation.get("id"),
            "document_number": header["document_number"],
            "operation_type": operation_type,
            "type_label": OPERATION_TYPE_LABELS.get(operation_type, operation_type or "Операция"),
            "status_label": str(status_meta["label"]),
            "status_tone": str(status_meta["tone"]),
            "acceptance_state": acceptance_state,
            "flow_state": flow_state,
            "has_lost": has_lost,
            "header": header,
            "site_name": self._site_name(sites_index, site_id),
            "source_site_name": self._site_name(sites_index, source_site_id),
            "destination_site_name": self._site_name(sites_index, destination_site_id),
            "lines": lines,
            "line_count": len(lines),
        }

    # ------------------------------------------------------------------
    # Lost assets presenter
    # ------------------------------------------------------------------

    def present_lost_assets_list(
        self,
        lost_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Present lost assets list items."""
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()
        result: list[dict[str, Any]] = []

        for row in lost_rows:
            item_id = self._to_int(row.get("item_id"))
            item = items_index.get(item_id or -1, {})
            site_id = self._to_int(row.get("site_id"))
            source_site_id = self._to_int(row.get("source_site_id"))
            qty = self._to_decimal(row.get("qty") or row.get("lost_qty") or 0) or Decimal("0")
            status = str(row.get("status") or "open")

            result.append({
                "operation_line_id": row.get("operation_line_id") or row.get("id"),
                "operation_id": row.get("operation_id"),
                "item_id": item_id,
                "item_name": item.get("name") or f"ТМЦ #{item_id}",
                "item_code": item.get("sku") or "—",
                "sku": item.get("sku") or "—",
                "unit_symbol": item.get("unit_symbol") or "—",
                "site_name": self._site_name(sites_index, site_id),
                "source_site_name": self._site_name(sites_index, source_site_id),
                "destination_site_name": self._site_name(sites_index, site_id),
                "qty": self._serialize_decimal(qty),
                "lost_qty": self._serialize_decimal(qty),
                "status": status,
                "document_number": row.get("document_number") or "",
                "created_at": row.get("updated_at") or "",
                "updated_at": row.get("updated_at") or "",
            })

        return result

    _ACTION_LABELS: dict[str, dict[str, str]] = {
        "found_to_destination": {
            "label": "Найдено на складе назначения",
            "description": "Актив найден и добавлен на склад назначения",
        },
        "write_off": {
            "label": "Списать",
            "description": "Окончательное списание актива",
        },
        "return_to_source": {
            "label": "Вернуть на склад-источник",
            "description": "Возврат актива на исходный склад",
        },
    }

    def present_lost_asset_detail(
        self,
        lost_asset: dict[str, Any],
    ) -> dict[str, Any]:
        """Present a single lost asset detail view-model."""
        items_index = self.get_items_index()
        sites_index = self.get_sites_index()

        item_id = self._to_int(lost_asset.get("item_id"))
        item = items_index.get(item_id or -1, {})
        site_id = self._to_int(lost_asset.get("site_id"))
        source_site_id = self._to_int(lost_asset.get("source_site_id"))
        qty = self._to_decimal(lost_asset.get("qty") or lost_asset.get("lost_qty") or 0) or Decimal("0")
        has_source = source_site_id is not None
        status = str(lost_asset.get("status") or "open")

        if status == "resolved":
            available_actions: list[dict[str, str]] = []
        else:
            action_codes = ["found_to_destination", "write_off"]
            if has_source:
                action_codes.append("return_to_source")
            available_actions = [
                {
                    "value": code,
                    "label": self._ACTION_LABELS[code]["label"],
                    "description": self._ACTION_LABELS[code]["description"],
                }
                for code in action_codes
            ]

        return {
            "operation_line_id": lost_asset.get("operation_line_id") or lost_asset.get("id"),
            "operation_id": lost_asset.get("operation_id"),
            "item_id": item_id,
            "item_name": item.get("name") or f"ТМЦ #{item_id}",
            "item_code": item.get("sku") or "—",
            "sku": item.get("sku") or "—",
            "unit_symbol": item.get("unit_symbol") or "—",
            "site_name": self._site_name(sites_index, site_id),
            "source_site_name": self._site_name(sites_index, source_site_id),
            "destination_site_name": self._site_name(sites_index, site_id),
            "qty": self._serialize_decimal(qty),
            "lost_qty": self._serialize_decimal(qty),
            "status": status,
            "document_number": lost_asset.get("document_number") or "",
            "created_at": lost_asset.get("updated_at") or "",
            "updated_at": lost_asset.get("updated_at") or "",
            "available_actions": available_actions,
            "has_source_site": has_source,
        }
