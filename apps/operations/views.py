from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import SyncContextMixin
from apps.operations.constants import CREATE_DISABLED_OPERATION_TYPES, OPERATION_STATUS_META
from apps.operations.forms import OperationCreateForm
from apps.operations.services import OperationPageService
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.operations_api import OperationsAPI

logger = logging.getLogger(__name__)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_page_size(raw_value: Any, default: int = 20) -> int:
    try:
        page_size = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(page_size, 10), 100)


def _default_draft(
    operate_sites: list[dict[str, Any]],
    *,
    fixed_operating_site_id: int | None = None,
) -> dict[str, Any]:
    default_site_id = fixed_operating_site_id or (operate_sites[0]["site_id"] if operate_sites else "")
    return {
        "operation_type": "RECEIVE",
        "site_id": default_site_id,
        "source_site_id": default_site_id,
        "destination_site_id": "",
        "issued_to_name": "",
        "notes": "",
        "items": [],
    }


def _safe_get_operate_sites(service: OperationPageService, request) -> list[dict[str, Any]]:
    try:
        return service.get_operate_sites()
    except SyncServerAPIError as exc:
        messages.error(request, str(exc) or "Не удалось загрузить доступные склады.")
        return []


def _build_create_payload(
    draft_data: dict[str, Any],
    *,
    operate_site_ids: set[int],
    fixed_operating_site_id: int | None = None,
) -> dict[str, Any]:
    operation_type = str(draft_data.get("operation_type") or "").strip().upper()
    if not operation_type:
        raise ValidationError("Выберите тип операции.")
    if operation_type in CREATE_DISABLED_OPERATION_TYPES:
        raise ValidationError("Для выбранного типа создание через web-клиент пока недоступно.")

    raw_items = draft_data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError("Добавьте хотя бы одну строку ТМЦ.")

    notes = str(draft_data.get("notes") or "").strip()
    issued_to_name = str(draft_data.get("issued_to_name") or "").strip()
    site_id = _to_int(draft_data.get("site_id"))
    source_site_id = _to_int(draft_data.get("source_site_id"))
    destination_site_id = _to_int(draft_data.get("destination_site_id"))

    payload: dict[str, Any] = {
        "operation_type": operation_type,
        "notes": notes or None,
        "lines": [],
    }

    if operation_type == "MOVE":
        if fixed_operating_site_id is not None:
            source_site_id = fixed_operating_site_id
        if source_site_id not in operate_site_ids:
            raise ValidationError("Выберите склад-источник для операции перемещения.")
        if destination_site_id not in operate_site_ids:
            raise ValidationError("Выберите склад-получатель для операции перемещения.")
        if source_site_id == destination_site_id:
            raise ValidationError("Склад-источник и склад-получатель должны отличаться.")
        payload["site_id"] = source_site_id
        payload["source_site_id"] = source_site_id
        payload["destination_site_id"] = destination_site_id
    else:
        if fixed_operating_site_id is not None:
            site_id = fixed_operating_site_id
        if site_id not in operate_site_ids:
            raise ValidationError("Выберите склад для операции.")
        payload["site_id"] = site_id

    if operation_type == "EXPENSE":
        if not issued_to_name:
            raise ValidationError("Укажите ФИО получателя для расходной операции.")
        payload["issued_to_name"] = issued_to_name

    allow_negative_qty = operation_type == "ADJUSTMENT"
    line_number = 1
    seen_item_ids: set[int] = set()
    for item in raw_items:
        item_id = _to_int(item.get("item_id") or item.get("id"))
        qty = _to_int(item.get("quantity"))
        if item_id is None:
            raise ValidationError("В одной из строк не выбран ТМЦ.")
        if qty is None:
            raise ValidationError("В одной из строк не указано количество.")
        if qty == 0:
            raise ValidationError("Количество не может быть нулевым.")
        if not allow_negative_qty and qty < 0:
            raise ValidationError("Отрицательное количество разрешено только для корректировки.")
        if item_id in seen_item_ids:
            raise ValidationError("В черновике есть дублирующиеся строки ТМЦ. Обновите список и попробуйте снова.")
        seen_item_ids.add(item_id)
        payload["lines"].append({"line_number": line_number, "item_id": item_id, "qty": qty})
        line_number += 1

    return payload


