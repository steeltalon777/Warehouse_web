from __future__ import annotations

from copy import deepcopy
from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, FileResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.catalog_cache.services import CatalogCacheSyncService
from apps.catalog.constants import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from apps.catalog.forms import CategoryForm, ItemForm, UnitForm, find_default_unit_id
from apps.catalog.services import CatalogService
from apps.catalog.tree import build_category_item_tree, normalize_tree_item
from apps.common.permissions import can_manage_catalog, can_use_client
from apps.sync_client.client import SyncServerClient
from apps.sync_client.exceptions import SyncServerAPIError


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


def _normalize_item(item: dict) -> dict:
    normalized_tree_item = normalize_tree_item(item)
    return {
        **item,
        **normalized_tree_item,
        "unit_name": str(item.get("unit_name") or item.get("unit") or "").strip(),
        "category_name": str(item.get("category_name") or "").strip(),
    }


def _normalize_items(items: list[dict]) -> list[dict]:
    normalized = [_normalize_item(item) for item in items if isinstance(item, dict)]
    normalized.sort(
        key=lambda item: (
            item.get("name", "").lower(),
            item.get("sku", "").lower(),
            item.get("id", ""),
        )
    )
    return normalized


def _normalize_units(units: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        normalized.append(
            {
                **unit,
                "id": str(_first_present(unit, "id", "unit_id", default="") or ""),
                "name": str(_first_present(unit, "name", "title", "label", default="")).strip(),
                "symbol": str(unit.get("symbol") or "").strip(),
            }
        )
    normalized.sort(
        key=lambda item: (
            item.get("name", "").lower(),
            item.get("symbol", "").lower(),
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


def _matches_item_search(item: dict, search: str) -> bool:
    search_term = search.casefold()
    if search_term in str(item.get("name") or "").casefold():
        return True
    if search_term in str(item.get("sku") or "").casefold():
        return True
    for tag in item.get("hashtags") or []:
        if search_term in str(tag).casefold():
            return True
    return False


def _matches_unit_search(unit: dict, search: str) -> bool:
    search_term = search.casefold()
    return (
        search_term in str(unit.get("name") or "").casefold()
        or search_term in str(unit.get("symbol") or "").casefold()
    )


def _parse_page(raw_value, *, default: int = 1) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_page_size(raw_value, *, default: int = 20) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(value, 1), 100)


def _build_manage_pagination(
    request,
    *,
    total_count: int,
    page: int,
    page_size: int,
    page_key: str = "page",
) -> dict:
    total_pages = max(1, ceil(total_count / page_size)) if page_size else 1
    page = min(max(page, 1), total_pages)
    window_start = max(1, page - 2)
    window_end = min(total_pages, page + 2)

    def build_url(page_number: int) -> str:
        query = request.GET.copy()
        query[page_key] = str(page_number)
        query["page_size"] = str(page_size)
        return f"?{query.urlencode()}"

    return {
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_url": build_url(page - 1) if page > 1 else "",
        "next_url": build_url(page + 1) if page < total_pages else "",
        "pages": [
            {
                "number": page_number,
                "url": build_url(page_number),
                "current": page_number == page,
            }
            for page_number in range(window_start, window_end + 1)
        ],
    }


class CatalogHomeView(LoginRequiredMixin, TemplateView):
    template_name = "catalog/home.html"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return redirect("nomenclature:tree")


class CatalogManageAccessMixin(LoginRequiredMixin):
    page_size_options = [10, 20, 50, 100]

    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user) or not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")

        self.service = _build_catalog_service(request)
        return super().dispatch(request, *args, **kwargs)

    def _get_categories_flat(self) -> tuple[list[dict], object]:
        result = self.service.list_admin_categories()
        if not result.ok:
            return [], result
        return _normalize_categories(result.data or []), result

    def _get_manage_categories_flat(self) -> tuple[list[dict], object]:
        categories, result = self._get_categories_flat()
        return _filter_manage_categories(categories), result


class CatalogManageTreeMixin(CatalogManageAccessMixin):
    def _build_tree_context(
        self,
        request,
        *,
        selected_category_id: str | int | None = None,
        selected_item_id: str | int | None = None,
    ) -> dict:
        categories, categories_result = self._get_manage_categories_flat()
        items_result = self.service.browse_all_items()
        items = _normalize_items(items_result.data or []) if items_result.ok else []

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not items_result.ok:
            messages.error(request, items_result.form_error)

        selected_kind = None
        selected_id = None
        if selected_item_id not in (None, ""):
            selected_kind = "item"
            selected_id = str(selected_item_id)
        elif selected_category_id not in (None, ""):
            selected_kind = "category"
            selected_id = str(selected_category_id)

        tree_nodes = build_category_item_tree(
            categories=categories,
            items=items,
            category_url_builder=lambda category: reverse(
                "nomenclature:category_update",
                kwargs={"pk": int(category["id"])},
            ),
            item_url_builder=lambda item: reverse(
                "nomenclature:item_update",
                kwargs={"pk": int(item["id"])},
            ),
            category_delete_builder=lambda category: reverse(
                "nomenclature:category_delete",
                kwargs={"pk": int(category["id"])},
            ),
            item_delete_builder=lambda item: reverse(
                "nomenclature:item_delete",
                kwargs={"pk": int(item["id"])},
            ),
            selected_kind=selected_kind,
            selected_id=selected_id,
        )

        return {
            "tree_nodes": tree_nodes,
            "cache_sync_next_url": request.get_full_path(),
        }


class NomenclatureTreeView(CatalogManageTreeMixin, TemplateView):
    template_name = "catalog/home.html"

    def get(self, request, *args, **kwargs):
        return render(
            request,
            self.template_name,
            self._build_tree_context(request),
        )


class CategoryListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_category_list.html"

    def get(self, request, *args, **kwargs):
        search = (request.GET.get("search") or "").strip()
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            messages.error(request, result.form_error)

        if search:
            search_term = search.casefold()
            categories = [
                category
                for category in categories
                if search_term in str(category.get("name") or "").casefold()
            ]

        paginator = Paginator(categories, page_size)
        page_obj = paginator.get_page(page)

        return render(
            request,
            self.template_name,
            {
                "flat_categories": list(page_obj.object_list),
                "search": search,
                "page_size": page_size,
                "page_size_options": [10, 20, 50, 100],
                "pagination": _build_manage_pagination(
                    request,
                    total_count=paginator.count,
                    page=page_obj.number,
                    page_size=page_size,
                ),
            },
        )


class CatalogCacheSyncView(CatalogManageAccessMixin, View):
    success_url = reverse_lazy("nomenclature:tree")

    def post(self, request, *args, **kwargs):
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or str(self.success_url)

        try:
            stats = CatalogCacheSyncService().sync_items()
        except SyncServerAPIError as exc:
            messages.error(request, str(exc) or "Не удалось синхронизировать кэш номенклатуры.")
        except Exception:
            messages.error(request, "Не удалось синхронизировать кэш номенклатуры.")
        else:
            messages.success(
                request,
                "Кэш поиска операций обновлён: "
                f"страниц {stats.pages}, загружено {stats.fetched}, сохранено {stats.upserted}.",
            )

        return redirect(next_url)


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
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "create",
                "page_title": "Новая категория",
                "page_note": "Категория будет добавлена в общую иерархию номенклатуры.",
                "back_url": reverse("nomenclature:category_list"),
            },
        )

    def post(self, request):
        categories, _ = self._get_manage_categories_flat()
        form = CategoryForm(request.POST, category_choices=categories)
        if form.is_valid():
            result = self.service.create_category(form.cleaned_data)
            if result.ok:
                messages.success(request, "Категория создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "create",
                "page_title": "Новая категория",
                "page_note": "Категория будет добавлена в общую иерархию номенклатуры.",
                "back_url": reverse("nomenclature:category_list"),
            },
        )


class CategoryUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("nomenclature:category_list")

    def _get_category(self, pk: str):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            return None, result, categories

        category_result = self.service.get_category(str(pk))
        if not category_result.ok:
            return None, category_result, categories

        return _normalize_category(category_result.data or {}), category_result, categories

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
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование категории",
                "page_note": "Изменения применяются к общей иерархии номенклатуры.",
                "back_url": reverse("nomenclature:category_list"),
            },
        )

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

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование категории",
                "page_note": "Изменения применяются к общей иерархии номенклатуры.",
                "back_url": reverse("nomenclature:category_list"),
            },
        )


class CategoryDeleteView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_confirm_delete.html"
    success_url = reverse_lazy("nomenclature:category_list")

    def _get_category(self, pk: str):
        result = self.service.get_category(str(pk))
        if not result.ok:
            return None, result
        return _normalize_category(result.data or {}), result

    def _build_page_context(self, category_id: str | int, category: dict) -> dict:
        is_root = not category.get("parent_id")
        return {
            "category_id": category_id,
            "category_name": category.get("name") or "",
            "is_root": is_root,
            "page_title": "Удаление категории",
            "page_note": "Категория будет удалена через SyncServer API.",
            "back_url": reverse("nomenclature:category_list"),
        }

    def get(self, request, pk):
        category, result = self._get_category(pk)
        if category is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Категория не найдена")
        return render(
            request,
            self.template_name,
            self._build_page_context(pk, category),
        )

    def post(self, request, pk):
        category, result = self._get_category(pk)
        if category is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Категория не найдена")
        result = self.service.delete_category(str(pk))
        if result.ok:
            messages.success(request, "Категория удалена.")
            return redirect(self.success_url)
        if result.not_found:
            raise Http404("Категория не найдена")
        messages.error(request, result.form_error)
        return render(
            request,
            self.template_name,
            self._build_page_context(pk, category),
        )


