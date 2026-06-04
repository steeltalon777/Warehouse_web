from __future__ import annotations

import json
import math
from typing import Any

import structlog
from django.contrib import messages
from django.db.utils import DatabaseError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.catalog.forms import ItemForm
from apps.catalog.services import CatalogService
from apps.catalog.views import _filter_manage_categories, _normalize_categories, _normalize_units
from apps.common.mixins import SyncContextMixin
from apps.common.permissions import can_manage_catalog
from apps.operations.services import OperationPageService
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.temporary_items_api import TemporaryItemsAPI

logger = structlog.get_logger()


class TemporaryItemListView(SyncContextMixin, View):
    """Список временных ТМЦ с пагинацией и фильтрацией."""

    template_name = "temporary_items/list.html"

    def get(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            page = int(request.GET.get("page", 1))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = int(request.GET.get("page_size", 20))
        except (ValueError, TypeError):
            page_size = 20
        status = request.GET.get("status")
        search = request.GET.get("search")

        filters = {}
        if status:
            filters["status"] = status
        if search:
            filters["search"] = search
        filters["page"] = page
        filters["page_size"] = page_size

        try:
            temp_api = TemporaryItemsAPI(self.client)
            result = temp_api.list_temporary_items_page(filters=filters)
            items = result.get("items", [])
            total_count = result.get("total_count", 0)
            current_page = result.get("page", 1)
            page_size = result.get("page_size", 20)
        except SyncServerAPIError as e:
            logger.error("temporary_items_list_error", error=str(e))
            messages.error(request, "Не удалось загрузить список временных ТМЦ.")
            items = []
            total_count = 0
            current_page = 1
            page_size = 20

        total_pages = max(1, math.ceil(total_count / page_size)) if page_size > 0 else 1

        context = {
            "items": items,
            "total_count": total_count,
            "page": current_page,
            "page_size": page_size,
            "total_pages": total_pages,
            "status": status,
            "search": search,
        }
        return render(request, self.template_name, context)


class TemporaryItemDetailView(SyncContextMixin, View):
    """Детальная информация о временной ТМЦ."""

    template_name = "temporary_items/detail.html"

    def get(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            temp_api = TemporaryItemsAPI(self.client)
            item = temp_api.get_temporary_item(item_id)
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_detail_error", item_id=item_id, error=str(e))
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        context = {
            "item": item,
        }
        return render(request, self.template_name, context)


class TemporaryItemApproveView(SyncContextMixin, View):
    """Преобразование временной ТМЦ в постоянную."""

    template_name = "temporary_items/approve.html"

    def _load_temporary_item(self, item_id):
        temp_api = TemporaryItemsAPI(self.client)
        return temp_api.get_temporary_item(item_id)

    def _catalog_form_options(self):
        catalog_service = CatalogService(self.client)
        categories_result = catalog_service.list_admin_categories()
        units_result = catalog_service.list_admin_units()
        categories = _normalize_categories(categories_result.data or []) if categories_result.ok else []
        units = _normalize_units(units_result.data or []) if units_result.ok else []
        return _filter_manage_categories(categories), units, categories_result, units_result

    def get(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            item = self._load_temporary_item(item_id)
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_detail_error", item_id=item_id, error=str(e))
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        categories, units, categories_result, units_result = self._catalog_form_options()
        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        initial = {
            "name": item.get("name") or "",
            "sku": item.get("sku") or "",
            "category_id": str(item.get("category_id") or ""),
            "unit_id": str(item.get("unit_id") or ""),
            "is_active": True,
        }
        form = ItemForm(initial=initial, categories=categories, units=units)

        context = {
            "item": item,
            "form": form,
            "page_title": "Преобразование временной ТМЦ в постоянную",
            "page_note": "Отредактируйте карточку будущей ТМЦ и сохраните. После создания временная ТМЦ будет автоматически объединена с новой.",
            "back_url": reverse("temporary_items:detail", kwargs={"item_id": item_id}),
        }
        return render(request, self.template_name, context)

    def post(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            item = self._load_temporary_item(item_id)
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_detail_error", item_id=item_id, error=str(e))
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        categories, units, categories_result, units_result = self._catalog_form_options()
        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        form = ItemForm(request.POST, categories=categories, units=units)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "item": item,
                    "form": form,
                    "page_title": "Преобразование временной ТМЦ в постоянную",
                    "page_note": "Отредактируйте карточку будущей ТМЦ и сохраните. После создания временная ТМЦ будет автоматически объединена с новой.",
                    "back_url": reverse("temporary_items:detail", kwargs={"item_id": item_id}),
                },
            )

        catalog_service = CatalogService(self.client)
        temp_api = TemporaryItemsAPI(self.client)
        created_item_id = None
        create_result = catalog_service.create_item(form.cleaned_data)
        if not create_result.ok:
            form.add_error(None, create_result.form_error)
            return render(
                request,
                self.template_name,
                {
                    "item": item,
                    "form": form,
                    "page_title": "Преобразование временной ТМЦ в постоянную",
                    "page_note": "Отредактируйте карточку будущей ТМЦ и сохраните. После создания временная ТМЦ будет автоматически объединена с новой.",
                    "back_url": reverse("temporary_items:detail", kwargs={"item_id": item_id}),
                },
            )

        try:
            created_item_id = create_result.data.get("id")
            temp_api.merge_to_item(item_id, {"target_item_id": created_item_id})
        except SyncServerAPIError as e:
            logger.error("temporary_item_merge_error", item_id=item_id, created_item_id=created_item_id, error=str(e))
            cleanup_message = ""
            if created_item_id is not None:
                cleanup_result = catalog_service.delete_item(str(created_item_id))
                if cleanup_result.ok:
                    cleanup_message = " Новая ТМЦ автоматически удалена."
                else:
                    cleanup_message = " Новая ТМЦ уже создана и требует ручной проверки."
            form.add_error(None, f"Не удалось завершить преобразование временной ТМЦ: {str(e)}.{cleanup_message}")
            return render(
                request,
                self.template_name,
                {
                    "item": item,
                    "form": form,
                    "page_title": "Преобразование временной ТМЦ в постоянную",
                    "page_note": "Отредактируйте карточку будущей ТМЦ и сохраните. После создания временная ТМЦ будет автоматически объединена с новой.",
                    "back_url": reverse("temporary_items:detail", kwargs={"item_id": item_id}),
                },
            )

        messages.success(request, "Временная ТМЦ преобразована в постоянную и объединена с новой карточкой.")
        return redirect("nomenclature:item_update", pk=created_item_id)


class TemporaryItemMergeView(SyncContextMixin, View):
    """Слияние временной ТМЦ с существующей."""

    template_name = "temporary_items/merge.html"

    def get(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            temp_api = TemporaryItemsAPI(self.client)
            item = temp_api.get_temporary_item(item_id)
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_detail_error", item_id=item_id, error=str(e))
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        context = {
            "item": item,
            "item_search_url": reverse("temporary_items:item_search"),
        }
        return render(request, self.template_name, context)

    def post(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        target_item_id = request.POST.get("target_item_id")
        if not target_item_id:
            messages.error(request, "Не выбран целевой ТМЦ для слияния.")
            return redirect("temporary_items:merge", item_id=item_id)

        try:
            temp_api = TemporaryItemsAPI(self.client)
            result = temp_api.merge_to_item(item_id, {"target_item_id": target_item_id})
            messages.success(request, "Временная ТМЦ успешно объединена с существующей.")
            return redirect("temporary_items:list")
        except SyncServerAPIError as e:
            logger.error("temporary_item_merge_error", item_id=item_id, error=str(e))
            messages.error(request, f"Не удалось объединить временную ТМЦ: {str(e)}")
            return redirect("temporary_items:merge", item_id=item_id)


class TemporaryItemCatalogSearchView(SyncContextMixin, View):
    def get(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return JsonResponse({"items": [], "error": "Нет прав для поиска по каталогу."}, status=403)

        query = (request.GET.get("q") or "").strip()
        if len(query) < 2:
            return JsonResponse({"items": []})

        service = OperationPageService(self.client, request=request)
        try:
            items = service.search_items(query, limit=12)
        except DatabaseError:
            logger.error("temporary_item_search_cache_error", exc_info=True)
            return JsonResponse({"items": []})
        except SyncServerAPIError as exc:
            return JsonResponse(
                {"items": [], "error": str(exc) or "Не удалось выполнить поиск по каталогу."},
                status=502,
            )

        return JsonResponse({"items": items})


class TemporaryItemDeleteView(SyncContextMixin, View):
    """Подтверждение и мягкое удаление временной ТМЦ."""

    template_name = "temporary_items/confirm_delete.html"

    def get(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            temp_api = TemporaryItemsAPI(self.client)
            item = temp_api.get_temporary_item(item_id)
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_detail_error", item_id=item_id, error=str(e))
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        context = {
            "item": item,
            "back_url": reverse("temporary_items:detail", kwargs={"item_id": item_id}),
        }
        return render(request, self.template_name, context)

    def post(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            temp_api = TemporaryItemsAPI(self.client)
            result = temp_api.delete_temporary_item(item_id)
            messages.success(request, "Временная ТМЦ удалена.")
            return redirect("temporary_items:list")
        except SyncServerAPIError as e:
            if e.status_code == 404:
                raise Http404("Временная ТМЦ не найдена.")
            logger.error("temporary_item_delete_error", item_id=item_id, error=str(e))
            error_detail = str(e)
            try:
                error_data = json.loads(str(e))
                error_detail = error_data.get("detail", str(e))
            except (json.JSONDecodeError, TypeError):
                pass
            messages.error(request, f"Не удалось удалить временную ТМЦ: {error_detail}")
            return redirect("temporary_items:delete", item_id=item_id)


class TemporaryItemBulkDeleteView(SyncContextMixin, View):
    """Массовое удаление временных ТМЦ (очистка завершённых)."""

    def post(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        item_ids = request.POST.getlist("item_ids")
        if not item_ids:
            messages.warning(request, "Не выбрано ни одной временной ТМЦ для удаления.")
            return redirect("temporary_items:list")

        temp_api = TemporaryItemsAPI(self.client)
        deleted_count = 0
        failed_count = 0

        for item_id in item_ids:
            item_id = item_id.strip()
            if not item_id:
                continue
            try:
                temp_api.delete_temporary_item(item_id)
                deleted_count += 1
            except SyncServerAPIError:
                failed_count += 1

        if deleted_count:
            messages.success(request, f"Удалено временных ТМЦ: {deleted_count}.")
        if failed_count:
            messages.warning(
                request,
                f"Не удалось удалить {failed_count} временных ТМЦ. "
                f"Возможно, статус не позволяет удаление (требуется 'active').",
            )

        return redirect("temporary_items:list")