def _format_create_error(exc: SyncServerAPIError) -> str:
    if exc.status_code == 403:
        return "У текущего пользователя нет прав на создание операции для выбранного склада."
    if exc.status_code in {409, 422}:
        return str(exc)
    return str(exc) or "Не удалось создать операцию."


def _format_submit_error(exc: SyncServerAPIError) -> str:
    if exc.status_code == 403:
        return "Операция создана, но подтверждение отклонено. У текущего пользователя нет прав на подтверждение для выбранного склада."
    if exc.status_code in {409, 422}:
        return f"Подтверждение отклонено: {exc}"
    if exc.status_code == 501:
        return "Операция создана, но подтверждение для этого типа пока не реализовано."
    return f"Подтверждение отклонено: {exc}"


def _format_cancel_error(exc: SyncServerAPIError) -> str:
    if exc.status_code == 403:
        return "У текущего пользователя нет прав на отмену этой операции."
    if exc.status_code == 409:
        return f"Отмена отклонена: {exc}"
    return str(exc) or "Не удалось отменить операцию."


class OperationsListView(SyncContextMixin, TemplateView):
    template_name = "operations/list.html"

    def get(self, request, *args, **kwargs):
        search = request.GET.get("search") or ""
        status = request.GET.get("status") or ""
        operation_type = request.GET.get("type") or ""
        page = max(_to_int(request.GET.get("page")) or 1, 1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)

        service = OperationPageService(self.client, request=request)
        api = OperationsAPI(self.client)
        operate_sites = _safe_get_operate_sites(service, request)

        filters: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "search": search or None,
            "status": status or None,
            "type": operation_type or None,
        }

        page_data = {"items": [], "total_count": 0, "page": page, "page_size": page_size}
        try:
            page_data = api.list_operations_page(filters=filters)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "?? ??????? ????????? ????????.")

        try:
            operations = service.present_operations(page_data.get("items", []))
        except SyncServerAPIError as exc:
            operations = []
            messages.error(request, str(exc) or "Не удалось подготовить список операций.")

        total_count = int(page_data.get("total_count") or 0)
        total_pages = max((total_count + page_size - 1) // page_size, 1)
        current_page = int(page_data.get("page") or page)

        context = {
            "operations": operations,
            "search": search,
            "status": status,
            "type": operation_type,
            "page_size": page_size,
            "current_page": current_page,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": max(current_page - 1, 1),
            "next_page": min(current_page + 1, total_pages),
            "can_create_operations": bool(operate_sites),
            "operation_type_options": service.operation_type_options(),
            "status_options": [
                {"code": status_code, "label": meta["label"]}
                for status_code, meta in OPERATION_STATUS_META.items()
            ],
        }
        return render(request, self.template_name, context)


class OperationDetailView(SyncContextMixin, TemplateView):
    template_name = "operations/detail.html"

    def get(self, request, operation_id):
        service = OperationPageService(self.client, request=request)
        try:
            operation = OperationsAPI(self.client).get_operation(operation_id)
            presented_operation = service.present_operation(operation)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                raise Http404("Операция не найдена.") from exc
            messages.error(request, str(exc) or "Не удалось загрузить операцию.")
            return redirect("operations:list")

        context = {
            "operation": presented_operation,
            "submit_next_url": reverse("operations:detail", kwargs={"operation_id": operation_id}),
            "cancel_next_url": reverse("operations:detail", kwargs={"operation_id": operation_id}),
        }
        return render(request, self.template_name, context)


class OperationItemSearchView(SyncContextMixin, View):
    def get(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        if not operate_sites:
            return JsonResponse({"items": [], "error": "Нет прав на создание операций."}, status=403)

        query = (request.GET.get("q") or "").strip()
        if len(query) < 2:
            return JsonResponse({"items": []})

        try:
            items = service.search_items(query, limit=12)
        except DatabaseError:
            logger.exception("Local catalog cache is not ready for item search.")
            return JsonResponse(
                {
                    "items": [],
                    "error": "????????? ??? ???????? ??? ?? ???????????. ????????? migrate ? sync_catalog_cache.",
                },
                status=503,
            )
        except SyncServerAPIError as exc:
            return JsonResponse({"items": [], "error": str(exc) or "?? ??????? ????????? ???."}, status=502)

        return JsonResponse({"items": items})


class OperationCreateView(SyncContextMixin, View):
    template_name = "operations/form.html"

    def get(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        fixed_operating_site_id = service.get_fixed_operating_site_id()
        draft = _default_draft(operate_sites, fixed_operating_site_id=fixed_operating_site_id)
        form = OperationCreateForm(initial={"draft_payload": json.dumps(draft, ensure_ascii=False)})
        return render(
            request,
            self.template_name,
            self._build_context(
                service=service,
                form=form,
                draft=draft,
                operate_sites=operate_sites,
                fixed_operating_site_id=fixed_operating_site_id,
            ),
        )

    def post(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        fixed_operating_site_id = service.get_fixed_operating_site_id()
        form = OperationCreateForm(request.POST)
        draft = _default_draft(operate_sites, fixed_operating_site_id=fixed_operating_site_id)

        if form.is_valid():
            draft = form.parsed_payload
            try:
                payload = _build_create_payload(
                    draft,
                    operate_site_ids={int(site["site_id"]) for site in operate_sites},
                    fixed_operating_site_id=fixed_operating_site_id,
                )
                created = OperationsAPI(self.client).create_operation(payload)
            except ValidationError as exc:
                form.add_error(None, exc.message)
            except SyncServerAPIError as exc:
                form.add_error(None, _format_create_error(exc))
            else:
                messages.success(request, "Операция создана.")
                return redirect("operations:detail", operation_id=created.get("id"))
        else:
            raw_payload = (request.POST.get("draft_payload") or "").strip()
            if raw_payload:
                try:
                    draft = json.loads(raw_payload)
                except json.JSONDecodeError:
                    draft = _default_draft(operate_sites, fixed_operating_site_id=fixed_operating_site_id)

        return render(
            request,
            self.template_name,
            self._build_context(
                service=service,
                form=form,
                draft=draft,
                operate_sites=operate_sites,
                fixed_operating_site_id=fixed_operating_site_id,
            ),
        )

    def _build_context(
        self,
        *,
        service: OperationPageService,
        form: OperationCreateForm,
        draft: dict[str, Any],
        operate_sites: list[dict[str, Any]],
        fixed_operating_site_id: int | None,
    ) -> dict[str, Any]:
        fixed_operating_site = None
        if fixed_operating_site_id is not None:
            fixed_operating_site = next(
                (site for site in operate_sites if int(site["site_id"]) == int(fixed_operating_site_id)),
                None,
            )

        return {
            "form": form,
            "draft": draft,
            "operate_sites": operate_sites,
            "can_create_operations": bool(operate_sites),
            "operation_type_options": service.operation_type_options(),
            "item_search_url": reverse("operations:item_search"),
            "can_choose_source_site": service.can_choose_source_site(),
            "fixed_operating_site": fixed_operating_site,
            "fixed_operating_site_id": fixed_operating_site_id or "",
        }


class SubmitOperationView(SyncContextMixin, View):
    def post(self, request, operation_id):
        next_url = request.POST.get("next") or reverse("operations:detail", kwargs={"operation_id": operation_id})

        try:
            OperationsAPI(self.client).submit_operation(operation_id, payload={"submit": True})
            messages.success(request, "Операция подтверждена.")
        except SyncServerAPIError as exc:
            messages.error(request, _format_submit_error(exc))

        return redirect(next_url)


class CancelOperationView(SyncContextMixin, View):
    def post(self, request, operation_id):
        next_url = request.POST.get("next") or reverse("operations:detail", kwargs={"operation_id": operation_id})
        reason = (request.POST.get("reason") or "").strip()
        payload: dict[str, Any] = {"cancel": True}
        if reason:
            payload["reason"] = reason

        try:
            OperationsAPI(self.client).cancel_operation(operation_id, payload=payload)
            messages.success(request, "Операция отменена.")
        except SyncServerAPIError as exc:
            messages.error(request, _format_cancel_error(exc))

        return redirect(next_url)
