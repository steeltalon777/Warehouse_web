from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.root_admin_client import SyncServerRootAdminClient
from apps.users.models import Role, Site, SyncDeviceBinding, SyncStatus, SyncUserBinding

User = get_user_model()


def _sanitized_payload(payload: dict) -> dict:
    from apps.sync_client.redaction import sanitize_payload

    if not payload:
        return payload
    return sanitize_payload(payload)


ROLE_SCOPE_MAP: dict[str, dict[str, bool]] = {
    Role.CHIEF_STOREKEEPER: {
        "can_view": True,
        "can_operate": True,
        "can_manage_catalog": True,
    },
    Role.STOREKEEPER: {
        "can_view": True,
        "can_operate": True,
        "can_manage_catalog": False,
    },
    Role.OBSERVER: {
        "can_view": True,
        "can_operate": False,
        "can_manage_catalog": False,
    },
    # TZ-AGENT_ROLE_ADMIN_UI §3.3.C: agent is scope-independent (ADR-0030
    # §4.3, TZ-AGENT-ROLE-SYNCSERVER §4.3). The mapping keeps a placeholder
    # permissions dict for consistency, but real scopes for agent are sent
    # as an empty list (see build_scopes below and SyncServer PUT
    # `/admin/users/{id}/scopes` accepting `{"scopes": []}`).
    Role.AGENT: {
        "can_view": True,
        "can_operate": False,
        "can_manage_catalog": True,
    },
}


@dataclass
class SyncPreparedState:
    syncserver_user_id: UUID
    sync_user_payload: dict[str, Any]
    scopes_payload: dict[str, Any]
    sync_user_response: dict[str, Any]
    sync_state_response: dict[str, Any]


