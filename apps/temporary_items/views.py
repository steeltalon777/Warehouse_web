from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.common.mixins import SyncContextMixin
from apps.common.permissions import can_manage_catalog
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.temporary_items_api import TemporaryItemsAPI

logger = logging.getLogger(__name__)


class TemporaryItemListView(SyncContextMixin, View):
    """Список временных ТМЦ с пагинацией и фильтрацией."""

    template_name = "temporary_items/list.html"

    def get(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        page = request.GET.get("page", 1)
        page_size = request.GET.get("page_size", 20)
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
            logger.error("Ошибка при получении списка временных ТМЦ: %s", e)
            messages.error(request, "Не удалось загрузить список временных ТМЦ.")
            items = []
            total_count = 0
            current_page = 1
            page_size = 20

        context = {
            "items": items,
            "total_count": total_count,
            "page": current_page,
            "page_size": page_size,
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
            logger.error("Ошибка при получении временной ТМЦ %s: %s", item_id, e)
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        context = {
            "item": item,
        }
        return render(request, self.template_name, context)


class TemporaryItemApproveView(SyncContextMixin, View):
    """Преобразование временной ТМЦ в постоянную."""

    template_name = "temporary_items/approve.html"

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
            logger.error("Ошибка при получении временной ТМЦ %s: %s", item_id, e)
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        context = {
            "item": item,
        }
        return render(request, self.template_name, context)

    def post(self, request, item_id, *args, **kwargs):
        if not can_manage_catalog(request.user):
            messages.error(request, "У вас нет прав для управления каталогом.")
            return redirect("client:dashboard")

        try:
            temp_api = TemporaryItemsAPI(self.client)
            result = temp_api.approve_as_item(item_id)
            messages.success(request, "Временная ТМЦ успешно преобразована в постоянную.")
            return redirect("temporary_items:detail", item_id=item_id)
        except SyncServerAPIError as e:
            logger.error("Ошибка при преобразовании временной ТМЦ %s: %s", item_id, e)
            messages.error(request, f"Не удалось преобразовать временную ТМЦ: {str(e)}")
            return redirect("temporary_items:approve", item_id=item_id)


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
            logger.error("Ошибка при получении временной ТМЦ %s: %s", item_id, e)
            messages.error(request, "Не удалось загрузить данные временной ТМЦ.")
            return redirect("temporary_items:list")

        # Получить список существующих ТМЦ для выбора
        from apps.sync_client.catalog_api import CatalogAPI
        catalog_api = CatalogAPI(self.client)
        try:
            catalog_items = catalog_api.list_items(filters={"site_id": self.site_id})
        except SyncServerAPIError:
            catalog_items = []

        context = {
            "item": item,
            "catalog_items": catalog_items,
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
            logger.error("Ошибка при слиянии временной ТМЦ %s: %s", item_id, e)
            messages.error(request, f"Не удалось объединить временную ТМЦ: {str(e)}")
            return redirect("temporary_items:merge", item_id=item_id)


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
            logger.error("Ошибка при получении временной ТМЦ %s: %s", item_id, e)
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
            logger.error("Ошибка при удалении временной ТМЦ %s: %s", item_id, e)
            error_detail = str(e)
            try:
                error_data = json.loads(str(e))
                error_detail = error_data.get("detail", str(e))
            except (json.JSONDecodeError, TypeError):
                pass
            messages.error(request, f"Не удалось удалить временную ТМЦ: {error_detail}")
            return redirect("temporary_items:delete", item_id=item_id)
