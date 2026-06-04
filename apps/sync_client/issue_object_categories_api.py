from __future__ import annotations

import structlog
from typing import Any, Optional

from .client import SyncServerClient

logger = structlog.get_logger()


class IssueObjectCategoriesAPI:
    """
    High-level client for SyncServer issue-object-categories endpoints.
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        self.client = client or SyncServerClient()

    def list_categories(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /issue-object-categories
        """
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/issue-object-categories",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        if isinstance(response, dict):
            response.setdefault("items", [])
            response.setdefault("total_count", len(response.get("items", [])))
            response.setdefault("page", params.get("page", 1))
            response.setdefault("page_size", params.get("page_size", len(response.get("items", [])) or 100))
            return response

        if isinstance(response, list):
            return {
                "items": response,
                "total_count": len(response),
                "page": params.get("page", 1),
                "page_size": params.get("page_size", len(response) or 100),
            }

        logger.warning(
            "unexpected_response_format", endpoint="/issue-object-categories", response_type=type(response).__name__,
        )
        return {
            "items": [],
            "total_count": 0,
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 100),
        }

    def create_category(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: POST /issue-object-categories
        """
        return self.client.post(
            "/issue-object-categories",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def get_category(
        self,
        category_id: int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /issue-object-categories/{category_id}
        """
        return self.client.get(
            f"/issue-object-categories/{category_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def update_category(
        self,
        category_id: int,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: PATCH /issue-object-categories/{category_id}
        """
        return self.client.patch(
            f"/issue-object-categories/{category_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def delete_category(
        self,
        category_id: int,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> None:
        """
        Endpoint: DELETE /issue-object-categories/{category_id}
        """
        return self.client.delete(
            f"/issue-object-categories/{category_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def _build_filter_params(self, filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not filters:
            return {}
        return {key: value for key, value in filters.items() if value is not None}


def get_issue_object_categories_api(client: Optional[SyncServerClient] = None) -> IssueObjectCategoriesAPI:
    return IssueObjectCategoriesAPI(client=client)