class UserSyncService:
    def __init__(self, client: SyncServerRootAdminClient | None = None) -> None:
        self.client = client or SyncServerRootAdminClient()

    def list_sites(self) -> list[dict[str, Any]]:
        response = self.client.get("/admin/sites", params={"page": 1, "page_size": 200})
        return response.get("sites", []) if isinstance(response, dict) else []

    def build_scopes(self, role: str, site_ids: list[str]) -> list[dict[str, Any]]:
        # TZ-AGENT_ROLE_ADMIN_UI §3.3.C: empty site_ids produce empty scopes.
        # SyncServer PUT `/admin/users/{id}/scopes` accepts `{"scopes": []}`
        # (verified during TZ-AGENT-ROLE-SYNCSERVER rev.2).
        if not site_ids:
            return []
        permissions = ROLE_SCOPE_MAP[role]
        return [
            {
                "site_id": self._normalize_site_id(site_id),
                **permissions,
            }
            for site_id in site_ids
        ]

    def prepare_sync(
        self,
        *,
        user: User,
        full_name: str,
        role: str,
        site_ids: list[str],
        default_site_id: str,
        syncserver_user_id: UUID | None = None,
    ) -> SyncPreparedState:
        sync_id = syncserver_user_id or uuid4()
        sync_user_payload = {
            "id": str(sync_id),
            "username": user.username,
            "email": user.email,
            "full_name": full_name,
            "is_active": user.is_active,
            "is_root": False,
            "role": role,
            # TZ-AGENT_ROLE_ADMIN_UI §3.3.C: agent sends `default_site_id=null`.
            # _normalize_site_id(None) returns str(None)=="None" which is wrong;
            # we short-circuit when the value is missing.
            "default_site_id": (
                self._normalize_site_id(default_site_id) if default_site_id else None
            ),
        }
        scopes_payload = {
            "scopes": self.build_scopes(role, site_ids),
        }

        sync_user_response = self.client.post("/auth/sync-user", json=sync_user_payload)
        self.client.put(f"/admin/users/{sync_id}/scopes", json=scopes_payload)
        sync_state_response = self.client.get(f"/admin/users/{sync_id}/sync-state")

        return SyncPreparedState(
            syncserver_user_id=sync_id,
            sync_user_payload=sync_user_payload,
            scopes_payload=scopes_payload,
            sync_user_response=sync_user_response,
            sync_state_response=sync_state_response,
        )

    def rotate_token(self, syncserver_user_id: UUID) -> dict[str, Any]:
        return self.client.post(f"/admin/users/{syncserver_user_id}/rotate-token")

    def fetch_sync_state(self, syncserver_user_id: UUID) -> dict[str, Any]:
        return self.client.get(f"/admin/users/{syncserver_user_id}/sync-state")

    def apply_prepared_state(
        self,
        *,
        user: User,
        binding: SyncUserBinding,
        prepared: SyncPreparedState,
        role: str,
        site_ids: list[str],
        default_site_id: str,
    ) -> SyncUserBinding:
        remote_user = prepared.sync_state_response.get("user") or prepared.sync_user_response.get("user") or {}
        scopes = prepared.sync_state_response.get("scopes", [])

        binding.syncserver_user_id = prepared.syncserver_user_id
        binding.sync_user_token = str(remote_user.get("user_token", binding.sync_user_token or ""))
        binding.sync_role = role
        binding.default_site_id = str(remote_user.get("default_site_id", default_site_id))
        binding.site_ids = [str(scope.get("site_id")) for scope in scopes] or site_ids
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(
            prepared.sync_state_response or prepared.sync_user_response
        )
        binding.save()
        return binding

    def sync_user_to_remote(
        self,
        *,
        user: User,
        binding: SyncUserBinding,
        full_name: str,
        role: str,
        site_ids: list[str],
        default_site_id: str,
    ) -> SyncUserBinding:
        """Full remote sync after local commit. Idempotent — uses stable UUID."""
        sync_id = binding.syncserver_user_id
        if not sync_id:
            raise ValueError("Binding has no SyncServer user ID for sync.")

        sync_user_payload = {
            "id": str(sync_id),
            "username": user.username,
            "email": user.email,
            "full_name": full_name,
            "is_active": user.is_active,
            "is_root": False,
            "role": role,
            # TZ-AGENT_ROLE_ADMIN_UI §3.3.C: agent sends `default_site_id=null`.
            "default_site_id": (
                self._normalize_site_id(default_site_id) if default_site_id else None
            ),
        }
        sync_user_response = self.client.post("/auth/sync-user", json=sync_user_payload)

        scopes_payload = {"scopes": self.build_scopes(role, site_ids)}
        self.client.put(f"/admin/users/{sync_id}/scopes", json=scopes_payload)

        sync_state_response = self.client.get(f"/admin/users/{sync_id}/sync-state")

        remote_user = sync_state_response.get("user") or sync_user_response.get("user") or {}
        scopes = sync_state_response.get("scopes", [])

        if not remote_user.get("user_token"):
            raise SyncServerAPIError(
                "SyncServer response missing user_token",
                status_code=200,
                payload=sync_state_response,
            )

        binding.syncserver_user_id = sync_id
        binding.sync_user_token = str(remote_user.get("user_token", binding.sync_user_token or ""))
        binding.sync_role = role
        binding.default_site_id = str(remote_user.get("default_site_id", default_site_id))
        binding.site_ids = [str(scope.get("site_id")) for scope in scopes] or site_ids
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(sync_state_response)
        binding.save()
        return binding

    def sync_existing_binding(self, *, user: User, binding: SyncUserBinding) -> SyncUserBinding:
        prepared = self.prepare_sync(
            user=user,
            full_name=user.first_name,
            role=binding.sync_role,
            site_ids=[str(site_id) for site_id in binding.site_ids],
            default_site_id=binding.default_site_id,
            syncserver_user_id=binding.syncserver_user_id,
        )
        return self.apply_prepared_state(
            user=user,
            binding=binding,
            prepared=prepared,
            role=binding.sync_role,
            site_ids=[str(site_id) for site_id in binding.site_ids],
            default_site_id=binding.default_site_id,
        )

    def repair_binding_from_remote(self, *, user: User, binding: SyncUserBinding) -> SyncUserBinding:
        if not binding.syncserver_user_id:
            raise ValueError("Binding has no SyncServer user id for repair.")

        sync_state = self.fetch_sync_state(binding.syncserver_user_id)
        remote_user = sync_state.get("user", {})
        scopes = sync_state.get("scopes", [])

        user.username = str(remote_user.get("username", user.username))
        user.email = str(remote_user.get("email", user.email or ""))
        user.first_name = str(remote_user.get("full_name", user.first_name or ""))
        user.is_active = bool(remote_user.get("is_active", user.is_active))
        user.save(update_fields=["username", "email", "first_name", "is_active"])

        binding.sync_user_token = str(remote_user.get("user_token", binding.sync_user_token or ""))
        binding.sync_role = str(remote_user.get("role", binding.sync_role))
        binding.default_site_id = str(remote_user.get("default_site_id", binding.default_site_id or ""))
        binding.site_ids = [str(scope.get("site_id")) for scope in scopes]
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(sync_state)
        binding.save()
        return binding

    def mark_failure(
        self,
        *,
        binding: SyncUserBinding,
        error: Exception,
        payload: dict[str, Any] | None = None,
        status: str = SyncStatus.SYNC_FAILED,
    ) -> SyncUserBinding:
        binding.sync_status = status
        binding.last_sync_error = str(error)
        binding.last_sync_at = timezone.now()
        if payload is not None:
            binding.last_sync_payload = _sanitized_payload(payload)
        binding.save(update_fields=[
            "sync_status",
            "last_sync_error",
            "last_sync_at",
            "last_sync_payload",
            "updated_at",
        ])
        return binding

    def apply_rotated_token(self, *, binding: SyncUserBinding, rotate_response: dict[str, Any]) -> SyncUserBinding:
        binding.sync_user_token = str(rotate_response.get("user_token", binding.sync_user_token))
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.token_rotated_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(rotate_response)
        binding.save(update_fields=[
            "sync_user_token",
            "sync_status",
            "last_sync_error",
            "last_sync_at",
            "token_rotated_at",
            "last_sync_payload",
            "updated_at",
        ])
        return binding

    @staticmethod
    def _normalize_site_id(site_id: str) -> int | str:
        try:
            return int(site_id)
        except (TypeError, ValueError):
            return str(site_id)


