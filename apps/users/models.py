from django.conf import settings
from django.db import models


# Create your models here.
class Site(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

class Role(models.TextChoices):
    ROOT = "root", "Root"
    CHIEF_STOREKEEPER = "chief_storekeeper", "Chief Storekeeper"
    STOREKEEPER = "storekeeper", "Storekeeper"

class UserProfile(models.Model):
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

