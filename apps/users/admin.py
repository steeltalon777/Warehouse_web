from __future__ import annotations

import copy
from uuid import uuid4

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpRequest, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from datetime import timedelta

from django.utils import timezone
from django.utils.html import format_html

from apps.sync_client.exceptions import SyncServerAPIError
from apps.users.admin_forms import (
    SuperuserLocalAdminForm,
    SyncManagedDeviceAdminForm,
    SyncManagedDeviceCreationForm,
    SyncManagedSiteAdminForm,
    SyncManagedUserAdminForm,
    SyncManagedUserCreationForm,
)
from apps.users.models import LoginAttempt, Site, SyncDeviceBinding, SyncStatus, SyncUserBinding
from apps.users.services import DeviceSyncService, SiteSyncService, UserSyncService

User = get_user_model()


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    form = SyncManagedSiteAdminForm
    list_display = ("name", "code", "syncserver_site_id", "is_active", "updated_at")
    search_fields = ("name", "code", "syncserver_site_id")
    readonly_fields = ("syncserver_site_id", "created_at", "updated_at")
    fields = ("code", "name", "description", "is_active", "syncserver_site_id", "created_at", "updated_at")
    actions = ["refresh_sites_from_syncserver"]

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request)

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_view_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_change_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_delete_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return False

    @admin.action(description="Обновить склады из SyncServer")
    def refresh_sites_from_syncserver(self, request: HttpRequest, queryset):
        try:
            count = SiteSyncService().refresh_local_cache()
            self.message_user(
                request,
                f"Склады обновлены: {count} записей.",
                level="success",
            )
        except Exception as exc:
            self.message_user(
                request,
                f"Не удалось обновить склады: {exc}",
                level="error",
            )

    def save_model(self, request: HttpRequest, obj: Site, form, change: bool) -> None:
        payload = {
            "code": form.cleaned_data["code"],
            "name": form.cleaned_data["name"],
            "description": form.cleaned_data.get("description") or "",
            "is_active": form.cleaned_data.get("is_active", True),
        }
        service = SiteSyncService()

        if change:
            if not obj.syncserver_site_id:
                raise RuntimeError("Local site mirror has no syncserver_site_id.")
            mirror = service.update_site(obj.syncserver_site_id, payload)
        else:
            mirror = service.create_site(payload)

        obj.pk = mirror.pk
        obj.syncserver_site_id = mirror.syncserver_site_id
        obj.code = mirror.code
        obj.name = mirror.name
        obj.description = mirror.description
        obj.is_active = mirror.is_active
        obj.created_at = mirror.created_at
        obj.updated_at = mirror.updated_at


