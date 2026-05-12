from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from apps.catalog.forms import ItemForm, find_default_unit_id
from apps.catalog.services import CatalogService
from apps.catalog.views import _normalize_categories, _normalize_units
from apps.common.mixins import SyncContextMixin
from apps.operations.constants import (
    CREATE_DISABLED_OPERATION_TYPES,
    OPERATION_STATUS_META,
)
from apps.operations.forms import (
    OperationCreateForm,
    validate_acceptance_lines,
    validate_lost_asset_resolve,
)
from apps.operations.services import OperationPageService
from apps.sync_client.assets_api import AssetsAPI
from apps.sync_client.documents_api import DocumentsAPI
from apps.sync_client.exceptions import SyncServerAPIError
from apps.documents.views import present_document
from apps.sync_client.operations_api import OperationsAPI

logger = logging.getLogger(__name__)
QTY_SCALE = Decimal("0.001")
MAX_QTY_ABS = Decimal("1000000000000000")
PENDING_ACCEPTANCE_PAGE_SIZE = 200


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal_qty(value: Any) -> Decimal | None:
    if value is None:
        return None

    raw_value = str(value).strip().replace(",", ".")
    if not raw_value:
        return None

    try:
        qty = Decimal(raw_value)
        quantized = qty.quantize(QTY_SCALE)
    except (InvalidOperation, ValueError):
        return None

    if not qty.is_finite() or qty != quantized:
        return None
    if abs(quantized) >= MAX_QTY_ABS:
        return None

    return quantized


def _serialize_decimal_qty(qty: Decimal) -> str:
    return format(qty.normalize(), "f")


def _current_local_datetime_value() -> str:
    return timezone.localtime().replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")


