from __future__ import annotations

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.sync_client.exceptions import SyncServerAPIError
from apps.users.admin_forms import (
    SuperuserLocalAdminForm,
    SyncManagedDeviceAdminForm,
    SyncManagedSiteAdminForm,
    SyncManagedUserAdminForm,
    SyncManagedUserCreationForm,
)
from apps.users.models import Site, SyncDeviceBinding, SyncStatus, SyncUserBinding
from apps.users.services import DeviceSyncService, SiteSyncService, UserSyncService

User = get_user_model()


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    form = SyncManagedSiteAdminForm
    list_display = ("name", "code", "syncserver_site_id", "is_active", "updated_at")
    search_fields = ("name", "code", "syncserver_site_id")
    readonly_fields = ("syncserver_site_id", "created_at", "updated_at")
    fields = ("code", "name", "description", "is_active", "syncserver_site_id", "created_at", "updated_at")
    actions = None

    def get_queryset(self, request: HttpRequest):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            try:
                SiteSyncService().refresh_local_cache()
            except Exception as exc:
                self.message_user(
                    request,
                    f"Не удалось обновить список складов из SyncServer: {exc}",
                    level=messages.warning,
                )
        return queryset

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return request.user.is_superuser

    def has_delete_permission(self, request: HttpRequest, obj: Site | None = None) -> bool:
        return False

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
    actions = ("repair_selected_bindings", "mark_selected_for_repair")
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
                    "default_site_id",
                    "site_ids",
                    "sync_user_token",
                    "sync_status",
                    "last_sync_error",
                    "last_sync_payload_pretty",
                    "last_sync_at",
                    "token_rotated_at",
                    "manual_token_updated_at",
                    "manual_token_updated_by",
                )
            },
        ),
    )

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

    @admin.action(description="Repair selected bindings from SyncServer")
    def repair_selected_bindings(self, request: HttpRequest, queryset):
        service = UserSyncService()
        repaired = 0
        failed = 0

        for binding in queryset.select_related("user"):
            try:
                service.repair_binding_from_remote(user=binding.user, binding=binding)
                repaired += 1
            except Exception as exc:
                failed += 1
                service.mark_failure(
                    binding=binding,
                    error=exc,
                    status=SyncStatus.REPAIR_REQUIRED,
                )

        if repaired:
            self.message_user(request, f"Исправлено binding-записей: {repaired}.", level=messages.success)
        if failed:
            self.message_user(request, f"Не удалось восстановить binding-записей: {failed}.", level=messages.error)

    @admin.action(description="Mark selected bindings as repair required")
    def mark_selected_for_repair(self, request: HttpRequest, queryset):
        updated = queryset.update(sync_status=SyncStatus.REPAIR_REQUIRED, updated_at=timezone.now())
        self.message_user(request, f"Помечено для ремонта binding-записей: {updated}.", level=messages.warning)