class CategoryTreeView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/category_tree.html"

    def get(self, request, *args, **kwargs):
        return redirect("nomenclature:tree")


class UnitListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_unit_list.html"

    def get(self, request, *args, **kwargs):
        search = (request.GET.get("search") or "").strip()
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)
        result = self.service.list_admin_units()
        if not result.ok:
            messages.error(request, result.form_error)
            units = []
        else:
            units = _normalize_units(result.data or [])

        if search:
            units = [unit for unit in units if _matches_unit_search(unit, search)]

        paginator = Paginator(units, page_size)
        page_obj = paginator.get_page(page)
        return render(
            request,
            self.template_name,
            {
                "units": list(page_obj.object_list),
                "search": search,
                "page_size": page_size,
                "page_size_options": self.page_size_options,
                "pagination": _build_manage_pagination(
                    request,
                    total_count=paginator.count,
                    page=page_obj.number,
                    page_size=page_size,
                ),
            },
        )


class UnitCreateView(CatalogManageAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("nomenclature:unit_list")

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                "form": UnitForm(),
                "mode": "create",
                "page_title": "Новая единица измерения",
                "page_note": "Создайте единицу, которая будет доступна в карточках ТМЦ.",
                "back_url": reverse("nomenclature:unit_list"),
            },
        )

    def post(self, request):
        form = UnitForm(request.POST)
        if form.is_valid():
            result = self.service.create_unit(form.cleaned_data)
            if result.ok:
                messages.success(request, "Единица создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "create",
                "page_title": "Новая единица измерения",
                "page_note": "Создайте единицу, которая будет доступна в карточках ТМЦ.",
                "back_url": reverse("nomenclature:unit_list"),
            },
        )


class UnitUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("nomenclature:unit_list")

    def _find_unit(self, pk: str):
        result = self.service.get_unit(str(pk))
        if not result.ok:
            return None, result
        return result.data, result

    def get(self, request, pk):
        unit, result = self._find_unit(pk)
        if unit is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Единица не найдена")
        form = UnitForm(initial=unit)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование единицы измерения",
                "page_note": "Изменения сразу отражаются в справочнике единиц измерения.",
                "back_url": reverse("nomenclature:unit_list"),
            },
        )

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
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование единицы измерения",
                "page_note": "Изменения сразу отражаются в справочнике единиц измерения.",
                "back_url": reverse("nomenclature:unit_list"),
            },
        )


