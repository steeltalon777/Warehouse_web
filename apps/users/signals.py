"""Legacy signals kept for backwards compatibility.

Do not auto-register these signals in app config. Django auth in Warehouse_web
is a technical admin/staff layer; domain users/roles/sites are managed in
SyncServer.
"""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import Role, UserProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Deprecated: keep optional profile creation only when explicitly wired."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"role": Role.STOREKEEPER},
        )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Deprecated: preserve compatibility for existing profile rows."""
    profile = getattr(instance, "profile", None)
    if profile:
        profile.save()
