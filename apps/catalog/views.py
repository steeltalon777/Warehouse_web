from __future__ import annotations

from copy import deepcopy

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.catalog.constants import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from apps.catalog.forms import CategoryForm, ItemForm, UnitForm
from apps.catalog.services import CatalogService
from apps.common.permissions import can_manage_catalog, can_use_client
from apps.sync_client.client import SyncServerClient


def _resolve_site_id(request) -> str:
    binding_site_id = ""
    try:
        binding_site_id = str(request.user.sync_binding.default_site_id or "").strip()
    except Exception:
        binding_site_id = ""

    return str(
        request.session.get("active_site")
        or request.session.get("sync_default_site_id")
        or request.session.get("site_id")
        or binding_site_id
        or getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")
        or ""
    ).strip()


def _build_catalog_service(request) -> CatalogService:
    client = SyncServerClient(
        user_id=request.user.id,
        site_id=_resolve_site_id(request) or None,
        request=request,
    )
    return CatalogService(client)


def _first_present(data: dict, *keys, default=None):
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _extract_parent_payload(category: dict) -> dict | None:
    parent = _first_present(category, "parent", "parent_category")
    if isinstance(parent, dict):
        return parent
    return None


def _extract_parent_id(category: dict) -> str | None:
    parent = _extract_parent_payload(category)
    if parent:
        nested_id = _first_present(
            parent,
            "id",
            "category_id",
            "parent_id",
            "parent_category_id",
        )
        if nested_id not in (None, "", 0, "0"):
            return str(nested_id)

    direct_parent_id = _first_present(category, "parent_id", "parent_category_id")
    if direct_parent_id not in (None, "", 0, "0"):
        return str(direct_parent_id)

    return None


def _extract_parent_name(category: dict) -> str:
    parent = _extract_parent_payload(category)
    if parent:
        return str(_first_present(parent, "name", "title", "label", default="")).strip()

    return str(
        _first_present(
            category,
            "parent_name",
            "parent_category_name",
            default="",
        )
    ).strip()


def _normalize_category(category: dict) -> dict:
    raw = deepcopy(category)
    category_id = _first_present(raw, "id", "category_id")
    name = str(_first_present(raw, "name", "title", "label", default="")).strip()
    parent_id = _extract_parent_id(raw)
    parent_name = _extract_parent_name(raw)

    return {
        **raw,
        "id": str(category_id or ""),
        "name": name,
        "parent_id": parent_id,
        "parent_name": parent_name,
        "parent": _extract_parent_payload(raw) or (
            {"id": parent_id, "name": parent_name} if parent_id else None
        ),
    }


def _normalize_categories(categories: list[dict]) -> list[dict]:
    normalized = [_normalize_category(category) for category in categories if isinstance(category, dict)]
    normalized.sort(
        key=lambda item: (
            item.get("parent_name", "").lower(),
            item.get("name", "").lower(),
            item.get("id", ""),
        )
    )
    return normalized


def _is_uncategorized_category(category: dict) -> bool:
    code = str(category.get("code") or "").strip()
    name = str(category.get("name") or "").strip()
    return code == UNCATEGORIZED_CATEGORY_CODE or name == UNCATEGORIZED_CATEGORY_NAME


def _filter_manage_categories(categories: list[dict]) -> list[dict]:
    return [category for category in categories if not _is_uncategorized_category(category)]


def _normalize_item_payload(payload: dict, all_categories: list[dict]) -> tuple[dict, str | None]:
    normalized = dict(payload)
    if normalized.get("category_id") not in (None, ""):
        return normalized, None

    uncategorized = _find_uncategorized_category(all_categories)
    if not uncategorized or uncategorized.get("id") in (None, ""):
        return normalized, 'В SyncServer не найдена служебная категория "Без категории".'

    normalized["category_id"] = int(uncategorized["id"])
    return normalized, None


class CatalogHomeView(LoginRequiredMixin, TemplateView):
    template_name = "catalog/home.html"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class CatalogManageAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user) or not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")

        self.service = _build_catalog_service(request)
        return super().dispatch(request, *args, **kwargs)

    def _get_categories_flat(self) -> tuple[list[dict], object]:
        result = self.service.list_categories()
        if not result.ok:
            return [], result
        return _normalize_categories(result.data or []), result

    def _get_manage_categories_flat(self) -> tuple[list[dict], object]:
        categories, result = self._get_categories_flat()
        return _filter_manage_categories(categories), result


class CategoryListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_category_list.html"

    def get(self, request, *args, **kwargs):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            messages.error(request, result.form_error)

        return render(request, self.template_name, {"flat_categories": categories})