class UnitDeleteView(CatalogManageAccessMixin, View):
    success_url = reverse_lazy("nomenclature:unit_list")

    def post(self, request, pk):
        result = self.service.delete_unit(str(pk))
        if result.ok:
            messages.success(request, "Единица удалена.")
        elif result.not_found:
            raise Http404("Единица не найдена")
        else:
            messages.error(request, result.form_error)
        return redirect(self.success_url)


class ItemListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/manage_item_list.html"

    def get(self, request, *args, **kwargs):
        category_id = (request.GET.get("category_id") or "").strip() or None
        search = (request.GET.get("search") or "").strip()
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = _parse_page_size(request.GET.get("page_size"), default=20)

        items_result = self.service.list_admin_items()
        categories, categories_result = self._get_categories_flat()
        categories_by_id = {str(category.get("id")): category for category in categories}

        if not items_result.ok:
            messages.error(request, items_result.form_error)
            items = []
        else:
            raw_items = []
            for item in items_result.data or []:
                category = categories_by_id.get(str(item.get("category_id")))
                raw_items.append(
                    {
                        **item,
                        "category_name": (category or {}).get("name", ""),
                    }
                )
            items = _normalize_items(raw_items)

        if category_id:
            items = [item for item in items if str(item.get("category_id")) == str(category_id)]

        if search:
            items = [item for item in items if _matches_item_search(item, search)]

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)

        paginator = Paginator(items, page_size)
        page_obj = paginator.get_page(page)
        create_item_url = reverse("nomenclature:item_create")
        if category_id:
            create_item_url = f"{create_item_url}?category_id={category_id}"

        return render(
            request,
            self.template_name,
            {
                "items": list(page_obj.object_list),
                "categories": _filter_manage_categories(categories),
                "selected_category_id": category_id or "",
                "search": search,
                "page_size": page_size,
                "page_size_options": self.page_size_options,
                "create_item_url": create_item_url,
                "pagination": _build_manage_pagination(
                    request,
                    total_count=paginator.count,
                    page=page_obj.number,
                    page_size=page_size,
                ),
            },
        )


class ItemFormCatalogMixin(CatalogManageAccessMixin):
    def _catalog_data(self):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_admin_units()
        units = _normalize_units(units_result.data or []) if units_result.ok else []
        return categories, _filter_manage_categories(categories), units, categories_result, units_result

    @staticmethod
    def _default_unit_id(units: list[dict]) -> str | None:
        return find_default_unit_id(units)


class ItemCreateView(ItemFormCatalogMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("nomenclature:item_list")

    def get(self, request):
        _, form_categories, units, categories_result, units_result = self._catalog_data()
        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        initial = {}
        category_id = (request.GET.get("category_id") or "").strip()
        if category_id:
            initial["category_id"] = category_id
        default_unit_id = self._default_unit_id(units)
        if default_unit_id:
            initial["unit_id"] = default_unit_id

        form = ItemForm(initial=initial, categories=form_categories, units=units)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "create",
                "page_title": "Новая ТМЦ",
                "page_note": "Заполните карточку и при необходимости выберите категорию через поиск.",
                "back_url": reverse("nomenclature:item_list"),
            },
        )

    def post(self, request):
        _, form_categories, units, _, _ = self._catalog_data()
        form = ItemForm(request.POST, categories=form_categories, units=units)
        if form.is_valid():
            result = self.service.create_item(form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "create",
                "page_title": "Новая ТМЦ",
                "page_note": "Заполните карточку и при необходимости выберите категорию через поиск.",
                "back_url": reverse("nomenclature:item_list"),
            },
        )


class ItemUpdateView(ItemFormCatalogMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("nomenclature:item_list")

    def _find_item(self, pk: str):
        result = self.service.get_item(str(pk))
        if not result.ok:
            return None, result
        return result.data, result

    def get(self, request, pk):
        categories, form_categories, units, categories_result, units_result = self._catalog_data()

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
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование ТМЦ",
                "page_note": "Измените карточку ТМЦ на отдельной форме.",
                "back_url": reverse("nomenclature:item_list"),
            },
        )

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
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "mode": "update",
                "page_title": "Редактирование ТМЦ",
                "page_note": "Измените карточку ТМЦ на отдельной форме.",
                "back_url": reverse("nomenclature:item_list"),
            },
        )


