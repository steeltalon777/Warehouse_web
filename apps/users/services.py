from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.sync_client.root_admin_client import SyncServerRootAdminClient
from apps.users.models import Role, Site, SyncStatus, SyncUserBinding

User = get_user_model()


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
            "default_site_id": self._normalize_site_id(default_site_id),
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
        binding.last_sync_payload = prepared.sync_state_response or prepared.sync_user_response
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
        binding.last_sync_payload = sync_state
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
            binding.last_sync_payload = payload
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
        binding.last_sync_payload = rotate_response
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

    def refresh_local_cache(self) -> None:
        remote_sites = self.list_sites()
        seen_ids: set[str] = set()

        for remote_site in remote_sites:
            mirror = self._upsert_local_mirror(remote_site)
            seen_ids.add(mirror.syncserver_site_id)

        if seen_ids:
            Site.objects.exclude(syncserver_site_id__in=seen_ids).delete()
            return

        Site.objects.all().delete()

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
        Site.objects.exclude(syncserver_site_id=syncserver_site_id).filter(code=code).delete()
        Site.objects.exclude(syncserver_site_id=syncserver_site_id).filter(name=name).delete()

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
