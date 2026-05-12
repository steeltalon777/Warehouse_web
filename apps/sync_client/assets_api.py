"""
Assets API client for SyncServer asset-register endpoints.

Provides high-level methods for:
- Pending acceptance list (line-level)
- Lost assets list / detail / resolve
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient

logger = logging.getLogger(__name__)

SAFEGUARD_MAX_PAGES = 50
SAFEGUARD_MAX_ROWS = 10_000


class AssetsAPI:
    """
    High-level client for SyncServer asset-register endpoints.

    Attributes:
        client (SyncServerClient): Underlying HTTP client instance.
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        self.client = client or SyncServerClient()
        logger.debug("AssetsAPI client initialized")

    # ------------------------------------------------------------------
    # Pending acceptance
    # ------------------------------------------------------------------

    def list_pending_acceptance(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a page of pending-acceptance lines.

        Endpoint: GET /api/v1/pending-acceptance

        Args:
            filters: Optional filters (page, page_size, search, site_id, operation_id, …)
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.

        Returns:
            Normalised dict with keys: items, total_count, page, page_size.
        """
        params = self._build_params(filters)
        response = self.client.get(
            "/pending-acceptance",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        return self._normalize_list_response(response, params)

    def list_pending_acceptance_all_pages(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        max_pages: int = SAFEGUARD_MAX_PAGES,
        max_rows: int = SAFEGUARD_MAX_ROWS,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Iterate over all pages of pending-acceptance and collect full result set.

        Safeguards:
        - Stops after ``max_pages`` pages.
        - Stops after ``max_rows`` rows.
        - Logs a warning if either limit is hit; does NOT raise.

        Returns:
            Normalised dict with keys: items, total_count, page (1), page_size (total),
            and ``truncated`` (bool) if safeguard was triggered.
        """
        page = 1
        all_items: list[dict[str, Any]] = []
        base_filters = dict(filters or {})

        while page <= max_pages and len(all_items) < max_rows:
            base_filters["page"] = page
            base_filters["page_size"] = min(100, max_rows - len(all_items))
            result = self.list_pending_acceptance(
                filters=base_filters,
                acting_user_id=acting_user_id,
                acting_site_id=acting_site_id,
            )
            items = result.get("items", [])
            if not items:
                break
            all_items.extend(items)
            total_count = int(result.get("total_count") or 0)
            if len(all_items) >= total_count:
                break
            page += 1

        truncated = False
        if page > max_pages or len(all_items) >= max_rows:
            truncated = True
            logger.warning(
                "Pending acceptance all-pages fetch hit safeguard limit",
                extra={"pages_fetched": page, "rows_collected": len(all_items)},
            )

        return {
            "items": all_items,
            "total_count": len(all_items),
            "page": 1,
            "page_size": len(all_items),
            "truncated": truncated,
        }

    # ------------------------------------------------------------------
    # Lost assets
    # ------------------------------------------------------------------

    def list_lost_assets(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a page of lost assets.

        Endpoint: GET /api/v1/lost-assets

        Args:
            filters: Optional filters (page, page_size, search, site_id, …)
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.

        Returns:
            Normalised dict with keys: items, total_count, page, page_size.
        """
        params = self._build_params(filters)
        response = self.client.get(
            "/lost-assets",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        return self._normalize_list_response(response, params)

    def get_lost_asset(
        self,
        operation_line_id: str | int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a single lost asset record by operation line ID.

        Endpoint: GET /api/v1/lost-assets/{operation_line_id}

        Returns:
            Lost asset detail dict.
        """
        logger.debug("Fetching lost asset", extra={"operation_line_id": operation_line_id})
        return self.client.get(
            f"/lost-assets/{operation_line_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def resolve_lost_asset(
        self,
        operation_line_id: str | int,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Resolve a lost asset.

        Endpoint: POST /api/v1/lost-assets/{operation_line_id}/resolve

        Args:
            operation_line_id: Operation line identifier.
            payload: Resolve payload with keys:
                - action (str): found_to_destination | return_to_source | write_off
                - qty (str): decimal quantity to resolve
                - note (str, optional): comment
                - responsible_recipient_id (int, optional): for found_to_destination

        Returns:
            Resolved asset detail dict.
        """
        logger.debug("Resolving lost asset", extra={"operation_line_id": operation_line_id, "action": payload.get("action")})
        return self.client.post(
            f"/lost-assets/{operation_line_id}/resolve",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_params(filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not filters:
            return {}
        return {key: value for key, value in filters.items() if value is not None and value != ""}

    @staticmethod
    def _normalize_list_response(response: Any, params: dict[str, Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            if "items" in response:
                response.setdefault("total_count", len(response.get("items", [])))
                response.setdefault("page", params.get("page", 1))
                response.setdefault("page_size", params.get("page_size", len(response.get("items", [])) or 20))
                return response
            if "lines" in response:
                lines = response["lines"]
                return {
                    "items": lines if isinstance(lines, list) else [],
                    "total_count": len(lines) if isinstance(lines, list) else 0,
                    "page": params.get("page", 1),
                    "page_size": params.get("page_size", len(lines) if isinstance(lines, list) else 20),
                }
            if "results" in response:
                results = response["results"]
                return {
                    "items": results if isinstance(results, list) else [],
                    "total_count": int(response.get("count", len(results if isinstance(results, list) else []))),
                    "page": params.get("page", 1),
                    "page_size": params.get("page_size", len(results if isinstance(results, list) else []) or 20),
                }
        if isinstance(response, list):
            return {
                "items": response,
                "total_count": len(response),
                "page": params.get("page", 1),
                "page_size": params.get("page_size", len(response) or 20),
            }

        logger.warning(
            "Unexpected list response format",
            extra={"response_type": type(response).__name__},
        )
        return {"items": [], "total_count": 0, "page": 1, "page_size": 20}


def get_assets_api(client: Optional[SyncServerClient] = None) -> AssetsAPI:
    """Convenience factory for AssetsAPI."""
    return AssetsAPI(client=client)
