"""
Documents API client module for SyncServer document endpoints.

This module provides high-level methods for interacting with SyncServer
documents API using the base SyncServerClient.

Documents are stored on SyncServer as metadata + JSONB payload (not as
PDF/DOCX files). The Django client is responsible for client-side DOCX→PDF
rendering using local templates and LibreOffice.

Usage:
    from apps.sync_client.client import SyncServerClient
    from apps.sync_client.documents_api import DocumentsAPI

    client = SyncServerClient(user_id="user-123", site_id="site-456")
    docs_api = DocumentsAPI(client)

    # Get a single document
    document = docs_api.get_document("doc-uuid")

    # List documents for an operation
    documents = docs_api.list_operation_documents("op-uuid", document_type="waybill")

    # Generate a new document for an operation
    result = docs_api.generate_operation_document("op-uuid", document_type="waybill")
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import SyncServerClient
from .exceptions import SyncServerAPIError

logger = logging.getLogger(__name__)


class DocumentsAPI:
    """
    High-level client for SyncServer documents API.

    Provides methods to retrieve, list, and generate documents.
    Documents are metadata + JSONB payload; actual PDF rendering
    happens client-side in the Django app.

    Attributes:
        client (SyncServerClient): Underlying HTTP client instance
    """

    def __init__(self, client: Optional[SyncServerClient] = None) -> None:
        """
        Initialize DocumentsAPI client.

        Args:
            client: Optional SyncServerClient instance. If not provided,
                   a new instance will be created with default settings.
        """
        self.client = client or SyncServerClient()
        logger.debug("DocumentsAPI client initialized")

    def get_document(
        self,
        document_id: str,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Get a single document by ID.

        Endpoint: GET /documents/{document_id}

        Args:
            document_id: Document UUID identifier.
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.

        Returns:
            dict: Document information including id, document_type,
                  document_number, status, template_name, payload, etc.

        Raises:
            SyncServerAPIError: If the API request fails (404, 403, etc.).
        """
        logger.debug("Fetching document", extra={"document_id": document_id})
        return self.client.get(
            f"/documents/{document_id}",
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

    def list_operation_documents(
        self,
        operation_id: str,
        document_type: Optional[str] = None,
        *,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List documents attached to a specific operation.

        Endpoint: GET /documents/operations/{operation_id}/documents

        Args:
            operation_id: Operation UUID identifier.
            document_type: Optional filter by document type (e.g. "waybill").
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.

        Returns:
            list[dict]: List of document dictionaries.

        Raises:
            SyncServerAPIError: If the API request fails.
        """
        logger.debug(
            "Fetching documents for operation",
            extra={"operation_id": operation_id, "document_type": document_type},
        )

        params: dict[str, Any] = {}
        if document_type:
            params["document_type"] = document_type

        response = self.client.get(
            f"/documents/operations/{operation_id}/documents",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )

        # Handle different response formats
        if isinstance(response, list):
            return response
        if isinstance(response, dict) and "items" in response:
            return response["items"]

        logger.warning(
            "Unexpected response format from /documents/operations/{operation_id}/documents",
            extra={"response_type": type(response).__name__},
        )
        return []

    def generate_operation_document(
        self,
        operation_id: str,
        document_type: str = "waybill",
        template_name: Optional[str] = None,
        *,
        auto_finalize: bool = False,
        language: str = "ru",
        basis_type: Optional[str] = None,
        basis_number: Optional[str] = None,
        basis_date: Optional[str] = None,
        acting_user_id: str | int | None = None,
        acting_site_id: str | int | None = None,
    ) -> dict[str, Any]:
        """
        Generate a new document for an operation on SyncServer.

        Endpoint: POST /documents/operations/{operation_id}/documents

        This creates a document record with metadata + JSONB payload on
        SyncServer. The actual DOCX→PDF rendering is done client-side.

        Args:
            operation_id: Operation UUID identifier.
            document_type: Document type (default "waybill").
            template_name: Optional template name override.
            auto_finalize: Automatically finalize the document on SyncServer.
            language: Document language code (default "ru").
            basis_type: Optional basis document type.
            basis_number: Optional basis document number.
            basis_date: Optional basis document date (ISO format).
            acting_user_id: Optional acting user ID override.
            acting_site_id: Optional acting site ID override.

        Returns:
            dict: Response with keys "document", "operation_id", "generated_at".

        Raises:
            SyncServerAPIError: If the API request fails.
        """
        logger.debug(
            "Generating document for operation",
            extra={
                "operation_id": operation_id,
                "document_type": document_type,
                "template_name": template_name,
            },
        )

        params: dict[str, Any] = {
            "document_type": document_type,
            "auto_finalize": str(auto_finalize).lower(),
            "language": language,
        }
        if template_name:
            params["template_name"] = template_name
        if basis_type:
            params["basis_type"] = basis_type
        if basis_number:
            params["basis_number"] = basis_number
        if basis_date:
            params["basis_date"] = basis_date

        return self.client.post(
            f"/documents/operations/{operation_id}/documents",
            params=params,
            acting_user_id=acting_user_id,
            acting_site_id=acting_site_id,
        )


# Convenience function for quick usage
def get_documents_api(client: Optional[SyncServerClient] = None) -> DocumentsAPI:
    """
    Get a DocumentsAPI instance.

    Args:
        client: Optional SyncServerClient instance.

    Returns:
        DocumentsAPI instance.
    """
    return DocumentsAPI(client=client)
