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
