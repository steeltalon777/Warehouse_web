"""
Operation enrichment module for BFF endpoints.

Enriches raw SyncServer operation responses with display fields
needed by the Angular frontend:
- display_number (format: {ddMMyy}/{HHmm}/{site_id})
- site_name, source_site_name, destination_site_name
- created_by_label (FIO/username from local Django users)
- lines_count
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from django.contrib.auth import get_user_model

from apps.sync_client.client import SyncServerClient

logger = structlog.get_logger()


def _compute_display_number(site_id: int | None, created_at: str | None) -> str | None:
    """
    Compute display operation number in format: {ddMMyy}/{HHmm}/{site_id}

    Example: site_id=5, created_at=2026-06-02T08:38:43Z => "020626/0838/5"
    Returns None if site_id or created_at is missing or unparseable.
    """
    if site_id is None or not created_at:
        return None
    try:
        dt_str = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        return f"{dt.strftime('%d%m%y')}/{dt.strftime('%H%M')}/{site_id}"
    except (ValueError, TypeError) as exc:
        logger.warning("compute_display_number_failed", site_id=site_id, created_at=created_at, error=str(exc))
        return None


def _get_sites_index(request) -> dict[int, dict[str, Any]]:
    """
    Build sites index from SyncServer catalog/sites endpoint.

    Returns mapping: site_id -> {name, code}
    Uses root client for full access.
    """
    try:
        root_client = SyncServerClient(request=request, force_root=True)
        response = root_client.get("/catalog/sites")
        sites = response.get("sites", []) if isinstance(response, dict) else []
        index: dict[int, dict[str, Any]] = {}
        for site in sites:
            try:
                site_id = int(site.get("site_id"))
            except (TypeError, ValueError):
                continue
            index[site_id] = {
                "name": str(site.get("name") or site.get("code") or site_id),
                "code": str(site.get("code") or ""),
            }
        return index
    except Exception as exc:
        logger.warning("load_sites_index_failed", error=str(exc))
        return {}


def _get_user_labels(request, user_ids: list[Any]) -> dict[str, str]:
    """
    Build user labels from local Django User model.

    Returns mapping: syncserver_user_id -> display name (FIO or username)
    """
    normalized_ids = {str(uid) for uid in user_ids if uid}
    if not normalized_ids:
        return {}

    try:
        User = get_user_model()
        rows = list(
            User.objects.filter(
                sync_binding__syncserver_user_id__in=normalized_ids
            ).values(
                "sync_binding__syncserver_user_id",
                "first_name",
                "last_name",
                "username",
            )
        )
    except Exception:
        logger.error("resolve_operation_authors_failed", exc_info=True)
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


def enrich_operation(
    operation: dict[str, Any],
    sites_index: dict[int, dict[str, Any]],
    user_labels: dict[str, str],
) -> dict[str, Any]:
    """
    Enrich a raw SyncServer operation dict with display fields.

    Preserves all original fields; only adds/overrides display fields.
    """
    site_id = _to_int(operation.get("site_id"))
    source_site_id = _to_int(operation.get("source_site_id"))
    destination_site_id = _to_int(operation.get("destination_site_id") or operation.get("target_site_id"))
    created_by_user_id = operation.get("created_by_user_id")

    created_at = operation.get("created_at")

    display_number = operation.get("display_number") or _compute_display_number(site_id, created_at)
    lines = operation.get("lines", [])
    lines_count = operation.get("lines_count") or len(lines) if isinstance(lines, list) else 0
    operation_type = operation.get("operation_type", "")
    acceptance_state = operation.get("acceptance_state", "not_required")
    acceptance_state_labels = {
        "not_required": "Не требуется",
        "pending": "Приёмка: ожидает",
        "in_progress": "Приёмка: частично",
        "resolved": "Приёмка: закрыта",
    }

    return {
        **operation,
        "type": operation_type,
        "display_number": display_number or operation.get("number"),
        "number": display_number or operation.get("number"),
        "site_name": _site_name(sites_index, site_id),
        "source_site_name": _site_name(sites_index, source_site_id),
        "destination_site_name": _site_name(sites_index, destination_site_id),
        "created_by_label": user_labels.get(str(created_by_user_id), "")
        or str(created_by_user_id),
        "lines_count": lines_count,
        "acceptance_state_label": acceptance_state_labels.get(
            acceptance_state, acceptance_state
        ),
    }


def _site_name(sites_index: dict[int, dict[str, Any]], site_id: int | None) -> str:
    if site_id is None:
        return ""
    site = sites_index.get(site_id)
    if not site:
        return str(site_id)
    return str(site.get("name") or site.get("code") or site_id)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
