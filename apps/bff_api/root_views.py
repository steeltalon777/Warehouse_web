from django.views import View

from apps.bff_api.helpers import _public_get, _handle_sync_error, _ok, _error
from apps.sync_client.exceptions import SyncServerAPIError


class RootView(View):
    def get(self, request):
        try:
            data = _public_get("/")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)


class DBCheckView(View):
    def get(self, request):
        try:
            data = _public_get("/db_check")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)