@admin.register(SyncDeviceBinding)
class SyncDeviceBindingAdmin(admin.ModelAdmin):
    form = SyncManagedDeviceAdminForm
    change_form_template = "admin/users/syncdevicebinding/change_form.html"
    actions = ("repair_selected_bindings", "mark_selected_for_repair")
    list_display = (
        "device_code",
        "device_name",
        "is_active",
        "sync_status",
        "last_sync_at",
        "masked_device_token",
    )
    search_fields = ("device_code", "device_name", "syncserver_device_id")
    readonly_fields = (
        "syncserver_device_id",
        "sync_device_token",
        "last_sync_at",
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
        "last_sync_error",
        "last_sync_payload_pretty",
        "last_sync_at",
        "token_rotated_at",
        "manual_token_updated_at",
        "manual_token_updated_by",
        "created_at",
        "updated_at",
    )

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj: SyncDeviceBinding | None = None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj: SyncDeviceBinding | None = None) -> bool:
        return request.user.is_superuser

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

    def save_model(self, request: HttpRequest, obj: SyncDeviceBinding, form, change: bool) -> None:
        service = DeviceSyncService()
        try:
            with transaction.atomic():
                super().save_model(request, obj, form, change)
                if change:
                    service.sync_existing_binding(binding=obj)
                else:
                    service.create_binding(binding=obj)
        except Exception as exc:
            if obj.pk:
                service.mark_failure(binding=obj, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            raise

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
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        try:
            DeviceSyncService().sync_existing_binding(binding=binding)
            self.message_user(request, "Устройство успешно синхронизировано с SyncServer.", level=messages.success)
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"SyncServer вернул ошибку: {exc}", level=messages.error)
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось синхронизировать устройство: {exc}", level=messages.error)
        return redirect(self._change_url(binding.pk))

    def rotate_token_view(self, request: HttpRequest, object_id: str):
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        if not binding.syncserver_device_id:
            self.message_user(request, "Нет SyncServer device id для rotate-token.", level=messages.error)
            return redirect(self._change_url(binding.pk))
        try:
            response = DeviceSyncService().rotate_token(binding.syncserver_device_id)
            DeviceSyncService().apply_rotated_token(binding=binding, rotate_response=response)
            self.message_user(request, "Токен устройства перевыпущен и сохранён локально.", level=messages.success)
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc)
            self.message_user(request, f"Rotate-token завершился ошибкой: {exc}", level=messages.error)
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось перевыпустить токен: {exc}", level=messages.error)
        return redirect(self._change_url(binding.pk))

    def repair_from_syncserver_view(self, request: HttpRequest, object_id: str):
        binding = get_object_or_404(SyncDeviceBinding, pk=object_id)
        if not binding.syncserver_device_id:
            self.message_user(request, "Нет SyncServer binding для восстановления.", level=messages.error)
            return redirect(self._change_url(binding.pk))
        try:
            DeviceSyncService().repair_binding_from_remote(binding=binding)
            self.message_user(request, "Карточка устройства восстановлена из SyncServer.", level=messages.success)
        except SyncServerAPIError as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Repair из SyncServer завершился ошибкой: {exc}", level=messages.error)
        except Exception as exc:
            DeviceSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось восстановить устройство из SyncServer: {exc}", level=messages.error)
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
            self.message_user(request, f"Исправлено device binding-записей: {repaired}.", level=messages.success)
        if failed:
            self.message_user(request, f"Не удалось восстановить device binding-записей: {failed}.", level=messages.error)

    @admin.action(description="Mark selected device bindings as repair required")
    def mark_selected_for_repair(self, request: HttpRequest, queryset):
        updated = queryset.update(sync_status=SyncStatus.REPAIR_REQUIRED, updated_at=timezone.now())
        self.message_user(request, f"Помечено для ремонта device binding-записей: {updated}.", level=messages.warning)

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
                    "default_site_id",
                    "is_active",
                    "sync_user_token",
                ),
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
                    "default_site_id",
                    "sync_user_token",
                    "is_active",
                )
            },
        ),
    )

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

        class BoundForm(base_form):
            pass

        BoundForm.site_choices = site_choices
        kwargs["form"] = BoundForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request: HttpRequest, obj=None):
        if obj and obj.is_superuser:
            return super().get_fieldsets(request, obj)
        return self.add_fieldsets if obj is None else self.fieldsets

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        if obj and obj.is_superuser:
            return super().get_readonly_fields(request, obj)
        return ()

    def save_model(self, request: HttpRequest, obj: User, form, change: bool) -> None:
        if obj.is_superuser:
            super().save_model(request, obj, form, change)
            return

        prepared = getattr(form, "_prepared_sync", None)
        if prepared is None:
            raise RuntimeError("Sync state was not prepared before saving the user.")

        password = form.cleaned_data.get("password")
        obj.email = form.cleaned_data["email"]
        obj.first_name = form.cleaned_data.get("full_name") or ""
        obj.is_staff = False
        obj.is_superuser = False
        if password:
            obj.set_password(password)

        service = UserSyncService()
        binding = None
        try:
            with transaction.atomic():
                obj.save()
                binding, _ = SyncUserBinding.objects.get_or_create(user=obj)
                binding.sync_role = form.cleaned_data["sync_role"]
                binding.default_site_id = str(form.cleaned_data["default_site_id"])
                binding.site_ids = [str(form.cleaned_data["default_site_id"])]
                binding.sync_status = SyncStatus.PENDING
                binding.last_sync_error = ""
                binding.last_sync_at = timezone.now()
                binding.save()

                service.apply_prepared_state(
                    user=obj,
                    binding=binding,
                    prepared=prepared,
                    role=form.cleaned_data["sync_role"],
                    site_ids=[str(form.cleaned_data["default_site_id"])],
                    default_site_id=str(form.cleaned_data["default_site_id"]),
                )
        except Exception as exc:
            if binding and binding.pk:
                service.mark_failure(
                    binding=binding,
                    error=exc,
                    payload=getattr(prepared, "sync_state_response", None) or getattr(prepared, "sync_user_response", None),
                    status=SyncStatus.REPAIR_REQUIRED,
                )
            raise

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
            self.message_user(request, f"SyncServer вернул ошибку: {exc}", level=messages.error)
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось синхронизировать пользователя: {exc}", level=messages.error)

        return redirect(self._change_url(user.pk))

    def rotate_token_view(self, request: HttpRequest, object_id: str):
        user = get_object_or_404(User, pk=object_id)
        if user.is_superuser:
            self.message_user(request, "Root token не ротируется через API.", level=messages.warning)
            return redirect(self._change_url(user.pk))

        binding = self._get_binding(user)
        if binding is None or not binding.syncserver_user_id:
            self.message_user(request, "Нет SyncServer user id для rotate-token.", level=messages.error)
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
            self.message_user(request, f"Rotate-token завершился ошибкой: {exc}", level=messages.error)
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось перевыпустить токен: {exc}", level=messages.error)

        return redirect(self._change_url(user.pk))

    def repair_from_syncserver_view(self, request: HttpRequest, object_id: str):
        user = get_object_or_404(User, pk=object_id)
        if user.is_superuser:
            self.message_user(request, "Root-пользователь не ремонтируется через SyncServer repair flow.", level=messages.warning)
            return redirect(self._change_url(user.pk))

        binding = self._get_binding(user)
        if binding is None or not binding.syncserver_user_id:
            self.message_user(request, "Нет SyncServer binding для восстановления.", level=messages.error)
            return redirect(self._change_url(user.pk))

        try:
            UserSyncService().repair_binding_from_remote(user=user, binding=binding)
            self.message_user(request, "Карточка пользователя восстановлена из SyncServer.", level=messages.success)
        except SyncServerAPIError as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Repair из SyncServer завершился ошибкой: {exc}", level=messages.error)
        except Exception as exc:
            UserSyncService().mark_failure(binding=binding, error=exc, status=SyncStatus.REPAIR_REQUIRED)
            self.message_user(request, f"Не удалось восстановить пользователя из SyncServer: {exc}", level=messages.error)

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