class SiteSyncService:
    def __init__(self, client: SyncServerRootAdminClient | None = None) -> None:
        self.client = client or SyncServerRootAdminClient()

    def list_sites(self) -> list[dict[str, Any]]:
        response = self.client.get("/admin/sites", params={"page": 1, "page_size": 200})
        return response.get("sites", []) if isinstance(response, dict) else []

    def refresh_local_cache(self) -> int:
        """Full paginated site snapshot from SyncServer.

        Fetches all pages up to total_count with page_size 200.
        Validates entire snapshot BEFORE any local writes.
        Does NOT prune sites that exist locally but not in remote response.
        Returns number of upserted sites.
        """
        all_remote_sites: list[dict[str, Any]] = []
        page = 1
        page_size = 200
        total_count = 0

        first_response = self.client.get("/admin/sites", params={"page": page, "page_size": page_size})
        if isinstance(first_response, dict):
            sites_page = first_response.get("sites", [])
            total_count = first_response.get("total_count", 0)
            all_remote_sites.extend(sites_page)

        while len(all_remote_sites) < total_count:
            page += 1
            page_response = self.client.get("/admin/sites", params={"page": page, "page_size": page_size})
            if isinstance(page_response, dict):
                all_remote_sites.extend(page_response.get("sites", []))

        for remote_site in all_remote_sites:
            site_id = remote_site.get("site_id") or remote_site.get("id")
            if not site_id:
                raise ValueError(f"Remote site missing site_id: {remote_site.get('code', 'unknown')}")

        count = 0
        for remote_site in all_remote_sites:
            self._upsert_local_mirror(remote_site)
            count += 1

        return count

    def create_site(self, payload: dict[str, Any]) -> Site:
        remote_site = self.client.post("/admin/sites", json=payload)
        return self._upsert_local_mirror(remote_site)

    def update_site(self, syncserver_site_id: str, payload: dict[str, Any]) -> Site:
        remote_site = self.client.patch(f"/admin/sites/{syncserver_site_id}", json=payload)
        return self._upsert_local_mirror(remote_site)

    def _upsert_local_mirror(self, remote_site: dict[str, Any]) -> Site:
        syncserver_site_id = str(remote_site.get("site_id") or remote_site.get("id") or "").strip()
        if not syncserver_site_id:
            raise ValueError("SyncServer site payload does not contain site_id.")

        code = str(remote_site.get("code") or "").strip()
        name = str(remote_site.get("name") or "").strip()

        defaults = {
            "code": code,
            "name": name,
            "description": remote_site.get("description") or "",
            "is_active": bool(remote_site.get("is_active", True)),
        }
        site, _ = Site.objects.update_or_create(
            syncserver_site_id=syncserver_site_id,
            defaults=defaults,
        )
        return site


