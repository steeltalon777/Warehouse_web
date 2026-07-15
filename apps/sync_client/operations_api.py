"""
Operations API client module for SyncServer operations endpoints.

This module provides high-level methods for interacting with SyncServer
operations API using the base SyncServerClient.

Operations represent inventory movements (receipts, issues, transfers)
and support lifecycle management (draft → submitted → completed/cancelled).

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.operations_api import OperationsAPI

    client = SyncServerClient(user_id="user-123", site_id="site-456")
    operations_api = OperationsAPI(client)

    # List operations with filters
    operations = operations_api.list_operations(filters={
        "status": "draft",
        "item_id": "item-123",
        "site_id": "site-456"
    })

    # Get specific operation
    operation = operations_api.get_operation("op-789")

    # Create new operation
    new_operation = operations_api.create_operation({
        "type": "receipt",
        "item_id": "item-123",
        "quantity": 10,
        "site_id": "site-456",
        "notes": "Initial stock receipt"
    })

    # Update operation
    updated_operation = operations_api.update_operation("op-789", {
        "quantity": 15,
        "notes": "Updated quantity"
    })

    # Submit operation for processing
    operations_api.submit_operation("op-789")

    # Cancel operation
    operations_api.cancel_operation("op-789")
"""

from __future__ import annotations

import structlog
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = structlog.get_logger()


