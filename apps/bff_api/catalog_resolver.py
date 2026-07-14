"""
BFF catalog read helpers (TZ-V3.2 stage C4).

The BFF layer holds one service:

- :func:`resolve_items` — user-context batch resolver for catalog item IDs.
  Uses the SyncServer read endpoint added in Stage A
  (``/catalog/read/items/resolve``). Caller tokens never leak to the browser
  via HTTP; the BFF performs the privileged request on behalf of the user.
"""
from __future__ import annotations

from typing import Any

import structlog

from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError

logger = structlog.get_logger()


def resolve_items(
    client: SyncServerClient,
    item_ids: list[str | int],
) -> list[dict[str, Any]]:
    """Resolve a batch of item IDs through the authoritative SyncServer endpoint.

    Returns one dict per requested ID, preserving input order. Each result
    carries the fields documented in TZ §4.3:

    - ``request_id`` (echo of the input)
    - ``status`` — one of ``active``, ``merged``, ``inactive``, ``deleted``, ``missing``
    - ``canonical_item_id`` — present when ``status == "merged"``
    - ``item`` — present when ``status in {"active", "merged"}`` and the canonical
      row exists; contains the read-model payload from SyncServer

    Errors propagate as :class:`SyncServerAPIError` so callers can return the
    structured failure to the browser via :func:`apps.bff_api.helpers._handle_sync_error`.
    """
    if not item_ids:
        return []

    payload = {"item_ids": [str(i) for i in item_ids]}
    response = client.post("/catalog/read/items/resolve", json=payload)
    if isinstance(response, dict):
        results = response.get("results")
        if isinstance(results, list):
            return results
    logger.warning(
        "catalog_resolver_unexpected_payload",
        payload_type=type(response).__name__,
        exc_info=True,
    )
    raise SyncServerAPIError(
        "Catalog resolver returned unexpected payload",
        status_code=502,
        method="POST",
        path="/catalog/read/items/resolve",
    )