@admin.register(SyncUserBinding)
class SyncUserBindingAdmin(admin.ModelAdmin):
    actions = None
    list_display = (
        "user",
        "sync_role",
        "default_site_id",
        "sync_status",
        "last_sync_at",
        "masked_user_token",
    )
    search_fields = ("user__username", "user__email", "syncserver_user_id")
    readonly_fields = (
        "user",
        "syncserver_user_id",
        "sync_role",
        "site_ids",
        "sync_user_token",
        "sync_status",
        "last_sync_at",
        "last_sync_error",
        "last_sync_payload_pretty",
        "token_rotated_at",
        "manual_token_updated_at",
        "manual_token_updated_by",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "syncserver_user_id",
                    "sync_role",
                    "site_ids",
                    "sync_status",
                    "last_sync_error",
                    "last_sync_at",
                    "token_rotated_at",
                    "manual_token_updated_at",
                    "manual_token_updated_by",
                )
            },
        ),
    )

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_view_permission(self, request: HttpRequest, obj: SyncUserBinding | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: SyncUserBinding | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_delete_permission(self, request: HttpRequest, obj: SyncUserBinding | None = None) -> bool:
        return False

    @admin.display(description="User token")
    def masked_user_token(self, obj: SyncUserBinding) -> str:
        token = obj.sync_user_token or ""
        if len(token) <= 8:
            return token
        return f"{token[:4]}...{token[-4:]}"

    @admin.display(description="Last sync payload")
    def last_sync_payload_pretty(self, obj: SyncUserBinding) -> str:
        return format_html("<pre style='white-space:pre-wrap;max-width:960px;'>{}</pre>", obj.last_sync_payload or {})

    def save_model(self, request: HttpRequest, obj: SyncUserBinding, form, change: bool) -> None:
        if change and "sync_user_token" in form.changed_data:
            obj.sync_status = SyncStatus.MANUAL_OVERRIDE
            obj.manual_token_updated_at = timezone.now()
            obj.manual_token_updated_by = request.user
            obj.last_sync_error = ""
        super().save_model(request, obj, form, change)


@admin.register(SyncDeviceBinding)
class SyncDeviceBindingAdmin(admin.ModelAdmin):
    form = SyncManagedDeviceAdminForm
    add_form = SyncManagedDeviceCreationForm
    change_form_template = "admin/users/syncdevicebinding/change_form.html"
    actions = ("repair_selected_bindings", "mark_selected_for_repair", "refresh_device_status_action")
    list_display = (
        "device_code",
        "device_name",
        "is_active",
        "sync_status",
        "last_sync_at",
        "online_status",
        "health_status",
        "masked_device_token",
        "sync_state_behind_by",
    )
    list_display_links = ("device_code",)
    list_filter = ("is_active", "sync_status", "device_code")
    search_fields = ("device_code", "device_name", "syncserver_device_id")
    readonly_fields = (
        "syncserver_device_id",
        "sync_device_token",
        "sync_status",
        "last_sync_at",
        "last_seen_at",
        "sync_state_status",
        "sync_state_last_seq",
        "sync_state_behind_by",
        "health_status",
        "last_sync_error",
        "last_sync_payload_pretty",
        "token_rotated_at",
        "manual_token_updated_at",
        "manual_token_updated_by",
        "created_at",
        "updated_at",
    )
    fields = (
        "device_code",
        "device_name",
        "syncserver_device_id",
        "sync_device_token",
        "is_active",
        "sync_status",
        "sync_state_status",
        "sync_state_last_seq",
        "sync_state_behind_by",
        "health_status",
        "last_sync_error",
        "last_sync_payload_pretty",
        "last_sync_at",
        "last_seen_at",
        "token_rotated_at",
        "manual_token_updated_at",
        "manual_token_updated_by",
        "created_at",
        "updated_at",
    )

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_view_permission(self, request: HttpRequest, obj: SyncDeviceBinding | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_change_permission(self, request: HttpRequest, obj: SyncDeviceBinding | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_delete_permission(self, request: HttpRequest, obj: SyncDeviceBinding | None = None) -> bool:
        return False

    @admin.display(description="Device token")
    def masked_device_token(self, obj: SyncDeviceBinding) -> str:
        token = obj.sync_device_token or ""
        if len(token) <= 8:
            return token
        return f"{token[:4]}...{token[-4:]}"

    @admin.display(description="Last sync payload")
    def last_sync_payload_pretty(self, obj: SyncDeviceBinding) -> str:
        return format_html("<pre style='white-space:pre-wrap;max-width:960px;'>{}</pre>", obj.last_sync_payload or {})

    @admin.display(description="Статус", ordering="sync_state_status")
    def online_status(self, obj):
        """Colour-coded badge based on cached ``sync_state_status`` field.

        Per TZ Task 2.3 this reads the cached field (populated by the
        admin action ``refresh_device_status_action``) and MUST NOT call
        the SyncServer API.

        When ``sync_state_status`` is not set (null/empty), falls back to
        computing online/offline from ``last_seen_at`` for backward
        compatibility with devices that have not been refreshed yet.
        """
        if obj.sync_state_status:
            status_colors = {
                "online": ("green", "Online"),
                "offline": ("red", "Offline"),
                "error": ("red", "Error"),
                "unknown": ("gray", "Неизвестно"),
            }
            color, label = status_colors.get(obj.sync_state_status, ("gray", "—"))
            return format_html('<span style="color:{};">\u25cf {}</span>', color, label)

        # Fallback: compute from last_seen_at (backward compat)
        if not obj.last_seen_at:
            return format_html('<span style="color:gray;">—</span>')
        delta = timezone.now() - obj.last_seen_at
        if delta < timedelta(minutes=5):
            return format_html('<span style="color:green;">\U0001f7e2 Online</span>')
        elif delta < timedelta(hours=1):
            return format_html('<span style="color:orange;">\U0001f7e1 Away</span>')
        return format_html('<span style="color:red;">\U0001f534 Offline</span>')

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change and "sync_device_token" in form.changed_data:
                obj.sync_status = SyncStatus.MANUAL_OVERRIDE
                obj.manual_token_updated_at = timezone.now()
                obj.manual_token_updated_by = request.user
                obj.last_sync_error = ""
            else:
                obj.sync_status = SyncStatus.PENDING
                obj.last_sync_error = ""
            super().save_model(request, obj, form, change)
            binding_pk = obj.pk

            transaction.on_commit(
                lambda: self._run_device_sync(
                    request=request,
                    binding_pk=binding_pk,
                    change=change,
                )
            )

    def _run_device_sync(self, request, binding_pk, change):
        """Remote device sync after local commit. Runs outside atomic."""
        from apps.users.models import SyncDeviceBinding
        from apps.users.services import DeviceSyncService

        service = DeviceSyncService()
        try:
            binding = SyncDeviceBinding.objects.get(pk=binding_pk)
            if change:
                if binding.syncserver_device_id:
                    service.sync_existing_binding(binding=binding)
                else:
                    service.ensure_device_remote(binding=binding)
            else:
                service.create_binding(binding=binding)
            self.message_user(
                request,
                "Устройство синхронизировано с SyncServer.",
                level="success",
            )
        except SyncServerAPIError as exc:
            try:
                binding = SyncDeviceBinding.objects.get(pk=binding_pk)
                service.mark_failure(binding=binding, error=exc)
            except SyncDeviceBinding.DoesNotExist:
                pass
            self.message_user(
                request,
                f"Локальные данные сохранены. Ошибка синхронизации: {exc}.",
                level="warning",
            )
        except Exception as exc:
            try:
                binding = SyncDeviceBinding.objects.get(pk=binding_pk)
                service.mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            except SyncDeviceBinding.DoesNotExist:
                pass
            self.message_user(
                request,
                f"Локальные данные сохранены. Не удалось синхронизировать устройство: {exc}",
                level="error",
            )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/sync/",
                self.admin_site.admin_view(self.sync_with_syncserver_view),
                name="users_syncdevicebinding_sync",
            ),
            path(
                "<path:object_id>/rotate-token/",
                self.admin_site.admin_view(self.rotate_token_view),
                name="users_syncdevicebinding_rotate_token",
            ),
            path(
                "<path:object_id>/repair/",
                self.admin_site.admin_view(self.repair_from_syncserver_view),
                name="users_syncdevicebinding_repair",
            ),
        ]
        return custom_urls + urls

    def sync_with_syncserver_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        try:
            DeviceSyncService().sync_existing_binding(binding=binding)
            self.message_user(request, "Устройство успешно синхронизировано с SyncServer.", level="success")
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"SyncServer вернул ошибку: {exc}", level="error")
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось синхронизировать устройство: {exc}", level="error")
        return redirect(self._change_url(binding.pk))

    def rotate_token_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        if not binding.syncserver_device_id:
            self.message_user(request, "Нет SyncServer device id для rotate-token.", level="error")
            return redirect(self._change_url(binding.pk))
        try:
            response = DeviceSyncService().rotate_token(binding.syncserver_device_id)
            DeviceSyncService().apply_rotated_token(binding=binding, rotate_response=response)
            self.message_user(request, "Токен устройства перевыпущен и сохранён локально.", level="success")
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"Rotate-token завершился ошибкой: {exc}", level="error")
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось перевыпустить токен: {exc}", level="error")
        return redirect(self._change_url(binding.pk))

    def repair_from_syncserver_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        if not binding.syncserver_device_id:
            self.message_user(request, "Нет SyncServer binding для восстановления.", level="error")
            return redirect(self._change_url(binding.pk))
        try:
            DeviceSyncService().repair_binding_from_remote(binding=binding)
            self.message_user(request, "Карточка устройства восстановлена из SyncServer.", level="success")
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Repair из SyncServer завершился ошибкой: {exc}", level="error")
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось восстановить устройство из SyncServer: {exc}", level="error")
        return redirect(self._change_url(binding.pk))

    @admin.action(description="Repair selected device bindings from SyncServer")
    def repair_selected_bindings(self, request: HttpRequest, queryset):
        service = DeviceSyncService()
        repaired = 0
        failed = 0
        for binding in queryset:
            try:
                service.repair_binding_from_remote(binding=binding)
                repaired += 1
            except Exception as exc:
                failed += 1
                service.mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
        if repaired:
            self.message_user(request, f"Исправлено device binding-записей: {repaired}.", level="success")
        if failed:
            self.message_user(request, f"Не удалось восстановить device binding-записей: {failed}.", level="error")

    @admin.action(description="Mark selected device bindings as repair required")
    def mark_selected_for_repair(self, request: HttpRequest, queryset):
        updated = queryset.update(sync_status=SyncStatus.REPAIR_REQUIRED, updated_at=timezone.now())
        self.message_user(request, f"Помечено для ремонта device binding-записей: {updated}.", level="warning")

    @admin.action(description="Refresh device status from SyncServer")
    def refresh_device_status_action(self, request: HttpRequest, queryset):
        service = DeviceSyncService()
        refreshed = 0
        failed = 0
        for binding in queryset:
            try:
                service.refresh_device_status(binding=binding)
                refreshed += 1
            except Exception as exc:
                failed += 1
        if refreshed:
            self.message_user(request, f"Обновлён статус устройств: {refreshed}.", level="success")
        if failed:
            self.message_user(request, f"Не удалось обновить статус устройств: {failed}.", level="error")

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, change=change, **kwargs)

    def _change_url(self, object_id: int) -> str:
        return reverse("admin:users_syncdevicebinding_change", args=[object_id])


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class SyncManagedUserAdmin(BaseUserAdmin):
    add_form = SyncManagedUserCreationForm
    form = SyncManagedUserAdminForm
    change_form_template = "admin/auth/user/change_form.html"
    list_display = (
        "username",
        "email",
        "is_active",
        "is_superuser",
        "sync_role_display",
        "sync_status_display",
    )
    search_fields = ("username", "email")
    ordering = ("username",)

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password",
                    "password_confirm",
                    "full_name",
                    "sync_role",
                    "site_ids",
                    "is_active",
                    "sync_user_token",
                )
            },
        ),
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "email",
                    "password",
                    "password_confirm",
                    "full_name",
                    "sync_role",
                    "site_ids",
                    "sync_user_token",
                    "is_active",
                )
            },
        ),
    )

    superuser_fieldsets = BaseUserAdmin.fieldsets

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_view_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_change_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_delete_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        return False

    def get_queryset(self, request: HttpRequest):
        return super().get_queryset(request).select_related("sync_binding")

    def get_form(self, request: HttpRequest, obj=None, change=False, **kwargs):
        if obj and obj.is_superuser:
            kwargs["form"] = SuperuserLocalAdminForm
            return super().get_form(request, obj, change=change, **kwargs)

        service = UserSyncService()
        site_choices: list[tuple[str, str]] = []
        try:
            site_choices = [
                (str(site["site_id"]), site["name"])
                for site in service.list_sites()
                if site.get("is_active", True)
            ]
        except Exception as exc:
            self.message_user(
                request,
                f"Не удалось получить список складов из SyncServer: {exc}",
                level=messages.warning,
            )

        base_form = self.add_form if obj is None else self.form

        form_attrs = {name: copy.deepcopy(field) for name, field in base_form.declared_fields.items()}
        form_attrs["site_choices"] = site_choices
        BoundForm = type(f"{base_form.__name__}Bound", (base_form,), form_attrs)
        kwargs["form"] = BoundForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request: HttpRequest, obj=None):
        if obj and obj.is_superuser:
            return self.superuser_fieldsets
        return self.add_fieldsets if obj is None else self.fieldsets

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        if obj and obj.is_superuser:
            return super().get_readonly_fields(request, obj)
        return ()

    def save_model(self, request: HttpRequest, obj: User, form, change: bool) -> None:
        if obj.is_superuser:
            super().save_model(request, obj, form, change)
            return

        desired = getattr(form, "_desired_intent", None)
        if desired is None:
            raise RuntimeError("Sync intent was not prepared before saving.")

        obj.email = form.cleaned_data["email"]
        obj.first_name = desired["full_name"]
        obj.is_staff = False
        obj.is_superuser = False

        with transaction.atomic():
            obj.save()
            binding, _ = SyncUserBinding.objects.get_or_create(user=obj)

            if not binding.syncserver_user_id:
                binding.syncserver_user_id = uuid4()

            binding.sync_role = desired["role"]
            binding.default_site_id = desired["default_site_id"]
            binding.site_ids = desired["site_ids"]
            binding.sync_status = SyncStatus.PENDING
            binding.last_sync_error = ""
            binding.last_sync_at = timezone.now()
            binding.save()

            binding_pk = binding.pk

            transaction.on_commit(
                lambda: self._run_user_sync(
                    request=request,
                    user=obj,
                    binding_pk=binding_pk,
                    desired=desired,
                )
            )

    def _run_user_sync(self, request, user, binding_pk, desired):
        """Remote sync after local commit. Runs outside atomic."""
        from apps.users.models import SyncUserBinding
        from apps.users.services import UserSyncService

        service = UserSyncService()
        try:
            binding = SyncUserBinding.objects.get(pk=binding_pk)
            service.sync_user_to_remote(
                user=user,
                binding=binding,
                full_name=desired["full_name"],
                role=desired["role"],
                site_ids=desired["site_ids"],
                default_site_id=desired["default_site_id"],
            )
            self.message_user(
                request,
                "Пользователь синхронизирован с SyncServer.",
                level="success",
            )
        except SyncServerAPIError as exc:
            try:
                binding = SyncUserBinding.objects.get(pk=binding_pk)
                service.mark_failure(binding=binding, error=exc)
            except SyncUserBinding.DoesNotExist:
                pass
            self.message_user(
                request,
                f"Локальные данные сохранены. Ошибка синхронизации с SyncServer: {exc}. "
                f"Binding помечен для ремонта.",
                level="warning",
            )
        except Exception as exc:
            try:
                binding = SyncUserBinding.objects.get(pk=binding_pk)
                service.mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            except SyncUserBinding.DoesNotExist:
                pass
            self.message_user(
                request,
                f"Локальные данные сохранены. Не удалось синхронизировать с SyncServer: {exc}",
                level="error",
            )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/sync/",
                self.admin_site.admin_view(self.sync_with_syncserver_view),
                name="users_user_sync",
            ),
            path(
                "<path:object_id>/rotate-token/",
                self.admin_site.admin_view(self.rotate_token_view),
                name="users_user_rotate_token",
            ),
            path(
                "<path:object_id>/repair/",
                self.admin_site.admin_view(self.repair_from_syncserver_view),
                name="users_user_repair",
            ),
        ]
        return custom_urls + urls

    def sync_with_syncserver_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        user = get_object_or_404(User, pk=object_id)
        if user.is_superuser:
            self.message_user(
                request,
                "Root-пользователь не синхронизируется через этот flow.",
                level=messages.warning,
            )
            return redirect(self._change_url(user.pk))

        binding = self._get_binding(user)
        if binding is None:
            self.message_user(
                request,
                "У пользователя нет локальной SyncServer binding-записи.",
                level=messages.error,
            )
            return redirect(self._change_url(user.pk))

        try:
            UserSyncService().sync_existing_binding(user=user, binding=binding)
            self.message_user(
                request,
                "Пользователь успешно синхронизирован с SyncServer.",
                level=messages.success,
            )
        except SyncServerAPIError as exc:
            UserSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"SyncServer вернул ошибку: {exc}", level="error")
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось синхронизировать пользователя: {exc}", level="error")

        return redirect(self._change_url(user.pk))

    def rotate_token_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        user = get_object_or_404(User, pk=object_id)
        if user.is_superuser:
            self.message_user(request, "Root token не ротируется через API.", level="warning")
            return redirect(self._change_url(user.pk))

        binding = self._get_binding(user)
        if binding is None or not binding.syncserver_user_id:
            self.message_user(request, "Нет SyncServer user id для rotate-token.", level="error")
            return redirect(self._change_url(user.pk))

        try:
            response = UserSyncService().rotate_token(binding.syncserver_user_id)
            UserSyncService().apply_rotated_token(binding=binding, rotate_response=response)
            self.message_user(
                request,
                "Токен пользователя перевыпущен и сохранён локально.",
                level=messages.success,
            )
        except SyncServerAPIError as exc:
            UserSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"Rotate-token завершился ошибкой: {exc}", level="error")
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось перевыпустить токен: {exc}", level="error")

        return redirect(self._change_url(user.pk))

    def repair_from_syncserver_view(self, request: HttpRequest, object_id: str):
        if request.method not in ("POST",):
            return HttpResponseNotAllowed(["POST"])
        if not (request.user.is_superuser and request.user.is_active):
            return HttpResponseForbidden()
        user = get_object_or_404(User, pk=object_id)
        if user.is_superuser:
            self.message_user(request, "Root-пользователь не ремонтируется через SyncServer repair flow.", level="warning")
            return redirect(self._change_url(user.pk))

        binding = self._get_binding(user)
        if binding is None or not binding.syncserver_user_id:
            self.message_user(request, "Нет SyncServer binding для восстановления.", level="error")
            return redirect(self._change_url(user.pk))

        try:
            UserSyncService().repair_binding_from_remote(user=user, binding=binding)
            self.message_user(request, "Карточка пользователя восстановлена из SyncServer.", level="success")
        except SyncServerAPIError as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Repair из SyncServer завершился ошибкой: {exc}", level="error")
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось восстановить пользователя из SyncServer: {exc}", level="error")

        return redirect(self._change_url(user.pk))

    @admin.display(description="Роль SyncServer")
    def sync_role_display(self, obj: User) -> str:
        binding = self._get_binding(obj)
        return binding.sync_role if binding else "-"

    @admin.display(description="Статус синхронизации")
    def sync_status_display(self, obj: User):
        binding = self._get_binding(obj)
        if not binding:
            return "-"

        colors = {
            SyncStatus.PENDING: "#b45309",
            SyncStatus.SYNCED: "#166534",
            SyncStatus.SYNC_FAILED: "#b91c1c",
            SyncStatus.REPAIR_REQUIRED: "#7c2d12",
            SyncStatus.MANUAL_OVERRIDE: "#1d4ed8",
        }
        color = colors.get(binding.sync_status, "#374151")
        return format_html(
            '<strong style="color:{};">{}</strong>',
            color,
            binding.get_sync_status_display(),
        )

    def _change_url(self, object_id: int) -> str:
        return reverse("admin:auth_user_change", args=[object_id])

    @staticmethod
    def _get_binding(user: User) -> SyncUserBinding | None:
        if not user.pk:
            return None
        try:
            return user.sync_binding
        except SyncUserBinding.DoesNotExist:
            return None


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Admin for login/logout audit history."""

    list_display = ("action", "user", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username", "ip_address")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "action", "ip_address", "user_agent", "request_id", "created_at")
    ordering = ("-created_at",)

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_view_permission(self, request: HttpRequest, obj: LoginAttempt | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: LoginAttempt | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: LoginAttempt | None = None) -> bool:
        return request.user.is_superuser and request.user.is_active
