"""
BFF views for review-required catalog items.

Uses the new SyncServer /api/v1/review-items endpoints.
"""

from __future__ import annotations

import structlog

from apps.sync_client.review_items_api import ReviewItemsAPI
from apps.sync_client.client import SyncServerClient
from braces.views import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.views import View

from .helpers import _build_client, _ok, _handle_sync_error, sync_api_error, json_error
from apps.sync_client.exceptions import SyncServerAPIError

logger = structlog.get_logger()


class ReviewItemsListView(LoginRequiredMixin, View):
    """GET /bff/review-items — list review-required items."""

    def get(self, request: HttpRequest) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            page = int(request.GET.get("page", 1))
            page_size = int(request.GET.get("page_size", 50))
            filters = {
                "search": request.GET.get("search"),
                "review_status": request.GET.get("review_status"),
                "created_by_user_id": request.GET.get("created_by_user_id"),
                "page": page,
                "page_size": page_size,
            }
            filters = {k: v for k, v in filters.items() if v is not None}
            data = api.list_review_items_page(filters)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ReviewItemDetailView(LoginRequiredMixin, View):
    """GET /bff/review-items/<id> — get review item detail.
    DELETE /bff/review-items/<id> — delete unused review item.
    """

    def get(self, request: HttpRequest, item_id: int) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            data = api.get_review_item(item_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def delete(self, request: HttpRequest, item_id: int) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            data = api.delete_review_item(item_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ReviewItemOperationsView(LoginRequiredMixin, View):
    """GET /bff/review-items/<id>/operations — list operations for review item."""

    def get(self, request: HttpRequest, item_id: int) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            page = int(request.GET.get("page", 1))
            page_size = int(request.GET.get("page_size", 50))
            data = api.list_review_item_operations(
                item_id,
                filters={"page": page, "page_size": page_size},
            )
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ReviewItemConfirmView(LoginRequiredMixin, View):
    """POST /bff/review-items/<id>/confirm — confirm review item."""

    def post(self, request: HttpRequest, item_id: int) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            from json import loads

            payload = loads(request.body)
            data = api.confirm_review_item(item_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ReviewItemMergeView(LoginRequiredMixin, View):
    """POST /bff/review-items/<id>/merge — merge review item into catalog item."""

    def post(self, request: HttpRequest, item_id: int) -> JsonResponse:
        api = ReviewItemsAPI(_build_client(request))
        try:
            from json import loads

            payload = loads(request.body)
            data = api.merge_review_item(item_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
