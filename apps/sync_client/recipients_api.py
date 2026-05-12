from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient

logger = logging.getLogger(__name__)


class RecipientsAPI:
    """
    High-level client for SyncServer recipient reference endpoints.
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        self.client = client or SyncServerClient()

    def list_recipients(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /recipients
        """
        params = self._build_filter_params(filters)
        response = self.client.get(
            "/recipients",
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
            "Unexpected response format from /recipients",
            extra={"response_type": type(response).__name__},
        )
        return {
            "items": [],
            "total_count": 0,
            "page": params.get("page", 1),
            "page_size": params.get("page_size", 100),
        }

    def create_recipient(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: POST /recipients
        """
        return self.client.post(
            "/recipients",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def merge_recipients(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: POST /recipients/merge
        """
        return self.client.post(
            "/recipients/merge",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def get_recipient(
        self,
        recipient_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: GET /recipients/{recipient_id}
        """
        return self.client.get(
            f"/recipients/{recipient_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def update_recipient(
        self,
        recipient_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Endpoint: PATCH /recipients/{recipient_id}
        """
        return self.client.patch(
            f"/recipients/{recipient_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def delete_recipient(
        self,
        recipient_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> Any:
        """
        Endpoint: DELETE /recipients/{recipient_id}
        """
        return self.client.delete(
            f"/recipients/{recipient_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def _build_filter_params(self, filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not filters:
            return {}
        return {key: value for key, value in filters.items() if value is not None}


def get_recipients_api(client: Optional[SyncServerClient] = None) -> RecipientsAPI:
    return RecipientsAPI(client=client)
