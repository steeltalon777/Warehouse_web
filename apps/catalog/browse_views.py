from __future__ import annotations

from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.catalog.services import CatalogService
from apps.catalog.tree import build_category_item_tree
from apps.catalog.views import _filter_manage_categories, _normalize_categories, _normalize_items
from apps.common.permissions import can_use_client
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
    site_id = _resolve_site_id(request) or None
    client = SyncServerClient(
        user_id=request.user.id,
        site_id=site_id,
        request=request,
    )
    return CatalogService(client)


def _parse_page(raw_value, *, default: int = 1) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _build_pagination(request, payload: dict, *, page_key: str = "page") -> dict:
    page = _parse_page(payload.get("page"), default=1)
    page_size = _parse_page(payload.get("page_size"), default=20)
    total_count = int(payload.get("total_count") or 0)
    total_pages = max(1, ceil(total_count / page_size)) if page_size else 1
    page = min(page, total_pages)

    def build_url(page_number: int) -> str:
        query = request.GET.copy()
        query[page_key] = str(page_number)
        return f"?{query.urlencode()}"

    pages = [
        {
            "number": page_number,
            "url": build_url(page_number),
            "current": page_number == page,
        }
        for page_number in range(1, total_pages + 1)
    ]

    return {
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_url": build_url(page - 1) if page > 1 else "",
        "next_url": build_url(page + 1) if page < total_pages else "",
        "pages": pages,
    }


def _build_catalog_home_url(request, **overrides) -> str:
    query = request.GET.copy()
    query["page"] = "1"
    for key, value in overrides.items():
        if value in (None, "", False):
            query.pop(key, None)
        else:
            query[key] = str(value)
    encoded = query.urlencode()
    base_url = reverse("catalog:home")
    return f"{base_url}?{encoded}" if encoded else base_url


class CatalogAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")

        self.service = _build_catalog_service(request)
        return super().dispatch(request, *args, **kwargs)


class CatalogHomeView(CatalogAccessMixin, View):
    template_name = "catalog/browse_home.html"

    def get(self, request, *args, **kwargs):
        search = (request.GET.get("search") or "").strip() or None
        selected_category_id = (request.GET.get("category_id") or "").strip() or None
        selected_item_id = (request.GET.get("item_id") or "").strip() or None
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = 20

        categories_result = self.service.list_categories(limit=1000)
        tree_items_result = self.service.browse_all_items()

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not tree_items_result.ok:
            messages.error(request, tree_items_result.form_error)

        categories = (
            _filter_manage_categories(_normalize_categories(categories_result.data or []))
            if categories_result.ok
            else []
        )
        tree_items = _normalize_items(tree_items_result.data or []) if tree_items_result.ok else []

        selected_item = None
        if selected_item_id:
            selected_item = next((item for item in tree_items if str(item.get("id")) == str(selected_item_id)), None)
            if selected_item and not selected_category_id:
                selected_category_id = str(selected_item.get("category_id") or "")

        selected_category = None
        if selected_category_id:
            selected_category = next(
                (category for category in categories if str(category.get("id")) == str(selected_category_id)),
                None,
            )

        tree_nodes = build_category_item_tree(
            categories=categories,
            items=tree_items,
            category_url_builder=lambda category: _build_catalog_home_url(
                request,
                category_id=category["id"],
                item_id=None,
            ),
            item_url_builder=lambda item: _build_catalog_home_url(
                request,
                category_id=item.get("category_id"),
                item_id=item["id"],
            ),
            selected_kind="item" if selected_item else ("category" if selected_category_id else None),
            selected_id=(selected_item_id if selected_item else selected_category_id),
        )

        items_payload: dict = {"items": [], "page": page, "page_size": page_size, "total_count": 0}
        if not selected_item:
            items_result = self.service.browse_items(
                search=search,
                category_id=selected_category_id,
                page=page,
                page_size=page_size,
            )
            if not items_result.ok:
                messages.error(request, items_result.form_error)
            elif isinstance(items_result.data, dict):
                items_payload = items_result.data

        return render(
            request,
            self.template_name,
            {
                "search": search or "",
                "selected_category_id": selected_category_id or "",
                "selected_item_id": selected_item_id or "",
                "selected_category": selected_category,
                "selected_item": selected_item,
                "tree_nodes": tree_nodes,
                "items": _normalize_items(items_payload.get("items", [])),
                "pagination": _build_pagination(request, items_payload),
                "catalog_reset_url": reverse("catalog:home"),
            },
        )


class BrowseItemListView(CatalogAccessMixin, View):
    def get(self, request, *args, **kwargs):
        next_url = _build_catalog_home_url(
            request,
            category_id=(request.GET.get("category_id") or "").strip() or None,
            item_id=(request.GET.get("item_id") or "").strip() or None,
        )
        return redirect(next_url)


class BrowseCategoryListView(CatalogAccessMixin, View):
    def get(self, request, *args, **kwargs):
        next_url = _build_catalog_home_url(
            request,
            category_id=(request.GET.get("category_id") or request.GET.get("parent_id") or "").strip() or None,
            item_id=None,
            parent_id=None,
        )
        return redirect(next_url)