class OperationsAPI:
    """
    High-level client for SyncServer operations API.

    This class provides convenient methods for inventory operation management
    including creation, updating, submission, and cancellation.

    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize OperationsAPI client.

        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("operations_api_initialized")

    def list_operations(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get list of operations with optional filtering.

        Endpoint: GET /operations

        Args:
            filters: Optional filters for operations (e.g., status, item_id, site_id, type)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            extra_headers: Optional extra headers forwarded to SyncServer.
            return_response: When True, return a ``(payload, response_headers)`` tuple.

        Returns:
            list: List of operation dictionaries

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> # Get draft operations
            >>> operations = operations_api.list_operations(filters={"status": "draft"})
            >>> # Get operations for specific item
            >>> operations = operations_api.list_operations(filters={"item_id": "item-123"})
            >>> # Get operations for specific site
            >>> operations = operations_api.list_operations(filters={"site_id": "site-456"})
            >>> # Get operations by type
            >>> operations = operations_api.list_operations(filters={"type": "receipt"})
        """
        logger.debug(
            "fetching_operations_list", filters=filters or {},
        )

        params = self._build_filter_params(filters)
        response = self.client.get(
            "/operations",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        # Handle different response formats
        if return_response:
            data, resp_headers = response
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
            elif isinstance(data, dict) and "operations" in data:
                items = data["operations"]
            elif isinstance(data, list):
                items = data
            else:
                logger.warning(
                    "unexpected_response_format", endpoint="/operations", response_type=type(data).__name__,
                )
                items = []
            return items, resp_headers

        if isinstance(response, dict) and "items" in response:
            return response["items"]
        elif isinstance(response, dict) and "operations" in response:
            return response["operations"]
        elif isinstance(response, list):
            return response
        else:
            logger.warning(
                "unexpected_response_format", endpoint="/operations", response_type=type(response).__name__,
            )
            return []


    def list_operations_page(
        self,
        filters: Optional[dict[str, Any]] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        logger.debug(
            "fetching_operations_page", filters=filters or {},
        )

        params = self._build_filter_params(filters)
        response = self.client.get(
            "/operations",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )

        if return_response:
            data, resp_headers = response
        else:
            data, resp_headers = response, {}

        if isinstance(data, dict):
            if "operations" in data and "items" not in data:
                data = {**data, "items": data.get("operations", [])}
            data.setdefault("items", [])
            data.setdefault("total_count", len(data.get("items", [])))
            data.setdefault("page", params.get("page", 1))
            data.setdefault("page_size", params.get("page_size", len(data.get("items", [])) or 20))
            if return_response:
                return data, resp_headers
            return data

        if isinstance(data, list):
            page_dict = {
                "items": data,
                "total_count": len(data),
                "page": params.get("page", 1),
                "page_size": params.get("page_size", len(data) or 20),
            }
            if return_response:
                return page_dict, resp_headers
            return page_dict

        logger.warning(
            "unexpected_response_format", endpoint="/operations", response_type=type(data).__name__,
        )
        empty = {"items": [], "total_count": 0, "page": 1, "page_size": params.get("page_size", 20)}
        if return_response:
            return empty, resp_headers
        return empty

    def get_operation(
        self,
        operation_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Get specific operation by ID.

        Endpoint: GET /operations/{operation_id}

        Args:
            operation_id: Operation identifier
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            extra_headers: Optional extra headers forwarded to SyncServer.
            return_response: When True, return a ``(payload, response_headers)`` tuple.

        Returns:
            dict: Operation information

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> operation = operations_api.get_operation("op-789")
            >>> print(operation["type"], operation["status"], operation["quantity"])
        """
        logger.debug("fetching_operation", operation_id=operation_id)
        response = self.client.get(
            f"/operations/{operation_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def create_operation(
        self,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Create new inventory operation.

        Endpoint: POST /operations

        Args:
            payload: Operation creation data
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Created operation information

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> new_operation = operations_api.create_operation({
            ...     "type": "receipt",  # or "issue", "transfer", "adjustment"
            ...     "item_id": "item-123",
            ...     "quantity": 10.5,
            ...     "unit_id": "unit-456",
            ...     "site_id": "site-789",
            ...     "target_site_id": "site-999",  # for transfers
            ...     "notes": "Initial stock receipt",
            ...     "status": "draft"
            ... })
            >>> print(new_operation["id"])
        """
        logger.debug(
            "creating_operation", payload_keys=list(payload.keys()),
        )
        response = self.client.post(
            "/operations",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def update_operation(
        self,
        operation_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Update existing operation.

        Endpoint: PATCH /operations/{operation_id}

        Args:
            operation_id: Operation identifier to update
            payload: Operation update data (partial updates supported)
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Updated operation information

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> updated_operation = operations_api.update_operation("op-789", {
            ...     "quantity": 15.0,
            ...     "notes": "Updated quantity after verification",
            ...     "status": "draft"  # keep as draft until submission
            ... })
            >>> print(updated_operation["quantity"])
        """
        logger.debug(
            "updating_operation", operation_id=operation_id, payload_keys=list(payload.keys()),
        )
        response = self.client.patch(
            f"/operations/{operation_id}",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def submit_operation(
        self,
        operation_id: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Submit operation for processing (draft → submitted).

        Endpoint: POST /operations/{operation_id}/submit

        Args:
            operation_id: Operation identifier to submit
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Submitted operation information

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> submitted_operation = operations_api.submit_operation("op-789")
            >>> print(submitted_operation["status"])  # should be "submitted"
        """
        logger.debug("submitting_operation", operation_id=operation_id)
        response = self.client.post(
            f"/operations/{operation_id}/submit",
            json=payload or {"submit": True},
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def cancel_operation(
        self,
        operation_id: str,
        *,
        payload: Optional[dict[str, Any]] = None,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Cancel operation (draft/submitted → cancelled).

        Endpoint: POST /operations/{operation_id}/cancel

        Args:
            operation_id: Operation identifier to cancel
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override

        Returns:
            dict: Cancelled operation information

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> cancelled_operation = operations_api.cancel_operation("op-789")
            >>> print(cancelled_operation["status"])  # should be "cancelled"
        """
        logger.debug("cancelling_operation", operation_id=operation_id)
        response = self.client.post(
            f"/operations/{operation_id}/cancel",
            json=payload or {"cancel": True},
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def restore_operation(
        self,
        operation_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Restore a cancelled operation back to draft status.

        Endpoint: POST /operations/{operation_id}/restore

        Args:
            operation_id: Operation identifier to restore
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            extra_headers: Optional extra headers forwarded to SyncServer.
            return_response: When True, return a ``(payload, response_headers)`` tuple.

        Returns:
            dict: Restored operation information

        Raises:
            SyncServerAPIError: On backend errors (409, 422, 403, etc.).
        """
        logger.debug("restoring_operation", operation_id=operation_id)
        response = self.client.post(
            f"/operations/{operation_id}/restore",
            json={"restore": True},
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    def delete_operation(
        self,
        operation_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> Any:
        """
        Delete a cancelled operation (soft delete).

        Endpoint: DELETE /operations/{operation_id}

        Args:
            operation_id: Operation identifier to delete
            acting_user_id: Optional acting user ID override
            acting_site_id: Optional acting site ID override
            extra_headers: Optional extra headers forwarded to SyncServer.
            return_response: When True, return a ``(payload, response_headers)`` tuple.

        Raises:
            SyncAPIError: If the API request fails

        Example:
            >>> operations_api = OperationsAPI()
            >>> operations_api.delete_operation("op-789")
        """
        logger.debug("deleting_operation", operation_id=operation_id)
        result = self.client.delete(
            f"/operations/{operation_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return result
        return result

    def accept_operation_lines(
        self,
        operation_id: str,
        payload: dict[str, Any],
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
        extra_headers: Optional[dict[str, str]] = None,
        return_response: bool = False,
    ) -> dict[str, Any]:
        """
        Submit acceptance for operation lines.

        Endpoint: POST /api/v1/operations/{operation_id}/accept-lines

        Args:
            operation_id: Operation identifier.
            payload: Acceptance payload with keys:
                - lines (list[dict]): each line has line_number, accepted_qty, lost_qty, note.
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.
            extra_headers: Optional extra headers forwarded to SyncServer.
            return_response: When True, return a ``(payload, response_headers)`` tuple.

        Returns:
            Updated operation dict with acceptance state.

        Raises:
            SyncServerAPIError: On backend errors (409, 422, 403, etc.).
        """
        logger.debug("accepting_operation_lines", operation_id=operation_id)
        response = self.client.post(
            f"/operations/{operation_id}/accept-lines",
            json=payload,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
            extra_headers=extra_headers,
            return_response=return_response,
        )
        if return_response:
            return response
        return response

    # ---------- HELPER METHODS ----------

    def _build_filter_params(self, filters: Optional[dict[str, Any]]) -> dict[str, Any]:
        """
        Build query parameters from filters dictionary.

        Args:
            filters: Dictionary of filter criteria

        Returns:
            dict: Query parameters for HTTP request
        """
        if not filters:
            return {}

        params = {}
        for key, value in filters.items():
            if value is not None:
                params[key] = value

        return params


# Convenience function for quick usage
def get_operations_api(client: Optional[SyncServerClient] = None) -> OperationsAPI:
    """
    Get an OperationsAPI instance.

    Args:
        client: Optional SyncServerClient instance

    Returns:
        OperationsAPI instance
    """
    return OperationsAPI(client=client)
