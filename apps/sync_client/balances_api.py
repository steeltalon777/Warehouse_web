"""
Balances API client for SyncServer v2 balances endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient

logger = logging.getLogger(__name__)


class BalancesAPI:
    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        self.client = client or SyncServerClient()
        logger.debug("BalancesAPI client initialized")

    def list_balances(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        page: int = 1,
        page_size: int = 100,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        params = self._build_filter_params(filters)
        params["page"] = page
        params["page_size"] = page_size

        response = self.client.get(
            "/balances",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        return self._normalize_list_response(response)

    def by_site(
        self,
        *,
        site_id: str | int,
        only_positive: bool = False,
        page: int = 1,
        page_size: int = 100,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        params = {
            "site_id": site_id,
            "only_positive": only_positive,
            "page": page,
            "page_size": page_size,
        }
        response = self.client.get(
            "/balances/by-site",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        return self._normalize_list_response(response)

    def get_balances_summary(
        self,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        response = self.client.get(
            "/balances/summary",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        return response if isinstance(response, dict) else {}

    def get_balances_by_item(
        self,
        item_id: str | int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/balances/items/{item_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )
        if isinstance(response, dict) and "items" in response:
            return response["items"]
        if isinstance(response, dict) and "balances" in response:
            return response["balances"]
        if isinstance(response, list):
            return response
        logger.warning(
            "Unexpected response format from balances by item",
            extra={"response_type": type(response).__name__},
        )
        return []

    @staticmethod
    def _build_filter_params(filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not filters:
            return {}
        return {key: value for key, value in filters.items() if value is not None and value != ""}

    @staticmethod
    def _normalize_list_response(response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            if "items" in response:
                return response
            if "balances" in response:
                balances = response["balances"]
                return {
                    "items": balances if isinstance(balances, list) else [],
                    "total_count": len(balances) if isinstance(balances, list) else 0,
                    "page": response.get("page", 1),
                    "page_size": response.get("page_size", len(balances) if isinstance(balances, list) else 0),
                }
        if isinstance(response, list):
            return {
                "items": response,
                "total_count": len(response),
                "page": 1,
                "page_size": len(response),
            }
        logger.warning(
            "Unexpected balances list response format",
            extra={"response_type": type(response).__name__},
        )
        return {"items": [], "total_count": 0, "page": 1, "page_size": 0}


def get_balances_api(client: Optional[SyncServerClient] = None) -> BalancesAPI:
    return BalancesAPI(client=client)
