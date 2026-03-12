from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        # Intentionally do not auto-import legacy profile signals.
        # Django auth in this project is used for technical admin/staff access,
        # while domain users/roles/sites live in SyncServer.
        return