def _normalize_effective_at(value: Any) -> str | None:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    parsed = parse_datetime(raw_value)
    if parsed is None:
        try:
            parsed = datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")
        except ValueError as exc:
            raise ValidationError("Укажите корректные дату и время операции.") from exc

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())

    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_item_form_options(catalog_service: CatalogService) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    categories_result = catalog_service.list_categories()
    units_result = catalog_service.list_units()
    categories = _normalize_categories(categories_result.data or []) if categories_result.ok else []
    units = _normalize_units(units_result.data or []) if units_result.ok else []
    return categories, units


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
    effective_at: str | None = None,
    default_unit_id: str | None = None,
) -> dict[str, Any]:
    default_site_id = fixed_operating_site_id or (operate_sites[0]["site_id"] if operate_sites else "")
    return {
        "operation_type": "RECEIVE",
        "site_id": default_site_id,
        "source_site_id": default_site_id,
        "destination_site_id": "",
        "issued_to_name": "",
        "notes": "",
        "effective_at": effective_at or "",
        "items": [],
        "default_unit_id": default_unit_id or "",
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
    destination_site_ids: set[int] | None = None,
    fixed_operating_site_id: int | None = None,
    default_unit_id: int | None = None,
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

    effective_at = _normalize_effective_at(draft_data.get("effective_at"))
    if effective_at:
        payload["effective_at"] = effective_at

    if operation_type == "MOVE":
        if fixed_operating_site_id is not None:
            source_site_id = fixed_operating_site_id
        if source_site_id not in operate_site_ids:
            raise ValidationError("Выберите склад-источник для операции перемещения.")
        allowed_destination_site_ids = destination_site_ids if destination_site_ids is not None else operate_site_ids
        if destination_site_id not in allowed_destination_site_ids:
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

    # Проверяем наличие временных строк для генерации client_request_id
    has_temporary_lines = any(
        str(item.get("kind") or "").strip().lower() == "temporary"
        for item in raw_items
    )
    if has_temporary_lines:
        # Генерируем client_request_id, если его ещё нет в черновике
        client_request_id = draft_data.get("client_request_id")
        if not client_request_id or not isinstance(client_request_id, str):
            client_request_id = str(uuid.uuid4())
        payload["client_request_id"] = client_request_id

    allow_negative_qty = operation_type == "ADJUSTMENT"
    line_number = 1
    seen_item_ids: set[int] = set()
    seen_temporary_keys: set[str] = set()

    for item in raw_items:
        kind = str(item.get("kind") or "").strip().lower()
        qty = _to_decimal_qty(item.get("quantity"))
        if qty is None:
            raise ValidationError("Количество должно быть числом с точностью до 3 знаков после запятой.")
        if qty == 0:
            raise ValidationError("Количество не может быть нулевым.")
        if not allow_negative_qty and qty < 0:
            raise ValidationError("Отрицательное количество разрешено только для корректировки.")

        # Определяем тип строки, если не указан явно
        if not kind:
            item_id = _to_int(item.get("item_id") or item.get("id"))
            if item_id is not None:
                kind = "catalog"
            else:
                # Проверяем наличие полей временной ТМЦ
                name = str(item.get("name") or "").strip()
                unit_id = _to_int(item.get("unit_id"))
                category_id = _to_int(item.get("category_id"))
                if name and unit_id is not None and category_id is not None:
                    kind = "temporary"
                else:
                    raise ValidationError("Не удалось определить тип строки. Укажите явно 'kind': 'catalog' или 'temporary'.")

        if kind == "catalog":
            item_id = _to_int(item.get("item_id") or item.get("id"))
            if item_id is None:
                raise ValidationError("В одной из каталожных строк не выбран ТМЦ.")
            if item_id in seen_item_ids:
                raise ValidationError("В черновике есть дублирующиеся строки ТМЦ. Обновите список и попробуйте снова.")
            seen_item_ids.add(item_id)
            payload["lines"].append(
                {
                    "line_number": line_number,
                    "item_id": item_id,
                    "qty": _serialize_decimal_qty(qty),
                }
            )
        elif kind == "temporary":
            # Проверяем обязательные поля для временной ТМЦ
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValidationError("Для временной ТМЦ укажите наименование.")
            unit_id = _to_int(item.get("unit_id"))
            if unit_id is None:
                unit_id = default_unit_id
            category_id = _to_int(item.get("category_id"))
            # category_id может быть None — это допустимо

            client_key = str(item.get("client_key") or "").strip()
            if not client_key:
                # Генерируем ключ, если не предоставлен
                client_key = f"tmp-{line_number}-{uuid.uuid4().hex[:8]}"
            if client_key in seen_temporary_keys:
                raise ValidationError("В черновике есть дублирующиеся временные строки. Обновите список и попробуйте снова.")
            seen_temporary_keys.add(client_key)

            temporary_item = {
                "client_key": client_key,
                "name": name,
                "sku": str(item.get("sku") or "").strip() or None,
                "unit_id": unit_id,
                "category_id": category_id,
                "description": str(item.get("description") or "").strip() or None,
            }
            payload["lines"].append(
                {
                    "line_number": line_number,
                    "temporary_item": temporary_item,
                    "qty": _serialize_decimal_qty(qty),
                }
            )
        else:
            raise ValidationError(f"Неизвестный тип строки: {kind}. Допустимые значения: 'catalog', 'temporary'.")

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


def _load_pending_acceptance_for_operation(
    assets_api: AssetsAPI,
    operation_id: str,
) -> dict[str, Any]:
    return assets_api.list_pending_acceptance_all_pages(
        filters={"operation_id": operation_id},
        max_rows=PENDING_ACCEPTANCE_PAGE_SIZE,
    )


def _get_post_list(request, field_name: str) -> list[str]:
    values = request.POST.getlist(field_name)
    if values:
        return values
    return request.POST.getlist(f"{field_name}[]")


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

        operation_documents: list[dict[str, Any]] = []
        try:
            operation_documents = [
                present_document(document)
                for document in DocumentsAPI(self.client).list_operation_documents(operation_id)
            ]
        except SyncServerAPIError as exc:
            messages.warning(request, str(exc) or "Не удалось загрузить печатные формы операции.")

        context = {
            "operation": presented_operation,
            "operation_documents": operation_documents,
            "submit_next_url": reverse("operations:detail", kwargs={"operation_id": operation_id}),
            "cancel_next_url": reverse("operations:detail", kwargs={"operation_id": operation_id}),
        }
        return render(request, self.template_name, context)


class OperationItemSearchView(SyncContextMixin, View):
    def get(self, request):
        service = OperationPageService(self.client, request=request)

        query = (request.GET.get("q") or "").strip()
        if len(query) < 2:
            return JsonResponse({"items": []})

        try:
            items = service.search_items(query, limit=12)
        except DatabaseError:
            logger.exception("Local catalog cache is not ready for item search.")
            return JsonResponse({"items": []})
        except SyncServerAPIError as exc:
            return JsonResponse({"items": [], "error": str(exc) or "?? ??????? ????????? ???."}, status=502)

        return JsonResponse({"items": items})


class OperationItemCreateView(SyncContextMixin, View):
    def post(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        if not operate_sites:
            return JsonResponse({"errors": {"__all__": ["Нет прав на создание операций."]}}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonResponse({"errors": {"__all__": ["Некорректный JSON-запрос."]}}, status=400)

        if not isinstance(payload, dict):
            return JsonResponse({"errors": {"__all__": ["Некорректный формат данных."]}}, status=400)

        # Загружаем списки категорий и единиц для валидации
        catalog_service = CatalogService(self.client)
        categories, units = _load_item_form_options(catalog_service)

        # Валидация обязательных полей временной ТМЦ
        errors = {}
        name = str(payload.get("name") or "").strip()
        if not name:
            errors["name"] = ["Укажите наименование."]

        unit_id = _to_int(payload.get("unit_id"))
        if unit_id is None:
            errors["unit_id"] = ["Выберите единицу измерения."]
        else:
            # Проверяем, что unit_id существует в списке единиц
            unit_exists = any(_to_int(unit.get("id")) == unit_id for unit in units)
            if not unit_exists:
                errors["unit_id"] = ["Выбранная единица измерения не найдена."]

        category_id = _to_int(payload.get("category_id"))
        if category_id is None:
            errors["category_id"] = ["Выберите категорию."]
        else:
            # Проверяем, что category_id существует в списке категорий
            category_exists = any(_to_int(cat.get("id")) == category_id for cat in categories)
            if not category_exists:
                errors["category_id"] = ["Выбранная категория не найдена."]

        if errors:
            return JsonResponse({"errors": errors}, status=400)

        # Дополнительные поля (необязательные)
        sku = str(payload.get("sku") or "").strip() or None
        description = str(payload.get("description") or "").strip() or None

        # Генерация client_key
        import uuid
        client_key = f"tmp-{uuid.uuid4().hex[:8]}"

        # Формируем объект временной ТМЦ
        temporary_item = {
            "client_key": client_key,
            "name": name,
            "sku": sku,
            "unit_id": unit_id,
            "category_id": category_id,
            "description": description,
        }

        # Возвращаем temporary_item для добавления в черновик операции
        return JsonResponse({"temporary_item": temporary_item}, status=201)


class OperationCreateView(SyncContextMixin, View):
    template_name = "operations/form.html"

    def get(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        destination_sites = service.get_all_sites()
        fixed_operating_site_id = service.get_fixed_operating_site_id()
        catalog_service = CatalogService(self.client)
        categories, units = _load_item_form_options(catalog_service)
        default_unit_id = find_default_unit_id(units)
        draft = _default_draft(
            operate_sites,
            fixed_operating_site_id=fixed_operating_site_id,
            effective_at=_current_local_datetime_value(),
            default_unit_id=default_unit_id,
        )
        form = OperationCreateForm(initial={"draft_payload": json.dumps(draft, ensure_ascii=False)})
        return render(
            request,
            self.template_name,
            self._build_context(
                service=service,
                form=form,
                draft=draft,
                operate_sites=operate_sites,
                destination_sites=destination_sites,
                fixed_operating_site_id=fixed_operating_site_id,
                item_categories=categories,
                item_units=units,
                default_item_unit_id=default_unit_id,
            ),
        )

    def post(self, request):
        service = OperationPageService(self.client, request=request)
        operate_sites = _safe_get_operate_sites(service, request)
        destination_sites = service.get_all_sites()
        fixed_operating_site_id = service.get_fixed_operating_site_id()
        form = OperationCreateForm(request.POST)
        catalog_service = CatalogService(self.client)
        categories, units = _load_item_form_options(catalog_service)
        default_unit_id = find_default_unit_id(units)
        draft = _default_draft(
            operate_sites,
            fixed_operating_site_id=fixed_operating_site_id,
            effective_at=_current_local_datetime_value(),
            default_unit_id=default_unit_id,
        )

        if form.is_valid():
            draft = form.parsed_payload
            try:
                payload = _build_create_payload(
                    draft,
                    operate_site_ids={int(site["site_id"]) for site in operate_sites},
                    destination_site_ids={int(site["site_id"]) for site in destination_sites},
                    fixed_operating_site_id=fixed_operating_site_id,
                    default_unit_id=_to_int(default_unit_id),
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
                    draft = _default_draft(
                        operate_sites,
                        fixed_operating_site_id=fixed_operating_site_id,
                        effective_at=_current_local_datetime_value(),
                        default_unit_id=default_unit_id,
                    )

        return render(
            request,
            self.template_name,
            self._build_context(
                service=service,
                form=form,
                draft=draft,
                operate_sites=operate_sites,
                destination_sites=destination_sites,
                fixed_operating_site_id=fixed_operating_site_id,
                item_categories=categories,
                item_units=units,
                default_item_unit_id=default_unit_id,
            ),
        )

    def _build_context(
        self,
        *,
        service: OperationPageService,
        form: OperationCreateForm,
        draft: dict[str, Any],
        operate_sites: list[dict[str, Any]],
        destination_sites: list[dict[str, Any]],
        fixed_operating_site_id: int | None,
        item_categories: list[dict[str, Any]],
        item_units: list[dict[str, Any]],
        default_item_unit_id: str | None,
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
            "destination_sites": destination_sites,
            "can_create_operations": bool(operate_sites),
            "operation_type_options": service.operation_type_options(),
            "item_search_url": reverse("operations:item_search"),
            "item_create_url": reverse("operations:item_create"),
            "can_choose_source_site": service.can_choose_source_site(),
            "fixed_operating_site": fixed_operating_site,
            "fixed_operating_site_id": fixed_operating_site_id or "",
            "item_categories": item_categories,
            "item_units": item_units,
            "default_item_unit_id": default_item_unit_id or "",
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

        # RECEIVE redirect: после submit отправляем пользователя на приёмку
        try:
            operation = OperationsAPI(self.client).get_operation(operation_id)
            op_type = str(operation.get("operation_type") or "").strip().upper()
            if op_type == "RECEIVE":
                return redirect("operations:acceptance_detail", operation_id=operation_id)
        except Exception:
            pass

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


# ------------------------------------------------------------------
# Pending acceptance list
# ------------------------------------------------------------------


class PendingAcceptanceListView(SyncContextMixin, TemplateView):
    template_name = "operations/pending_acceptance_list.html"

    def get(self, request, *args, **kwargs):
        search = request.GET.get("search") or ""
        site_id = request.GET.get("site_id") or ""
        op_type = request.GET.get("type") or ""
        page = max(_to_int(request.GET.get("page")) or 1, 1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)

        service = OperationPageService(self.client, request=request)
        assets_api = AssetsAPI(self.client)

        filters: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "search": search or None,
            "site_id": site_id or None,
        }

        page_data = {"items": [], "total_count": 0, "page": page, "page_size": page_size}
        try:
            page_data = assets_api.list_pending_acceptance(filters=filters)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось загрузить список ожидающих приёмки.")

        pending_rows = page_data.get("items", [])
        grouped = service.group_pending_rows(pending_rows)

        # Apply client-side type filter if requested
        if op_type:
            grouped = [op for op in grouped if op["operation_type"] == op_type.upper()]

        # Build site filter options from all available sites for dropdown
        all_sites = service.get_all_sites()
        available_sites = [
            {"id": site["site_id"], "name": site["name"]}
            for site in all_sites
        ]

        total_count = len(grouped)
        page_count = max((total_count + page_size - 1) // page_size, 1)

        context = {
            "groups": grouped,
            "search": search,
            "site_id": site_id,
            "type_filter": op_type,
            "page_size": page_size,
            "page": page,
            "total_count": total_count,
            "page_count": page_count,
            "has_prev": page > 1,
            "has_next": page < page_count,
            "prev_page": max(page - 1, 1),
            "next_page": min(page + 1, page_count),
            "available_sites": available_sites,
            "type_options": [
                {"code": "RECEIVE", "label": "Приход"},
                {"code": "MOVE", "label": "Перемещение"},
            ],
        }
        return render(request, self.template_name, context)


# ------------------------------------------------------------------
# Acceptance detail and submit
# ------------------------------------------------------------------


class AcceptanceDetailView(SyncContextMixin, TemplateView):
    template_name = "operations/acceptance_detail.html"

    def get(self, request, operation_id):
        service = OperationPageService(self.client, request=request)
        ops_api = OperationsAPI(self.client)
        assets_api = AssetsAPI(self.client)

        try:
            operation = ops_api.get_operation(operation_id)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                raise Http404("Операция не найдена.") from exc
            messages.error(request, str(exc) or "Не удалось загрузить операцию.")
            return redirect("operations:pending_acceptance")

        try:
            pending_data = _load_pending_acceptance_for_operation(assets_api, operation_id)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось загрузить строки приёмки.")
            pending_data = {"items": []}

        view_model = service.present_acceptance_detail(operation, pending_data.get("items", []))

        context = {
            "view_model": view_model,
            "operation_id": operation_id,
            "back_url": reverse("operations:pending_acceptance"),
        }
        return render(request, self.template_name, context)


class AcceptanceSubmitView(SyncContextMixin, View):
    def post(self, request, operation_id):
        service = OperationPageService(self.client, request=request)
        ops_api = OperationsAPI(self.client)
        assets_api = AssetsAPI(self.client)

        # Re-fetch pending rows to get current remaining quantities
        try:
            pending_data = _load_pending_acceptance_for_operation(assets_api, operation_id)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось загрузить актуальные данные приёмки.")
            return redirect("operations:acceptance_detail", operation_id=operation_id)

        pending_rows = pending_data.get("items", [])
        if not pending_rows:
            messages.warning(request, "Операция уже полностью обработана.")
            return redirect("operations:acceptance_detail", operation_id=operation_id)

        # Build remaining_by_line map
        remaining_by_line: dict[int | str, Decimal] = {}
        for row in pending_rows:
            line_id = row.get("operation_line_id") or row.get("line_id") or row.get("id")
            if line_id is None:
                continue
            expected = service._to_decimal(row.get("qty") or row.get("expected_qty") or 0) or Decimal("0")
            accepted = service._to_decimal(row.get("accepted_qty") or 0) or Decimal("0")
            lost = service._to_decimal(row.get("lost_qty") or 0) or Decimal("0")
            remaining = expected - accepted - lost
            if remaining > Decimal("0"):
                remaining_by_line[line_id] = remaining

        # Parse raw lines from POST
        raw_lines: list[dict[str, Any]] = []
        line_ids = _get_post_list(request, "line_id")
        line_numbers = _get_post_list(request, "line_number")
        if not line_ids:
            line_ids = line_numbers
        accepted_qtys = _get_post_list(request, "accepted_qty")
        lost_qtys = _get_post_list(request, "lost_qty")
        notes = _get_post_list(request, "note")

        for i, line_id in enumerate(line_ids):
            raw_lines.append({
                "line_id": _to_int(line_id),
                "line_number": line_numbers[i] if i < len(line_numbers) else line_id,
                "accepted_qty": accepted_qtys[i] if i < len(accepted_qtys) else "0",
                "lost_qty": lost_qtys[i] if i < len(lost_qtys) else "0",
                "note": notes[i] if i < len(notes) else "",
            })

        try:
            payload_lines = validate_acceptance_lines(
                raw_lines,
                remaining_by_line=remaining_by_line,
            )
        except ValidationError as exc:
            messages.error(request, exc.message)
            return redirect("operations:acceptance_detail", operation_id=operation_id)

        payload = {"lines": payload_lines}

        try:
            ops_api.accept_operation_lines(operation_id, payload)
            messages.success(request, "Приёмка выполнена.")
        except SyncServerAPIError as exc:
            if exc.status_code == 409:
                messages.error(request, "Конфликт данных: возможно, строки уже были приняты другим пользователем. Обновите страницу.")
            elif exc.status_code == 422:
                messages.error(request, f"Ошибка в данных приёмки: {exc}")
            elif exc.status_code == 403:
                messages.error(request, "У вас нет прав на приёмку этой операции.")
            else:
                messages.error(request, str(exc) or "Не удалось выполнить приёмку.")
            return redirect("operations:acceptance_detail", operation_id=operation_id)

        return redirect("operations:acceptance_detail", operation_id=operation_id)


# ------------------------------------------------------------------
# Lost assets list
# ------------------------------------------------------------------


class LostAssetsListView(SyncContextMixin, TemplateView):
    template_name = "operations/lost_assets_list.html"

    def get(self, request, *args, **kwargs):
        search = request.GET.get("search") or ""
        site_id = request.GET.get("site_id") or ""
        operation_id_filter = request.GET.get("operation_id") or ""
        page = max(_to_int(request.GET.get("page")) or 1, 1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)

        service = OperationPageService(self.client, request=request)
        assets_api = AssetsAPI(self.client)

        filters: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "search": search or None,
            "site_id": site_id or None,
            "operation_id": operation_id_filter or None,
        }

        page_data = {"items": [], "total_count": 0, "page": page, "page_size": page_size}
        try:
            page_data = assets_api.list_lost_assets(filters=filters)
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось загрузить список потерь.")

        lost_rows = page_data.get("items", [])
        presented = service.present_lost_assets_list(lost_rows)

        total_count = int(page_data.get("total_count") or 0)
        total_pages = max((total_count + page_size - 1) // page_size, 1)
        current_page = int(page_data.get("page") or page)

        # Build site filter options from all available sites for dropdown
        all_sites = service.get_all_sites()
        available_sites = [
            {"id": site["site_id"], "name": site["name"]}
            for site in all_sites
        ]

        context = {
            "items": presented,
            "search": search,
            "site_id": site_id,
            "operation_id_filter": operation_id_filter,
            "page_size": page_size,
            "page": current_page,
            "total_count": total_count,
            "page_count": total_pages,
            "has_prev": current_page > 1,
            "has_next": current_page < total_pages,
            "prev_page": max(current_page - 1, 1),
            "next_page": min(current_page + 1, total_pages),
            "available_sites": available_sites,
        }
        return render(request, self.template_name, context)


class LostAssetDetailView(SyncContextMixin, TemplateView):
    template_name = "operations/lost_asset_detail.html"

    def get(self, request, operation_line_id):
        service = OperationPageService(self.client, request=request)
        assets_api = AssetsAPI(self.client)

        try:
            lost_asset = assets_api.get_lost_asset(operation_line_id)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                raise Http404("Запись потери не найдена.") from exc
            messages.error(request, str(exc) or "Не удалось загрузить данные потери.")
            return redirect("operations:lost_assets")

        presented = service.present_lost_asset_detail(lost_asset)

        # Load recipients list for the resolve form
        recipients = []
        try:
            from apps.sync_client.recipients_api import RecipientsAPI
            recipients_api = RecipientsAPI(self.client)
            resp = recipients_api.list_recipients(filters={"per_page": 200})
            recipients = resp.get("items", []) if isinstance(resp, dict) else []
        except Exception:
            recipients = []

        context = {
            "item": presented,
            "operation_line_id": operation_line_id,
            "recipients": recipients,
            "back_url": reverse("operations:lost_assets"),
        }
        return render(request, self.template_name, context)


class LostAssetResolveView(SyncContextMixin, View):
    def post(self, request, operation_line_id):
        service = OperationPageService(self.client, request=request)
        assets_api = AssetsAPI(self.client)

        # Fetch current lost asset to get max_qty and has_source_site
        try:
            lost_asset = assets_api.get_lost_asset(operation_line_id)
        except SyncServerAPIError as exc:
            if exc.status_code == 404:
                messages.error(request, "Запись потери не найдена или уже разрешена.")
            else:
                messages.error(request, str(exc) or "Не удалось загрузить данные потери.")
            return redirect("operations:lost_assets")

        presented = service.present_lost_asset_detail(lost_asset)
        max_qty = service._to_decimal(lost_asset.get("qty") or lost_asset.get("lost_qty") or 0) or Decimal("0")

        try:
            payload = validate_lost_asset_resolve(
                {
                    "action": request.POST.get("action"),
                    "qty": request.POST.get("qty"),
                    "note": request.POST.get("note"),
                    "responsible_recipient_id": request.POST.get("responsible_recipient_id"),
                },
                max_qty=max_qty,
                has_source_site=presented["has_source_site"],
            )
        except ValidationError as exc:
            messages.error(request, exc.message)
            return redirect("operations:lost_asset_detail", operation_line_id=operation_line_id)

        try:
            assets_api.resolve_lost_asset(operation_line_id, payload)
            messages.success(request, "Потеря разрешена.")
        except SyncServerAPIError as exc:
            if exc.status_code == 409:
                messages.error(request, "Конфликт: потеря уже была разрешена другим пользователем.")
            elif exc.status_code == 422:
                messages.error(request, f"Ошибка в данных: {exc}")
            elif exc.status_code == 403:
                messages.error(request, "У вас нет прав на разрешение этой потери.")
            else:
                messages.error(request, str(exc) or "Не удалось разрешить потерю.")
            return redirect("operations:lost_asset_detail", operation_line_id=operation_line_id)

        return redirect("operations:lost_assets")
