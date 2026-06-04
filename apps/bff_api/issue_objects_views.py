import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_storekeeper,
    _require_chief_or_root,
)
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.issue_objects_api import IssueObjectsAPI
from apps.sync_client.issue_object_categories_api import IssueObjectCategoriesAPI


def _io(request):
    return IssueObjectsAPI(_build_client(request))


def _ioc(request):
    return IssueObjectCategoriesAPI(_build_client(request))


class IssueObjectsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _io(request)
            params: dict[str, str] = {}
            for key in ("search", "category_id", "is_active", "include_inactive", "include_deleted", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_issue_objects(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _io(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_issue_object(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class IssueObjectsMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_chief_or_root(request.user):
            return _error("Only chief_storekeeper or root can merge issue objects", "forbidden", 403)
        try:
            api = _io(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.merge_issue_objects(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class IssueObjectDetailView(LoginRequiredMixin, View):
    def get(self, request, issue_object_id):
        try:
            api = _io(request)
            data = api.get_issue_object(issue_object_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, issue_object_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _io(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_issue_object(issue_object_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, issue_object_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _io(request)
            api.delete_issue_object(issue_object_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class ObjectAssetsListView(LoginRequiredMixin, View):
    def get(self, request, issue_object_id):
        try:
            api = _io(request)
            params: dict[str, str] = {}
            for key in ("search", "item_id", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_object_assets(issue_object_id, filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class IssueObjectCategoriesListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _ioc(request)
            params: dict[str, str] = {}
            for key in ("search", "parent_id", "is_active", "include_deleted", "page", "page_size"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.list_categories(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ioc(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.create_category(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)


class IssueObjectCategoryDetailView(LoginRequiredMixin, View):
    def get(self, request, category_id):
        try:
            api = _ioc(request)
            data = api.get_category(category_id)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, category_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ioc(request)
            payload = json.loads(request.body) if request.body else {}
            data = api.update_category(category_id, payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

    def delete(self, request, category_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            api = _ioc(request)
            api.delete_category(category_id)
            return _ok({"deleted": True})
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class IssueObjectsTreeView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _io(request)
            params: dict[str, str] = {}
            for key in ("search", "include_inactive", "include_deleted"):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            data = api.get_tree(filters=params)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
