from django.http import JsonResponse
from django.views import View

from apps.catalog.services import CatalogService
from apps.sync_client.client import SyncServerClient


class HealthCheckView(View):
    def get(self, request):
        return JsonResponse({"status": "ok", "service": "warehouse_web"})


class SyncHealthCheckView(View):
    def get(self, request):
        client = SyncServerClient()
        service = CatalogService(client)
        result = service.list_categories()
        if result.ok:
            return JsonResponse({"status": "ok", "syncserver": "reachable"})
        return JsonResponse(
            {
                "status": "degraded",
                "syncserver": "unreachable",
                "detail": result.form_error,
            },
            status=503,
        )
