from django.http import JsonResponse
from django.views import View

from apps.catalog.services import CatalogService


class HealthCheckView(View):
    def get(self, request):
        return JsonResponse({"status": "ok", "service": "warehouse_web"})


class SyncHealthCheckView(View):
    service = CatalogService()

    def get(self, request):
        result = self.service.list_categories()
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