class ItemDeactivateView(CatalogManageAccessMixin, View):
    success_url = reverse_lazy("nomenclature:item_list")

    def post(self, request, pk):
        result = self.service.delete_item(str(pk))
        if result.ok:
            messages.success(request, "ТМЦ удалена.")
        elif result.not_found:
            raise Http404("ТМЦ не найдена")
        else:
            messages.error(request, result.form_error)
        return redirect(self.success_url)


class ItemMergeView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/item_merge.html"

    def get(self, request, *args, **kwargs):
        items_result = self.service.list_admin_items()
        items = _normalize_items(items_result.data or []) if items_result.ok else []
        if not items_result.ok:
            messages.error(request, items_result.form_error)
        return render(
            request,
            self.template_name,
            {
                "items": items,
                "source_item_id": (request.GET.get("source_item_id") or "").strip(),
                "target_item_id": (request.GET.get("target_item_id") or "").strip(),
            },
        )

    def post(self, request, *args, **kwargs):
        source_id = (request.POST.get("source_item_id") or "").strip()
        target_id = (request.POST.get("target_item_id") or "").strip()
        comment = (request.POST.get("comment") or "").strip() or None
        if not source_id or not target_id:
            messages.error(request, "Выберите source и target ТМЦ.")
            return self.get(request, *args, **kwargs)

        result = self.service.merge_items(source_id, target_id, comment=comment)
        if result.ok:
            messages.success(request, "ТМЦ успешно объединены.")
            return redirect("nomenclature:item_list")

        messages.error(request, result.form_error)
        return self.get(request, *args, **kwargs)


class CategoryMergeView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/category_merge.html"

    def get(self, request, *args, **kwargs):
        categories, result = self._get_manage_categories_flat()
        if not result.ok:
            messages.error(request, result.form_error)
        return render(
            request,
            self.template_name,
            {
                "categories": categories,
                "source_category_id": (request.GET.get("source_category_id") or "").strip(),
                "target_category_id": (request.GET.get("target_category_id") or "").strip(),
            },
        )

    def post(self, request, *args, **kwargs):
        source_id = (request.POST.get("source_category_id") or "").strip()
        target_id = (request.POST.get("target_category_id") or "").strip()
        comment = (request.POST.get("comment") or "").strip() or None
        if not source_id or not target_id:
            messages.error(request, "Выберите source и target категорию.")
            return self.get(request, *args, **kwargs)

        result = self.service.merge_categories(source_id, target_id, comment=comment)
        if result.ok:
            messages.success(request, "Категории успешно объединены.")
            return redirect("nomenclature:category_list")

        messages.error(request, result.form_error)
        return self.get(request, *args, **kwargs)


class ItemSplitView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/item_split.html"

    def get(self, request, pk: int, *args, **kwargs):
        item_result = self.service.get_item(str(pk))
        if not item_result.ok:
            messages.error(request, item_result.form_error)
            raise Http404("ТМЦ не найдена")
        categories, _ = self._get_manage_categories_flat()
        units_result = self.service.list_admin_units()
        units = _normalize_units(units_result.data or []) if units_result.ok else []
        balances_result = self.service.get_item_balances(pk)
        balances = balances_result.data if balances_result.ok and isinstance(balances_result.data, list) else []
        normalized_balances = []
        for row in balances:
            if not isinstance(row, dict):
                continue
            qty = str(row.get("qty") or row.get("quantity") or "0")
            normalized_balances.append(
                {
                    "site_id": row.get("site_id"),
                    "site_name": row.get("site_name") or f"Склад {row.get('site_id')}",
                    "qty": qty,
                }
            )
        return render(
            request,
            self.template_name,
            {
                "source_item": _normalize_item(item_result.data or {}),
                "categories": categories,
                "units": units,
                "balances": normalized_balances,
            },
        )

    def post(self, request, pk: int, *args, **kwargs):
        source_result = self.service.get_item(str(pk))
        if not source_result.ok:
            messages.error(request, source_result.form_error)
            raise Http404("ТМЦ не найдена")

        site_ids = request.POST.getlist("site_id")
        qtys = request.POST.getlist("qty")
        site_quantities: list[dict] = []
        for site_id, qty in zip(site_ids, qtys, strict=False):
            site_id_val = (site_id or "").strip()
            qty_val = (qty or "").strip()
            if not site_id_val or not qty_val:
                continue
            site_quantities.append({"site_id": int(site_id_val), "qty": qty_val})

        payload = {
            "source_item_id": int(pk),
            "target_item": {
                "sku": (request.POST.get("sku") or "").strip() or None,
                "name": (request.POST.get("name") or "").strip(),
                "category_id": int(request.POST.get("category_id")),
                "unit_id": int(request.POST.get("unit_id")),
                "description": (request.POST.get("description") or "").strip() or None,
            },
            "site_quantities": site_quantities,
            "comment": (request.POST.get("comment") or "").strip() or None,
        }

        result = self.service.split_item(payload)
        if result.ok:
            messages.success(request, "ТМЦ успешно разделена: новая позиция создана.")
            return redirect("nomenclature:item_list")

        messages.error(request, result.form_error)
        return self.get(request, pk, *args, **kwargs)