class CategoryCreateView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("nomenclature:category_list")

    def get(self, request):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            messages.error(request, result.form_error)

        initial = {}
        parent_id = (request.GET.get("parent_id") or "").strip()
        if parent_id:
            initial["parent_id"] = parent_id

        form = CategoryForm(initial=initial, category_choices=categories)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        categories, _ = self._get_manage_categories_flat()
        form = CategoryForm(request.POST, category_choices=categories)
        if form.is_valid():
            result = self.service.create_category(form.cleaned_data)
            if result.ok:
                messages.success(request, "Категория создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)

        return render(request, self.template_name, {"form": form, "mode": "create"})


class CategoryUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("nomenclature:category_list")

    def _get_category(self, pk: str):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            return None, result, categories

        for category in categories:
            if str(category["id"]) == str(pk):
                return category, result, categories
        return None, result, categories

    def get(self, request, pk):
        category, result, categories = self._get_category(pk)
        if category is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Категория не найдена")

        initial = {**category, "parent_id": category.get("parent_id") or ""}
        form = CategoryForm(
            initial=initial,
            category_choices=[c for c in categories if str(c["id"]) != str(pk)],
        )
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        _, _, categories = self._get_category(pk)
        form = CategoryForm(
            request.POST,
            category_choices=[c for c in categories if str(c["id"]) != str(pk)],
        )
        if form.is_valid():
            result = self.service.update_category(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "Категория обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("Категория не найдена")
            form.add_error(None, result.form_error)

        return render(request, self.template_name, {"form": form, "mode": "update"})


class CategoryDeleteView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_confirm_delete.html"
    success_url = reverse_lazy("nomenclature:category_list")

    def _get_category(self, pk: str):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            return None, result
        for category in categories:
            if str(category["id"]) == str(pk):
                return category, result
        return None, result

    def get(self, request, pk):
        category, result = self._get_category(pk)
        if category is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("РљР°С‚РµРіРѕСЂРёСЏ РЅРµ РЅР°Р№РґРµРЅР°")
        return render(request, self.template_name, {"category_id": pk})

    def post(self, request, pk):
        category, result = self._get_category(pk)
        if category is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("РљР°С‚РµРіРѕСЂРёСЏ РЅРµ РЅР°Р№РґРµРЅР°")
        result = self.service.update_category(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "Категория деактивирована.")
            return redirect(self.success_url)
        if result.not_found:
            raise Http404("Категория не найдена")
        messages.error(request, result.form_error)
        return render(request, self.template_name, {"category_id": pk})


class CategoryTreeView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/category_tree.html"

    def get(self, request, *args, **kwargs):
        return redirect("nomenclature:category_list")


class UnitListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_unit_list.html"

    def get(self, request, *args, **kwargs):
        result = self.service.list_units()
        if not result.ok:
            messages.error(request, result.form_error)
            units = []
        else:
            units = result.data
        return render(request, self.template_name, {"units": units})


class UnitCreateView(CatalogManageAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("nomenclature:unit_list")

    def get(self, request):
        return render(request, self.template_name, {"form": UnitForm(), "mode": "create"})

    def post(self, request):
        form = UnitForm(request.POST)
        if form.is_valid():
            result = self.service.create_unit(form.cleaned_data)
            if result.ok:
                messages.success(request, "Единица создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class UnitUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("nomenclature:unit_list")

    def _find_unit(self, pk: str):
        result = self.service.list_units()
        if not result.ok:
            return None, result
        for unit in result.data:
            if str(unit["id"]) == str(pk):
                return unit, result
        return None, None

    def get(self, request, pk):
        unit, result = self._find_unit(pk)
        if unit is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Единица не найдена")
        form = UnitForm(initial=unit)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        form = UnitForm(request.POST)
        if form.is_valid():
            result = self.service.update_unit(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "Единица обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("Единица не найдена")
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "update"})


class ItemListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_item_list.html"

    def get(self, request, *args, **kwargs):
        category_id = request.GET.get("category_id") or None
        search = request.GET.get("search") or None

        items_result = self.service.list_items(category_id=category_id, search=search)
        categories, categories_result = self._get_categories_flat()

        if not items_result.ok:
            messages.error(request, items_result.form_error)
            items = []
        else:
            items = items_result.data

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)

        return render(
            request,
            self.template_name,
            {
                "items": items,
                "categories": categories,
                "selected_category_id": category_id or "",
                "search": search or "",
            },
        )


class ItemCreateView(CatalogManageAccessMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("nomenclature:item_list")

    def _catalog_data(self):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_units()
        units = units_result.data if units_result.ok else []
        return categories, _filter_manage_categories(categories), units, categories_result, units_result

    def get(self, request):
        all_categories, form_categories, units, categories_result, units_result = self._catalog_data()
        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        form = ItemForm(categories=form_categories, units=units)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        _, form_categories, units, _, _ = self._catalog_data()
        form = ItemForm(request.POST, categories=form_categories, units=units)
        if form.is_valid():
            result = self.service.create_item(form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class ItemUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("nomenclature:item_list")

    def _find_item(self, pk: str):
        result = self.service.list_items()
        if not result.ok:
            return None, result
        for item in result.data:
            if str(item["id"]) == str(pk):
                return item, result
        return None, None

    def get(self, request, pk):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_units()
        units = units_result.data if units_result.ok else []

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        item, result = self._find_item(pk)
        if item is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("ТМЦ не найдена")

        form = ItemForm(initial=item, categories=_filter_manage_categories(categories), units=units)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        _, form_categories, units, _, _ = self._catalog_data()
        form = ItemForm(request.POST, categories=form_categories, units=units)
        if form.is_valid():
            result = self.service.update_item(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("ТМЦ не найдена")
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def _catalog_data(self):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_units()
        units = units_result.data if units_result.ok else []

        if not categories_result.ok:
            messages.error(self.request, categories_result.form_error)
        if not units_result.ok:
            messages.error(self.request, units_result.form_error)

        return categories, _filter_manage_categories(categories), units, categories_result, units_result


class ItemDeactivateView(CatalogManageAccessMixin, View):
    success_url = reverse_lazy("nomenclature:item_list")

    def post(self, request, pk):
        result = self.service.update_item(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "ТМЦ деактивирована.")
        elif result.not_found:
            raise Http404("ТМЦ не найдена")
        else:
            messages.error(request, result.form_error)
        return redirect(self.success_url)
