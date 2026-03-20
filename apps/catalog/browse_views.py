from __future__ import annotations

from math import ceil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.catalog.constants import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from apps.catalog.services import CatalogService
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


def _active_categories(categories: list[dict]) -> list[dict]:
    return [
        category
        for category in categories
        if isinstance(category, dict) and category.get("is_active", True)
    ]


def _is_uncategorized_category(category: dict) -> bool:
    code = str(category.get("code") or "").strip()
    name = str(category.get("name") or "").strip()
    return code == UNCATEGORIZED_CATEGORY_CODE or name == UNCATEGORIZED_CATEGORY_NAME


def _filter_visible_categories(categories: list[dict]) -> list[dict]:
    return [category for category in categories if not _is_uncategorized_category(category)]


class CatalogAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_use_client(request.user):
            return HttpResponseForbidden("Нет доступа")

        self.service = _build_catalog_service(request)
        return super().dispatch(request, *args, **kwargs)


class CatalogHomeView(CatalogAccessMixin, TemplateView):
    template_name = "catalog/browse_home.html"


class BrowseItemListView(CatalogAccessMixin, View):
    template_name = "catalog/browse_item_list.html"

    def get(self, request, *args, **kwargs):
        search = (request.GET.get("search") or "").strip() or None
        category_id = (request.GET.get("category_id") or "").strip() or None
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = 20

        items_result = self.service.browse_items(
            search=search,
            category_id=category_id,
            page=page,
            page_size=page_size,
        )
        categories_result = self.service.list_categories()

        if not items_result.ok:
            messages.error(request, items_result.form_error)
        if not categories_result.ok:
            messages.error(request, categories_result.form_error)

        items_payload = items_result.data if items_result.ok and isinstance(items_result.data, dict) else {}
        categories = _active_categories(categories_result.data or []) if categories_result.ok else []

        return render(
            request,
            self.template_name,
            {
                "items": items_payload.get("items", []),
                "categories": categories,
                "selected_category_id": category_id or "",
                "search": search or "",
                "pagination": _build_pagination(request, items_payload or {"page": page, "page_size": page_size}),
            },
        )


class BrowseCategoryListView(CatalogAccessMixin, View):
    template_name = "catalog/browse_category_list.html"

    def get(self, request, *args, **kwargs):
        search = (request.GET.get("search") or "").strip() or None
        parent_id = (request.GET.get("parent_id") or "").strip() or None
        page = _parse_page(request.GET.get("page"), default=1)
        page_size = 20

        categories_result = self.service.browse_categories(
            search=search,
            parent_id=parent_id,
            page=page,
            page_size=page_size,
            include="parent,parent_chain_summary,items_preview",
            items_preview_limit=5,
        )
        parent_options_result = self.service.list_categories()

        if not categories_result.ok:
            messages.error(request, categories_result.form_error)
        if not parent_options_result.ok:
            messages.error(request, parent_options_result.form_error)

        categories_payload = (
            categories_result.data if categories_result.ok and isinstance(categories_result.data, dict) else {}
        )
        parent_options = _active_categories(parent_options_result.data or []) if parent_options_result.ok else []

        return render(
            request,
            self.template_name,
            {
                "categories": _filter_visible_categories(categories_payload.get("categories", [])),
                "parent_options": _filter_visible_categories(parent_options),
                "selected_parent_id": parent_id or "",
                "search": search or "",
                "pagination": _build_pagination(request, categories_payload or {"page": page, "page_size": page_size}),
            },
        )