# ---------------------------------------------------------------------------
# Angular SPA shell (Phase 1: Django as host)
# ---------------------------------------------------------------------------

import re
from pathlib import Path
from html.parser import HTMLParser


class _AngularIndexParser(HTMLParser):
    """Extract <style>, <link rel=stylesheet>, <script> from Angular index.html.

    When ``asset_prefix`` is set (e.g. ``"/nomenclature"``), asset URLs are
    prefixed so the browser resolves them independently of the page location.
    When empty, relative URLs from index.html are kept as-is (they resolve
    against the page URL at runtime).
    """

    def __init__(self, asset_prefix: str = "") -> None:
        super().__init__()
        self.asset_prefix = asset_prefix
        self.inline_styles: list[str] = []
        self.css_links: list[str] = []
        self.scripts: list[str] = []
        self._capture_style = False
        self._style_data: list[str] = []

    def _asset_url(self, relative_path: str) -> str:
        if self.asset_prefix:
            return f"{self.asset_prefix}/{relative_path}"
        return relative_path

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "style" and attr_dict.get("media") != "print":
            self._capture_style = True
            self._style_data = []
        elif tag == "link" and attr_dict.get("rel") == "stylesheet":
            href = attr_dict.get("href", "")
            if href:
                self.css_links.append(self._asset_url(href))
        elif tag == "script" and attr_dict.get("type") == "module":
            src = attr_dict.get("src", "")
            if src:
                self.scripts.append(self._asset_url(src))

    def handle_data(self, data: str) -> None:
        if getattr(self, "_capture_style", False):
            self._style_data.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and getattr(self, "_capture_style", False):
            self.inline_styles.append("".join(self._style_data))
            self._capture_style = False


class AngularStaticFilesView(View):
    """Serves built Angular assets from ``FRONTEND_BUILD_DIR``.

    Mounted at root level so that ``<base href="/">`` in the SPA template
    resolves chunk/asset URLs against the root of the domain.
    """

    _FILE_RE = re.compile(r"\.(?:js|css|ico|png|jpg|jpeg|svg|gif|woff2?|ttf|eot|json|map)$")

    _MIME: dict[str, str] = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".ico": "image/x-icon",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".gif": "image/gif",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
        ".json": "application/json",
        ".map": "application/json",
    }

    @property
    def dist_dir(self) -> Path:
        return Path(settings.FRONTEND_BUILD_DIR)

    def get(self, request, path: str) -> HttpResponse:
        dist = self.dist_dir
        if not self._FILE_RE.search(path):
            raise Http404

        file_path = (dist / path).resolve()
        if not str(file_path).startswith(str(dist.resolve())):
            raise Http404
        if not file_path.exists() or not file_path.is_file():
            raise Http404

        content_type = self._MIME.get(file_path.suffix, "application/octet-stream")
        return FileResponse(file_path.open("rb"), content_type=content_type)


