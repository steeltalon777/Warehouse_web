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

from apps.catalog.forms import CategoryForm, ItemForm, UnitForm
from apps.catalog.services import CatalogService
from apps.common.permissions import can_manage_catalog, can_use_client
from apps.sync_client.client import SyncServerClient


def _resolve_site_id(request):
    return (
        request.session.get("active_site")
        or request.session.get("sync_default_site_id")
        or request.session.get("site_id")
        or getattr(settings, "SYNC_DEFAULT_ACTING_SITE_ID", "")
    )


def _build_catalog_service(request) -> CatalogService:
    site_id = _resolve_site_id(request)
    client = SyncServerClient(
        user_id=request.user.id,
        site_id=site_id,
        request=request,
    )
    return CatalogService(client)


def _first_present(data: dict, *keys, default=None):
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _normalize_scalar_id(value):
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, dict):
        nested = _first_present(
            value,
            "id",
            "category_id",
            "parent_id",
            "parent_category_id",
        )
        return str(nested) if nested not in (None, "", 0, "0") else None
    return str(value)


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

    direct_parent_id = _first_present(
        category,
        "parent_id",
        "parent_category_id",
    )
    if direct_parent_id not in (None, "", 0, "0"):
        return str(direct_parent_id)

    return None


def _extract_parent_name(category: dict) -> str:
    parent = _extract_parent_payload(category)
    if parent:
        return str(
            _first_present(parent, "name", "title", "label", default="")
        ).strip()

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
    if category_id in (None, ""):
        category_id = ""

    name = str(_first_present(raw, "name", "title", "label", default="")).strip()
    parent_id = _extract_parent_id(raw)
    parent_name = _extract_parent_name(raw)

    normalized = {
        **raw,
        "id": str(category_id),
        "name": name,
        "parent_id": parent_id,
        "parent_name": parent_name,
        "children": [],
        "_raw": raw,
    }

    parent_payload = _extract_parent_payload(raw)
    if parent_payload:
        normalized["parent"] = parent_payload
    elif parent_id:
        normalized["parent"] = {
            "id": parent_id,
            "name": parent_name,
        }
    else:
        normalized["parent"] = None

    return normalized


def _normalize_categories(categories: list[dict]) -> list[dict]:
    normalized = [_normalize_category(category) for category in categories if isinstance(category, dict)]
    by_id = {category["id"]: category for category in normalized if category.get("id")}

    for category in normalized:
        if category["parent_id"] and not category["parent_name"]:
            parent = by_id.get(category["parent_id"])
            if parent:
                category["parent_name"] = parent.get("name", "")
                category["parent"] = {
                    "id": parent["id"],
                    "name": parent.get("name", ""),
                }

    normalized.sort(
        key=lambda x: (
            x.get("parent_id") is not None,
            x.get("parent_name", "").lower(),
            x.get("name", "").lower(),
            x.get("id", ""),
        )
    )
    return normalized


def _build_category_tree_from_flat(categories: list[dict]) -> list[dict]:
    normalized = [_normalize_category(category) for category in categories if isinstance(category, dict)]
    nodes = {}

    for category in normalized:
        node = {**category, "children": []}
        nodes[category["id"]] = node

    roots = []

    for category in normalized:
        node = nodes[category["id"]]
        parent_id = category.get("parent_id")

        if parent_id and parent_id in nodes and parent_id != category["id"]:
            parent_node = nodes[parent_id]
            node["parent_name"] = node.get("parent_name") or parent_node.get("name", "")
            node["parent"] = {
                "id": parent_node.get("id"),
                "name": parent_node.get("name", ""),
            }
            parent_node.setdefault("children", []).append(node)
        else:
            roots.append(node)

    def _sort_branch(branch: list[dict]):
        branch.sort(key=lambda x: (x.get("name", "").lower(), x.get("id", "")))
        for item in branch:
            children = item.get("children") or []
            if children:
                _sort_branch(children)

    _sort_branch(roots)
    return roots


def _flatten_tree(tree: list[dict]) -> list[dict]:
    result = []

    def _walk(nodes: list[dict], parent: dict | None = None):
        for node in nodes:
            normalized = _normalize_category(node)
            children = node.get("children") or normalized.get("children") or []

            if parent and not normalized.get("parent_id"):
                normalized["parent_id"] = parent.get("id")
                normalized["parent_name"] = parent.get("name", "")
                normalized["parent"] = {
                    "id": parent.get("id"),
                    "name": parent.get("name", ""),
                }

            result.append(normalized)
            if children:
                _walk(children, normalized)

    _walk(tree)
    return _normalize_categories(result)


def _looks_like_tree_payload(data) -> bool:
    if not isinstance(data, list) or not data:
        return False
    return any(isinstance(item, dict) and "children" in item for item in data)


class CatalogHomeView(LoginRequiredMixin, TemplateView):
    template_name = "catalog/home.html"

    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class CatalogReadAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")

        site_id = _resolve_site_id(request)
        if not site_id:
            messages.error(request, "Не выбран активный склад для работы со справочниками.")
            return redirect("catalog:home")

        self.service = _build_catalog_service(request)
        return super().dispatch(request, *args, **kwargs)

    def _get_categories_flat(self) -> tuple[list[dict], object]:
        result = self.service.list_categories()
        if not result.ok:
            return [], result
        return _normalize_categories(result.data or []), result

    def _get_categories_tree(self) -> tuple[list[dict], object]:
        tree_result = self.service.categories_tree()
        if tree_result.ok and isinstance(tree_result.data, list):
            if _looks_like_tree_payload(tree_result.data):
                return tree_result.data, tree_result

            flat_from_tree = _normalize_categories(tree_result.data)
            if flat_from_tree:
                return _build_category_tree_from_flat(flat_from_tree), tree_result

        flat_categories, flat_result = self._get_categories_flat()
        if flat_result.ok:
            return _build_category_tree_from_flat(flat_categories), flat_result

        return [], tree_result if not tree_result.ok else flat_result


