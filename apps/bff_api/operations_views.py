import json
import re
import uuid

import structlog

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.bff_api.helpers import (
    _build_client,
    _handle_sync_error,
    _ok,
    _error,
    _require_storekeeper,
)
from apps.bff_api.operations_enricher import (
    _get_sites_index,
    _get_user_labels,
    enrich_operation,
)
from apps.sync_client.api_error_response import api_error_response
from apps.sync_client.exceptions import (
    SyncBackendUnavailable,
    SyncServerAPIError,
)
from apps.sync_client.operations_api import OperationsAPI

logger = structlog.get_logger()

# Warehouse 3.2 client signals we require ``expected_version`` / ``client_request_id``.
# Legacy prefixes (e.g. ``legacy-``, ``dev-``) are still acceptable for rollout
# compatibility but UUIDs are the preferred shape.
CLIENT_VERSION_HEADER = "X-Warehouse-Client"
NEW_CLIENT_VERSION = "3.2"
CLIENT_REQUEST_ID_MAX_LENGTH = 100
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _ops(request):
    return OperationsAPI(_build_client(request))


def _is_new_client(request) -> bool:
    """True when the caller is the Warehouse 3.2 web client (or Angular SPA).

    The header is set by the Angular shell. Legacy callers without the header
    keep the permissive behaviour for the duration of the rollout.
    """
    version = (request.META.get("HTTP_X_WAREHOUSE_CLIENT") or "").strip()
    return version.startswith(NEW_CLIENT_VERSION)


def _enrich_list(request, data):
    items = data.get("items", [])
    if not items:
        return data
    sites_index = _get_sites_index(request)
    user_ids = {op.get("created_by_user_id") for op in items}
    user_labels = _get_user_labels(request, user_ids)
    data["items"] = [enrich_operation(op, sites_index, user_labels) for op in items]
    return data


def _enrich_detail(request, operation):
    if not operation:
        return operation
    sites_index = _get_sites_index(request)
    user_labels = _get_user_labels(request, {operation.get("created_by_user_id")})
    return enrich_operation(operation, sites_index, user_labels)


def _current_request_id(request) -> str:
    """Best-effort X-Request-Id retrieval — used when mapping write timeouts."""
    return (request.META.get("HTTP_X_REQUEST_ID") or "").strip()


# Headers that the SPA / Angular shell sends per
# `docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md` §3.2 and that the BFF
# must forward to SyncServer for log correlation. Token headers are explicitly
# NOT in this list — Django resolution happens in ``SyncServerClient``.
CLIENT_CORRELATION_HEADERS = (
    "X-Client-Session-Id",
    "X-Client-Tab-Id",
    "X-Client-Request-Id",
    "X-Client-Draft-Id",
    "X-Frontend-Version",
)


def _collect_correlation_headers(request) -> dict[str, str]:
    """Read browser-supplied correlation headers from ``request.headers`` and
    return only the non-empty ones, so the BFF can forward them downstream.
    """
    collected: dict[str, str] = {}
    for header in CLIENT_CORRELATION_HEADERS:
        value = request.headers.get(header)
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if text:
            collected[header] = text
    return collected


def _apply_sync_request_id(response: JsonResponse, sync_headers: dict[str, str], request) -> JsonResponse:
    """Prefer ``X-Request-Id`` from SyncServer's response headers (it carries
    the SyncServer's server-side correlation id); fall back to the per-request
    id from ``RequestTracingMiddleware`` that already lives in
    ``request.META['X_REQUEST_ID']``. ``RequestTracingMiddleware`` already sets
    this header on every response, so this is best-effort: when SyncServer
    returned one, we surface it; otherwise the middleware default survives.
    """
    sync_request_id = sync_headers.get("X-Request-Id") or sync_headers.get("x-request-id")
    if sync_request_id:
        response["X-Request-Id"] = sync_request_id
    return response


def _operation_outcome_unknown(exc: SyncBackendUnavailable, request) -> JsonResponse:
    """Translate write-timeout / connection failures into the distinct
    ``operation_outcome_unknown`` envelope so Angular can show retry-safe UI
    without pretending the operation succeeded.
    """
    payload = exc.payload if isinstance(exc.payload, dict) else {}
    body: dict = {
        "code": "operation_outcome_unknown",
        "message": str(exc) or "Operation outcome is unknown after a write timeout.",
        "retry_safe": True,
    }
    request_id = _current_request_id(request)
    if request_id:
        body["request_id"] = request_id
    elif payload.get("request_id"):
        body["request_id"] = payload["request_id"]
    return JsonResponse({"ok": False, "error": body}, status=504)


def _validate_client_request_id(payload: dict, *, request) -> JsonResponse | None:
    """Enforce TZ C5 contract: create operations MUST carry a non-empty
    client_request_id (≤ 100 chars). UUIDs and prefixed legacy keys are
    accepted.
    """
    raw = payload.get("client_request_id") if isinstance(payload, dict) else None
    if not raw or not isinstance(raw, str):
        return _error(
            "client_request_id is required and must be a non-empty string.",
            "validation_error",
            400,
        )
    value = raw.strip()
    if not value:
        return _error(
            "client_request_id is required and must be a non-empty string.",
            "validation_error",
            400,
        )
    if len(value) > CLIENT_REQUEST_ID_MAX_LENGTH:
        return _error(
            f"client_request_id must be <= {CLIENT_REQUEST_ID_MAX_LENGTH} chars.",
            "validation_error",
            400,
        )
    # BFF only enforces non-empty + length. Stricter format constraints
    # (UUID preferred for Angular 3.2, legacy- / dev- prefixes accepted for
    # rollout compatibility) are the client's responsibility and validated
    # server-side by SyncServer.
    return None


