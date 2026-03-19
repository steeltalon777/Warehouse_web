from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        # Intentionally do not auto-import legacy profile signals.
        # Django auth in this project is used for technical admin/staff access,
        # while domain users/roles/sites live in SyncServer.

        # Import and register SyncServer authentication signals
        try:
            # Use simple sync signals for cleaner integration
            from . import simple_sync_signals  # noqa: F401
            print(f"Registered SyncServer authentication signals for {self.name}")
        except ImportError as e:
            print(f"Warning: Could not import simple_sync_signals for {self.name}: {e}")
            # Fall back to original sync_signals
            try:
                from . import sync_signals  # noqa: F401
                print(f"Registered original sync_signals for {self.name}")
            except ImportError as e2:
                print(f"Warning: Could not import any sync signals for {self.name}: {e2}")

        return

