from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings

from apps.common.permissions import can_use_client
from apps.sync_client.client import SyncServerClient


class SyncContextMixin(LoginRequiredMixin):
    """
    Shared runtime context for SyncServer-backed feature views.
    """

    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return self.handle_no_permission()

        self.site_id = (
            request.session.get("active_site")
            or request.session.get("sync_default_site_id")
            or request.session.get("site_id")
            or getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")
        )
        self.client = SyncServerClient(
            user_id=request.user.id,
            site_id=self.site_id,
            request=request,
        )
        return super().dispatch(request, *args, **kwargs)
