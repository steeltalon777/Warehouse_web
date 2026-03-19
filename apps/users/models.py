from django.conf import settings
from django.db import models


class Site(models.Model):
    """Legacy warehouse site mirror kept for transition period.

    Source of truth for sites is SyncServer. This model must not drive
    authentication/authorization decisions in Django.
    """

    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Role(models.TextChoices):
    """Legacy role enum.

    Domain roles should come from SyncServer. Django superuser/staff remains
    the technical admin layer for this web client.
    """

    ROOT = "root", "Root"
    CHIEF_STOREKEEPER = "chief_storekeeper", "Chief Storekeeper"
    STOREKEEPER = "storekeeper", "Storekeeper"
    OBSERVER = "observer", "Observer"


class SyncStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    SYNC_FAILED = "sync_failed", "Sync Failed"
    REPAIR_REQUIRED = "repair_required", "Repair Required"
    MANUAL_OVERRIDE = "manual_override", "Manual Override"


class UserProfile(models.Model):
    """Deprecated profile extension for transition compatibility.

    Keep optional and non-blocking: auth flow for Django superuser/staff must
    work without this table/record.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=50,
        choices=Role.choices,
        default=Role.STOREKEEPER,
    )
    site = models.ForeignKey(
        Site,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"


class SyncUserBinding(models.Model):
    """Local binding for a Django user managed in SyncServer."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sync_binding",
    )
    syncserver_user_id = models.UUIDField(unique=True, null=True, blank=True)
    sync_user_token = models.CharField(max_length=255, blank=True)
    sync_role = models.CharField(
        max_length=50,
        choices=Role.choices,
        default=Role.STOREKEEPER,
    )
    default_site_id = models.CharField(max_length=64, blank=True)
    site_ids = models.JSONField(default=list, blank=True)
    sync_status = models.CharField(
        max_length=32,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING,
    )
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True)
    last_sync_payload = models.JSONField(default=dict, blank=True)
    token_rotated_at = models.DateTimeField(null=True, blank=True)
    manual_token_updated_at = models.DateTimeField(null=True, blank=True)
    manual_token_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manual_sync_token_updates",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return f"Sync binding for {self.user.username}"