class CatalogManageAccessMixin(CatalogReadAccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


def _find_category_in_tree(nodes: list[dict], category_id: str) -> dict | None:
    for node in nodes:
        if str(node.get("id")) == str(category_id):
            return node
        children = node.get("children") or []
        found = _find_category_in_tree(children, category_id)
        if found is not None:
            return found
    return None


def _filter_category_tree(nodes: list[dict], term: str) -> list[dict]:
    if not term:
        return nodes

    lowered = term.lower()
    filtered: list[dict] = []
    for node in nodes:
        children = node.get("children") or []
        filtered_children = _filter_category_tree(children, term)
        haystack = f'{node.get("name", "")} {node.get("code", "")}'.lower()
        if lowered in haystack or filtered_children:
            filtered.append({**node, "children": filtered_children})
    return filtered


def _flatten_category_ids(nodes: list[dict]) -> list[str]:
    result: list[str] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id:
            result.append(node_id)
        result.extend(_flatten_category_ids(node.get("children") or []))
    return result


class CategoryListView(CatalogReadAccessMixin, TemplateView):
    template_name = "catalog/category_list.html"

    def get(self, request, *args, **kwargs):
        tree, result = self._get_categories_tree()
        if not result.ok:
            messages.error(request, result.form_error)

        search = (request.GET.get("search") or "").strip()
        filtered_tree = _filter_category_tree(tree, search)
        flat_categories = _flatten_tree(tree)
        visible_ids = set(_flatten_category_ids(filtered_tree))
        visible_categories = [
            category for category in flat_categories
            if category.get("id") in visible_ids
        ] if search else flat_categories

        selected_id = str(request.GET.get("category_id") or "").strip()
        selected_category = _find_category_in_tree(tree, selected_id) if selected_id else None
        if selected_category is None and visible_categories:
            selected_category = visible_categories[0]

        create_initial = {"is_active": True}
        if selected_category is not None:
            create_initial["parent_id"] = selected_category.get("id")

        return render(
            request,
            self.template_name,
            {
                "categories": filtered_tree,
                "flat_categories": flat_categories,
                "selected_category": selected_category,
                "selected_category_id": str(selected_category.get("id")) if selected_category else "",
                "search": search,
                "site_context_id": _resolve_site_id(request),
                "catalog_is_global": True,
                "can_manage_catalog": can_manage_catalog(request.user),
                "create_form": CategoryForm(
                    initial=create_initial,
                    category_choices=flat_categories,
                ),
            },
        )


class CategoryCreateView(CatalogManageAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:category_list")

    def get(self, request):
        categories, result = self._get_categories_flat()
        if not result.ok:
            messages.error(request, result.form_error)

        initial = {}
        parent_id = (request.GET.get("parent_id") or "").strip()
        if parent_id:
            initial["parent_id"] = parent_id

        form = CategoryForm(initial=initial, category_choices=categories)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        categories, _ = self._get_categories_flat()

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
    success_url = reverse_lazy("catalog:category_list")

    def _get_category(self, pk: str):
        categories, result = self._get_categories_flat()
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

        initial = {
            **category,
            "parent_id": category.get("parent_id") or "",
        }

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
    success_url = reverse_lazy("catalog:category_list")

    def get(self, request, pk):
        return render(request, self.template_name, {"category_id": pk})

    def post(self, request, pk):
        result = self.service.update_category(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "Категория деактивирована.")
            return redirect(self.success_url)
        if result.not_found:
            raise Http404("Категория не найдена")
        messages.error(request, result.form_error)
        return render(request, self.template_name, {"category_id": pk})


class CategoryTreeView(CatalogReadAccessMixin, TemplateView):
    template_name = "catalog/category_tree.html"

    def get(self, request, *args, **kwargs):
        return redirect("catalog:category_list")


class UnitListView(CatalogManageAccessMixin, TemplateView):
    template_name = "catalog/unit_list.html"

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
    success_url = reverse_lazy("catalog:unit_list")

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
    success_url = reverse_lazy("catalog:unit_list")

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
    template_name = "catalog/item_list.html"

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
    success_url = reverse_lazy("catalog:item_list")

    def _catalog_data(self):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_units()

        units = units_result.data if units_result.ok else []

        return categories, units, categories_result, units_result

    def get(self, request):
        categories, units, categories_result, units_result = self._catalog_data()

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        form = ItemForm(categories=categories, units=units)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        categories, units, _, _ = self._catalog_data()
        form = ItemForm(request.POST, categories=categories, units=units)
        if form.is_valid():
            result = self.service.create_item(form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class ItemUpdateView(CatalogManageAccessMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("catalog:item_list")

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

        form = ItemForm(initial=item, categories=categories, units=units)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        categories, categories_result = self._get_categories_flat()
        units_result = self.service.list_units()
        units = units_result.data if units_result.ok else []

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not units_result.ok:
            messages.error(request, units_result.form_error)

        form = ItemForm(request.POST, categories=categories, units=units)
        if form.is_valid():
            result = self.service.update_item(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("ТМЦ не найдена")
            form.add_error(None, result.form_error)

        return render(request, self.template_name, {"form": form, "mode": "update"})


class ItemDeactivateView(CatalogManageAccessMixin, View):
    success_url = reverse_lazy("catalog:item_list")

    def post(self, request, pk):
        result = self.service.update_item(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "ТМЦ деактивирована.")
        elif result.not_found:
            raise Http404("ТМЦ не найдена")
        else:
            messages.error(request, result.form_error)
        return redirect(self.success_url)
