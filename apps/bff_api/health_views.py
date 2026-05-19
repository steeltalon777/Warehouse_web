from django.views import View

from apps.bff_api.helpers import _public_get, _handle_sync_error, _ok, _error
from apps.sync_client.exceptions import SyncServerAPIError


class HealthView(View):
    def get(self, request):
        try:
            data = _public_get("/health")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)


class ReadyView(View):
    def get(self, request):
        try:
            data = _public_get("/ready")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)


class HealthDetailedView(View):
    def get(self, request):
        try:
            data = _public_get("/health/detailed")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)


class HealthReadinessView(View):
    def get(self, request):
        try:
            data = _public_get("/health/readiness")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)


class HealthLivenessView(View):
    def get(self, request):
        try:
            data = _public_get("/health/liveness")
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except Exception as exc:
            return _error(str(exc), status=502)
