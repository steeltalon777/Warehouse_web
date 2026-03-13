from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceResult:
    ok: bool
    data: Any = None
    form_error: str | None = None
    not_found: bool = False
    server_unavailable: bool = False


class SyncUsersService:
    """
    DEPRECATED.

    Legacy users/roles/sites integration relied on old SyncServer endpoints:
    - /users
    - /roles
    - /sites

    These routes are not part of the current canonical API contract for Warehouse_web.
    Use apps.sync_client.admin_api.AdminAPI instead.
    """

    def __init__(self) -> None:
        raise RuntimeError(
            "apps.integration.users_service is deprecated. "
            "Use apps.sync_client.admin_api.AdminAPI and current /api/v1/admin/* endpoints."
        )