class DeviceSyncService:
    def __init__(self, client: SyncServerRootAdminClient | None = None) -> None:
        self.client = client or SyncServerRootAdminClient()

    def create_device(self, *, device_code: str, device_name: str, is_active: bool) -> dict[str, Any]:
        return self.client.post(
            "/admin/devices",
            json={
                "device_code": device_code,
                "device_name": device_name,
                "site_id": None,
                "is_active": is_active,
            },
        )

    def update_device(
        self,
        *,
        syncserver_device_id: int,
        device_code: str,
        device_name: str,
        is_active: bool,
    ) -> dict[str, Any]:
        return self.client.patch(
            f"/admin/devices/{syncserver_device_id}",
            json={
                "device_code": device_code,
                "device_name": device_name,
                "site_id": None,
                "is_active": is_active,
            },
        )

    def fetch_device(self, syncserver_device_id: int) -> dict[str, Any]:
        return self.client.get(f"/admin/devices/{syncserver_device_id}")

    def rotate_token(self, syncserver_device_id: int) -> dict[str, Any]:
        return self.client.post(f"/admin/devices/{syncserver_device_id}/rotate-token")

    def apply_remote_state(
        self,
        *,
        binding: SyncDeviceBinding,
        remote_device: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> SyncDeviceBinding:
        binding.syncserver_device_id = int(
            remote_device.get("device_id") or remote_device.get("id") or binding.syncserver_device_id or 0
        )
        binding.device_code = str(remote_device.get("device_code", binding.device_code))
        binding.device_name = str(remote_device.get("device_name", binding.device_name))
        binding.is_active = bool(remote_device.get("is_active", binding.is_active))
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(payload or remote_device)
        remote_last_seen = remote_device.get("last_seen_at")
        if remote_last_seen is not None:
            binding.last_seen_at = remote_last_seen
        binding.save()
        return binding

    def create_binding(self, *, binding: SyncDeviceBinding) -> SyncDeviceBinding:
        remote = self.create_device(
            device_code=binding.device_code,
            device_name=binding.device_name,
            is_active=binding.is_active,
        )
        self.apply_remote_state(binding=binding, remote_device=remote, payload=remote)
        binding.sync_device_token = str(remote.get("device_token", binding.sync_device_token or ""))
        binding.save(update_fields=["sync_device_token", "updated_at"])
        return binding

    def sync_existing_binding(self, *, binding: SyncDeviceBinding) -> SyncDeviceBinding:
        if not binding.syncserver_device_id:
            raise ValueError("Binding has no SyncServer device id for sync.")
        remote = self.update_device(
            syncserver_device_id=binding.syncserver_device_id,
            device_code=binding.device_code,
            device_name=binding.device_name,
            is_active=binding.is_active,
        )
        return self.apply_remote_state(binding=binding, remote_device=remote, payload=remote)

    def ensure_device_remote(
        self,
        *,
        binding: SyncDeviceBinding,
    ) -> SyncDeviceBinding:
        """Idempotent device ensure using PUT by-code."""
        remote = self.client.put(
            f"/admin/devices/by-code/{binding.device_code}",
            json={
                "device_name": binding.device_name,
                "site_id": None,
                "is_active": binding.is_active,
            },
        )
        self.apply_remote_state(binding=binding, remote_device=remote, payload=remote)
        binding.sync_device_token = str(remote.get("device_token", binding.sync_device_token or ""))
        binding.save(update_fields=["sync_device_token", "updated_at"])
        return binding

    def repair_binding_from_remote(self, *, binding: SyncDeviceBinding) -> SyncDeviceBinding:
        if not binding.syncserver_device_id:
            raise ValueError("Binding has no SyncServer device id for repair.")
        remote = self.fetch_device(binding.syncserver_device_id)
        return self.apply_remote_state(binding=binding, remote_device=remote, payload=remote)

    def apply_rotated_token(self, *, binding: SyncDeviceBinding, rotate_response: dict[str, Any]) -> SyncDeviceBinding:
        binding.sync_device_token = str(rotate_response.get("device_token", binding.sync_device_token))
        binding.sync_status = SyncStatus.SYNCED
        binding.last_sync_error = ""
        binding.last_sync_at = timezone.now()
        binding.token_rotated_at = timezone.now()
        binding.last_sync_payload = _sanitized_payload(rotate_response)
        binding.save(
            update_fields=[
                "sync_device_token",
                "sync_status",
                "last_sync_error",
                "last_sync_at",
                "token_rotated_at",
                "last_sync_payload",
                "updated_at",
            ]
        )
        return binding

    def fetch_device_sync_status(self, device_id: int) -> dict[str, Any]:
        """Fetch device sync state from SyncServer.

        Calls ``GET /api/v1/sync/status/{device_id}`` through the root admin
        client. The response contains ``last_sequence_number``,
        ``last_sync_at``, ``status``, ``server_seq_upto``, ``behind_by``.
        """
        return self.client.get(f"/sync/status/{device_id}")

    def refresh_device_status(self, *, binding: SyncDeviceBinding) -> SyncDeviceBinding:
        """Refresh device runtime status from SyncServer sync_state.

        1. Calls ``GET /api/v1/sync/status/{device_id}`` via the root client.
        2. Computes online/offline from *last_sync_at* using the configurable
           threshold (default 300 seconds / 5 minutes).
        3. Computes health from *behind_by*:
             - ``healthy``: behind_by < 50
             - ``degraded``: 50 <= behind_by <= 200
             - ``unhealthy``: behind_by > 200 or status == "error"
        4. Persists the derived fields on the binding so they are visible in
           the admin list without repeated online calls.
        """
        if not binding.syncserver_device_id:
            raise ValueError("Binding has no SyncServer device id for refresh.")

        data = self.fetch_device_sync_status(binding.syncserver_device_id)
        threshold = getattr(settings, "SYNC_ONLINE_THRESHOLD_SECONDS", 300)

        # ── Sync state fields from SyncServer response ─────────────────
        state_status: str = data.get("status", "unknown")
        last_seq: int | None = data.get("last_sequence_number")
        behind_by: int = data.get("behind_by", 0)
        last_sync_at_raw = data.get("last_sync_at")

        # ── Derive online/offline ──────────────────────────────────────
        binding.last_seen_at = last_sync_at_raw
        if state_status == "online":
            binding.sync_state_status = "online"
        elif state_status == "offline":
            binding.sync_state_status = "offline"
        elif state_status == "error":
            binding.sync_state_status = "error"
        else:
            # Fallback: compute from last_sync_at
            if last_sync_at_raw is not None:
                try:
                    from django.utils import timezone as tz
                    # Accept both string (ISO) and datetime objects
                    if isinstance(last_sync_at_raw, str):
                        from datetime import datetime
                        parsed = datetime.fromisoformat(last_sync_at_raw.replace("Z", "+00:00"))
                    else:
                        parsed = last_sync_at_raw
                    delta = tz.now() - parsed
                    binding.sync_state_status = "online" if delta.total_seconds() < threshold else "offline"
                except (TypeError, ValueError):
                    binding.sync_state_status = "unknown"
            else:
                binding.sync_state_status = "unknown"

        # ── Derive health ──────────────────────────────────────────────
        if state_status == "error":
            binding.health_status = "unhealthy"
        elif behind_by < 50:
            binding.health_status = "healthy"
        elif behind_by <= 200:
            binding.health_status = "degraded"
        else:
            binding.health_status = "unhealthy"

        binding.sync_state_last_seq = last_seq
        binding.sync_state_behind_by = behind_by
        binding.save(update_fields=[
            "sync_state_status",
            "sync_state_last_seq",
            "sync_state_behind_by",
            "health_status",
            "last_seen_at",
            "updated_at",
        ])
        return binding

    def mark_failure(
        self,
        *,
        binding: SyncDeviceBinding,
        error: Exception,
        payload: dict[str, Any] | None = None,
        status: str = SyncStatus.SYNC_FAILED,
    ) -> SyncDeviceBinding:
        binding.sync_status = status
        binding.last_sync_error = str(error)
        binding.last_sync_at = timezone.now()
        if payload is not None:
            binding.last_sync_payload = _sanitized_payload(payload)
        binding.save(
            update_fields=[
                "sync_status",
                "last_sync_error",
                "last_sync_at",
                "last_sync_payload",
                "updated_at",
            ]
        )
        return binding
