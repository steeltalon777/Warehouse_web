import logging

from django.contrib.auth.mixins import LoginRequiredMixin

from apps.common.permissions import can_use_client
from apps.sync_client.client import SyncServerClient
from apps.sync_client.sites_api import SitesAPI
from apps.sync_client.users_api import UsersAPI

logger = logging.getLogger(__name__)


class SyncContextMixin(LoginRequiredMixin):
    """
    Shared runtime context for SyncServer-backed feature views.
    """

    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return self.handle_no_permission()

        self.site_id = request.session.get("active_site") or getattr(
            getattr(request.user, "profile", None), "site_id", None
        )
        self.client = SyncServerClient(user_id=request.user.id, site_id=self.site_id)
        return super().dispatch(request, *args, **kwargs)


class SyncAdminMixin(LoginRequiredMixin):
    """
    Shared admin context for SyncServer admin views.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

        sync_identity = getattr(request, "sync_identity", None)
        if not sync_identity:
            logger.warning("No SyncServer identity found in request")
            self.user_id = "admin"
            self.site_id = "main"
        else:
            self.user_id = sync_identity.user_id
            self.site_id = sync_identity.site_id or "main"

        self.client = SyncServerClient(user_id=self.user_id, site_id=self.site_id)
        self.users_api = UsersAPI(self.client)
        self.sites_api = SitesAPI(self.client)
