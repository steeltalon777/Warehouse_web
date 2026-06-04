from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient

logger = logging.getLogger(__name__)


class IssueObjectsAPI:
    """
    High-level client for SyncServer issue-object reference endpoints.
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        self.client = client or SyncServerClient()

    def list_issue_objects(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /issue-objects
        """
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/issue-objects",
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
            "Unexpected response format from /issue-objects",
            extra={"response_type": type(response).__name__},
        )
        return {
            "items": [],
            "total_count": 0,
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 100),
        }

    def create_issue_object(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: POST /issue-objects
        """
        return self.client.post(
            "/issue-objects",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def merge_issue_objects(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: POST /issue-objects/merge
        """
        return self.client.post(
            "/issue-objects/merge",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def get_issue_object(
        self,
        issue_object_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /issue-objects/{issue_object_id}
        """
        return self.client.get(
            f"/issue-objects/{issue_object_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def update_issue_object(
        self,
        issue_object_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: PATCH /issue-objects/{issue_object_id}
        """
        return self.client.patch(
            f"/issue-objects/{issue_object_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def delete_issue_object(
        self,
        issue_object_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> Any:
        """
        Endpoint: DELETE /issue-objects/{issue_object_id}
        """
        return self.client.delete(
            f"/issue-objects/{issue_object_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def list_object_assets(
        self,
        issue_object_id: str,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /issue-objects/{issue_object_id}/assets
        """
        params = self._build_filter_params(filters)
        response = self.client.get(
            f"/issue-objects/{issue_object_id}/assets",
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
            "Unexpected response format from /issue-objects/{id}/assets",
            extra={"response_type": type(response).__name__},
        )
        return {
            "items": [],
            "total_count": 0,
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 100),
        }

    def get_tree(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Endpoint: GET /issue-objects/tree
        """
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/issue-objects/tree",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        if isinstance(response, list):
            return response

        logger.warning(
            "Unexpected response format from /issue-objects/tree",
            extra={"response_type": type(response).__name__},
        )
        return []

    def _build_filter_params(self, filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not filters:
            return {}
        return {key: value for key, value in filters.items() if value is not None}


def get_issue_objects_api(client: Optional[SyncServerClient] = None) -> IssueObjectsAPI:
    return IssueObjectsAPI(client=client)
