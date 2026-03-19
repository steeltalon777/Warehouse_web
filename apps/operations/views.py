from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.common.mixins import SyncContextMixin
from apps.operations.forms import OperationCreateForm
from apps.sync_client.exceptions import SyncServerAPIError
from apps.sync_client.operations_api import OperationsAPI

from apps.common.api_error_handler import (
    APIErrorHandler,
    handle_api_errors,
    safe_api_call,
    log_api_call,
)


class OperationsListView(SyncContextMixin, TemplateView):
    template_name = "operations/list.html"

    @handle_api_errors(operation="Получение списка операций")
    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        status = request.GET.get("status") or None
        operation_type = request.GET.get("type") or None

        api = OperationsAPI(self.client)
        operations = []

        try:
            # Build filters
            filters = {}
            if search:
                filters["search"] = search
            if status:
                filters["status"] = status
            if operation_type:
                filters["type"] = operation_type

            # Log API call
            log_api_call(
                method="GET",
                path="/operations",
                context={"filters": filters, "limit": limit, "offset": offset},
            )

            operations = api.list_operations(filters=filters)

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении списка операций"
            )

        context = {
            "operations": operations,
            "search": search or "",
            "status": status or "",
            "type": operation_type or "",
            "limit": limit,
            "offset": offset,
            "prev_offset": max(offset - limit, 0),
            "next_offset": offset + limit,
        }
        return render(request, self.template_name, context)


class OperationDetailView(SyncContextMixin, TemplateView):
    template_name = "operations/detail.html"

    @handle_api_errors(operation="Получение деталей операции")
    def get(self, request, operation_id):
        operation = None

        try:
            # Log API call
            log_api_call(
                method="GET",
                path=f"/operations/{operation_id}",
                context={"operation_id": operation_id},
            )

            operation = OperationsAPI(self.client).get_operation(operation_id)

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "получении деталей операции"
            )

        return render(request, self.template_name, {"operation": operation})


class OperationCreateView(SyncContextMixin, View):
    template_name = "operations/form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": OperationCreateForm()})

    @handle_api_errors(operation="Создание операции")
    def post(self, request):
        form = OperationCreateForm(request.POST)
        if form.is_valid():
            try:
                # Log API call
                log_api_call(
                    method="POST",
                    path="/operations",
                    context={"form_data_keys": list(form.cleaned_data.keys())},
                )

                created = OperationsAPI(self.client).create_operation(form.cleaned_data)
                messages.success(request, "Операция создана.")

                # Log successful creation
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Операция создана: {created.get('id')}",
                    extra={
                        "operation_id": created.get("id"),
                        "type": created.get("type"),
                    },
                )

                return redirect("operations:detail", operation_id=created.get("id"))

            except SyncServerAPIError as exc:
                # Add error to form for display
                form.add_error(None, str(exc))
                # Re-raise for decorator to handle
                raise
            except Exception as exc:
                # Handle generic errors
                APIErrorHandler.handle_generic_error(request, exc, "создании операции")
                form.add_error(None, "Произошла непредвиденная ошибка")

        return render(request, self.template_name, {"form": form})


class SubmitOperationView(SyncContextMixin, View):
    """Представление для отправки операции на обработку"""

    @handle_api_errors(
        operation="Отправка операции на обработку", retry_transient=True, max_retries=2
    )
    def post(self, request, operation_id):
        try:
            api = OperationsAPI(self.client)

            # Log API call
            log_api_call(
                method="POST",
                path=f"/operations/{operation_id}/submit",
                context={"operation_id": operation_id},
            )

            operation = api.submit_operation(operation_id)
            messages.success(
                request, f"Операция {operation_id} отправлена на обработку."
            )

            # Log successful submission
            logger = logging.getLogger(__name__)
            logger.info(
                f"Операция отправлена: {operation_id}",
                extra={
                    "operation_id": operation_id,
                    "new_status": operation.get("status"),
                },
            )

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(
                request, exc, "отправке операции на обработку"
            )

        return redirect("operations:detail", operation_id=operation_id)


class CancelOperationView(SyncContextMixin, View):
    """Представление для отмены операции"""

    @handle_api_errors(operation="Отмена операции", retry_transient=True, max_retries=2)
    def post(self, request, operation_id):
        try:
            api = OperationsAPI(self.client)

            # Log API call
            log_api_call(
                method="POST",
                path=f"/operations/{operation_id}/cancel",
                context={"operation_id": operation_id},
            )

            operation = api.cancel_operation(operation_id)
            messages.success(request, f"Операция {operation_id} отменена.")

            # Log successful cancellation
            logger = logging.getLogger(__name__)
            logger.info(
                f"Операция отменена: {operation_id}",
                extra={
                    "operation_id": operation_id,
                    "new_status": operation.get("status"),
                },
            )

        except SyncServerAPIError as exc:
            # Error will be handled by decorator
            raise
        except Exception as exc:
            # Handle generic errors
            APIErrorHandler.handle_generic_error(request, exc, "отмене операции")

        return redirect("operations:detail", operation_id=operation_id)


# Alternative implementation using safe_api_call for simpler views
class SimpleOperationsListView(SyncContextMixin, TemplateView):
    """
    Alternative implementation using safe_api_call helper.
    Shows different approach to error handling.
    """

    template_name = "operations/list.html"

    def get(self, request, *args, **kwargs):
        limit = int(request.GET.get("limit", 20))
        offset = int(request.GET.get("offset", 0))
        search = request.GET.get("search") or None
        status = request.GET.get("status") or None
        operation_type = request.GET.get("type") or None

        api = OperationsAPI(self.client)

        # Build filters
        filters = {}
        if search:
            filters["search"] = search
        if status:
            filters["status"] = status
        if operation_type:
            filters["type"] = operation_type

        # Use safe_api_call for error handling
        operations = (
            safe_api_call(
                api.list_operations,
                request,
                operation="Получение списка операций",
                filters=filters,
            )
            or []
        )

        context = {
            "operations": operations,
            "search": search or "",
            "status": status or "",
            "type": operation_type or "",
            "limit": limit,
            "offset": offset,
            "prev_offset": max(offset - limit, 0),
            "next_offset": offset + limit,
        }
        return render(request, self.template_name, context)