class _AngularSpaServeMixin:
    """Mixin that renders the Angular SPA template with injected assets.

    Subclasses must set:
    - ``template_name`` — Django template path
    - ``asset_prefix`` — URL prefix for assets (e.g. ``"/nomenclature"``) or ``""``
    """

    template_name: str = ""
    asset_prefix: str = ""

    def _render_spa(self, request) -> HttpResponse:
        dist = Path(settings.FRONTEND_BUILD_DIR)
        index_path = dist / "index.html"
        if not index_path.exists():
            raise Http404(
                "Angular build not found. "
                "Run 'npm run build' in Warehouse_frontend."
            )

        index_html = index_path.read_text(encoding="utf-8")
        parser = _AngularIndexParser(asset_prefix=self.asset_prefix)
        parser.feed(index_html)

        return render(request, self.template_name, {
            "spa_inline_styles": "\n".join(parser.inline_styles),
            "spa_css": parser.css_links[0] if parser.css_links else None,
            "spa_scripts": parser.scripts,
        })


class _CatalogSpaAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class _NomenclatureSpaAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")
        if not can_manage_catalog(request.user):
            return redirect("/catalog/")
        return super().dispatch(request, *args, **kwargs)


class NomenclatureSPAView(LoginRequiredMixin, _NomenclatureSpaAccessMixin, _AngularSpaServeMixin, View):
    """Serves the Angular SPA for /nomenclature/.

    File requests (js, css, etc.) are served from the build directory.
    Everything else renders the Django template with the SPA shell.
    """

    template_name = "catalog/nomenclature_spa.html"
    asset_prefix = ""

    def get(self, request, path: str = "") -> HttpResponse:
        dist = Path(settings.FRONTEND_BUILD_DIR)

        if path:
            file_path = (dist / path).resolve()
            if str(file_path).startswith(str(dist.resolve())) and file_path.exists() and file_path.is_file():
                content_type = {
                    ".js": "application/javascript",
                    ".css": "text/css",
                    ".ico": "image/x-icon",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".gif": "image/gif",
                    ".woff": "font/woff",
                    ".woff2": "font/woff2",
                    ".ttf": "font/ttf",
                    ".eot": "application/vnd.ms-fontobject",
                    ".json": "application/json",
                    ".map": "application/json",
                }.get(file_path.suffix, "application/octet-stream")

                return FileResponse(file_path.open("rb"), content_type=content_type)

        return self._render_spa(request)


class OperationsSPAView(LoginRequiredMixin, _AngularSpaServeMixin, View):
    """Serves the Angular SPA for /operations/.

    This view only renders the SPA template. Static file requests are
    handled by ``AngularStaticFilesView`` at root level.
    """

    template_name = "catalog/operations_spa.html"
    asset_prefix = ""

    def get(self, request, path: str = "") -> HttpResponse:
        return self._render_spa(request)


class TemporaryItemsSPAView(LoginRequiredMixin, _AngularSpaServeMixin, View):
    """Serves the Angular SPA for /temporary-items/.

    Static file requests are handled by AngularStaticFilesView at root level.
    """

    template_name = "catalog/temp_items_spa.html"
    asset_prefix = ""

    def get(self, request, path: str = "") -> HttpResponse:
        return self._render_spa(request)


class IssuedAssetsSPAView(LoginRequiredMixin, _AngularSpaServeMixin, View):
    """Serves the Angular SPA for /issued-assets/.

    Static file requests are handled by AngularStaticFilesView at root level.
    """

    template_name = "catalog/issued_assets_spa.html"
    asset_prefix = ""

    def get(self, request, path: str = "") -> HttpResponse:
        return self._render_spa(request)


class CatalogSPAView(LoginRequiredMixin, _CatalogSpaAccessMixin, _AngularSpaServeMixin, View):
    """Serves the Angular SPA for /catalog/.

    Static file requests are handled by AngularStaticFilesView at root level.
    """

    template_name = "catalog/catalog_spa.html"
    asset_prefix = ""

    def get(self, request, path: str = "") -> HttpResponse:
        return self._render_spa(request)