def _validate_expected_version(payload: dict, *, request) -> JsonResponse | None:
    """Enforce TZ C5 contract: Warehouse 3.2 PATCH / submit must include
    ``expected_version``. Legacy callers without the X-Warehouse-Client header
    are permitted to omit it for backward compatibility during rollout.
    """
    if not _is_new_client(request):
        return None
    raw = payload.get("expected_version") if isinstance(payload, dict) else None
    if raw is None:
        return _error(
            "expected_version is required for Warehouse 3.2 clients.",
            "validation_error",
            400,
        )
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return _error(
            "expected_version must be an integer.",
            "validation_error",
            400,
        )
    if version < 1:
        return _error(
            "expected_version must be a positive integer.",
            "validation_error",
            400,
        )
    return None


class OperationsListView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            api = _ops(request)
            params: dict[str, str] = {}
            for key in (
                "site_id", "type", "status", "created_by_user_id",
                "acceptance_state",
                "effective_after", "effective_before",
                "created_after", "created_before",
                "updated_after", "updated_before",
                "search", "item_ids", "page", "page_size",
                "exclude_adjustments", "client_request_id",
            ):
                val = request.GET.get(key)
                if val is not None:
                    params[key] = val
            # Resolve "me" to current user's SyncServer UUID
            if params.get("created_by_user_id") == "me":
                user = request.user
                sync_id = getattr(getattr(user, "sync_binding", None), "syncserver_user_id", None)
                if sync_id:
                    params["created_by_user_id"] = str(sync_id)
                else:
                    del params["created_by_user_id"]
            extra_headers = _collect_correlation_headers(request)
            data, sync_headers = api.list_operations_page(
                filters=params,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(_enrich_list(request, data))
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

        if not isinstance(payload, dict):
            return _error("JSON object body required", "validation_error", 400)

        id_error = _validate_client_request_id(payload, request=request)
        if id_error is not None:
            return id_error

        extra_headers = _collect_correlation_headers(request)

        try:
            api = _ops(request)
            data, sync_headers = api.create_operation(
                payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class OperationDetailView(LoginRequiredMixin, View):
    def delete(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            _, sync_headers = api.delete_operation(
                operation_id,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok({"deleted": True})
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def get(self, request, operation_id):
        try:
            api = _ops(request)
            extra_headers = _collect_correlation_headers(request)
            data, sync_headers = api.get_operation(
                operation_id,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(_enrich_detail(request, data))
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

    def patch(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

        if not isinstance(payload, dict):
            return _error("JSON object body required", "validation_error", 400)

        version_error = _validate_expected_version(payload, request=request)
        if version_error is not None:
            return version_error

        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data, sync_headers = api.update_operation(
                operation_id,
                payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class OperationEffectiveAtView(LoginRequiredMixin, View):
    def patch(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)
        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data = api.client.patch(
                f"/operations/{operation_id}/effective-at",
                json=payload,
                extra_headers=extra_headers,
            )
            return _ok(data)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class OperationSubmitView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {"submit": True}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

        if not isinstance(payload, dict):
            payload = {"submit": True}

        if _is_new_client(request) and "expected_version" not in payload:
            payload = {**payload, "expected_version": payload.get("expected_version")}

        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data, sync_headers = api.submit_operation(
                operation_id,
                payload=payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return api_error_response(exc)


class OperationCancelView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {"cancel": True}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)
        if not isinstance(payload, dict):
            payload = {"cancel": True}
        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data, sync_headers = api.cancel_operation(
                operation_id,
                payload=payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return api_error_response(exc)


class OperationRestoreView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data, sync_headers = api.restore_operation(
                operation_id,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class OperationFromSourceDocumentView(LoginRequiredMixin, View):
    """BFF proxy for POST /api/v1/operations/from-source-document.

    Создаёт операцию из внешнего документа (накладная, OCR, импорт).
    Schema физически не допускает temporary_item.
    """

    def post(self, request):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)

        if not isinstance(payload, dict):
            return _error("JSON object body required", "validation_error", 400)

        if not payload.get("source_ref"):
            return _error("source_ref is required", "validation_error", 400)

        extra_headers = _collect_correlation_headers(request)

        try:
            api = _ops(request)
            data, sync_headers = api.create_operation_from_source_document(
                payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)


class OperationAcceptLinesView(LoginRequiredMixin, View):
    def post(self, request, operation_id):
        if not _require_storekeeper(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return _error("Invalid JSON body", "validation_error", 400)
        if not isinstance(payload, dict):
            payload = {}
        extra_headers = _collect_correlation_headers(request)
        try:
            api = _ops(request)
            data, sync_headers = api.accept_operation_lines(
                operation_id,
                payload,
                extra_headers=extra_headers,
                return_response=True,
            )
            response = _ok(data)
            return _apply_sync_request_id(response, sync_headers, request)
        except SyncBackendUnavailable as exc:
            return _operation_outcome_unknown(exc, request)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
