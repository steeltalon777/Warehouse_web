from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError

from apps.sync_client.exceptions import SyncServerAPIError
from apps.users.models import Role, Site, SyncDeviceBinding, SyncUserBinding
from apps.users.services import DeviceSyncService, UserSyncService

User = get_user_model()


MANAGED_ROLE_CHOICES = [
    (Role.CHIEF_STOREKEEPER, "Главный кладовщик"),
    (Role.STOREKEEPER, "Кладовщик"),
    (Role.OBSERVER, "Обозреватель"),
]


class SyncManagedUserAdminForm(UserChangeForm):
    site_choices: list[tuple[str, str]] = []

    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Оставьте пустым, чтобы не менять локальный Django-пароль.",
    )
    password_confirm = forms.CharField(
        label="Подтвердите пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
    )
    full_name = forms.CharField(label="ФИО", max_length=255, required=False)
    sync_role = forms.ChoiceField(label="Роль", choices=MANAGED_ROLE_CHOICES)
    default_site_id = forms.ChoiceField(
        label="Склад",
        choices=[],
        required=True,
    )
    sync_user_token = forms.CharField(
        label="User token",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "readonly": "readonly",
                "style": "background:#f3f4f6;color:#6b7280;",
            }
        ),
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = ("username", "email", "is_active")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.service = UserSyncService()
        self.fields["default_site_id"].choices = self.site_choices
        self.fields["password"].help_text = ""
        self.fields["password"].initial = ""
        self.fields["password_confirm"].initial = ""
        self.fields["full_name"].initial = self.instance.first_name

        binding = self._get_binding()
        if binding:
            self.fields["sync_role"].initial = binding.sync_role
            self.fields["default_site_id"].initial = str(binding.default_site_id or "")
            self.fields["sync_user_token"].initial = binding.sync_user_token

        self._prepared_sync = None

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        password = cleaned_data.get("password") or ""
        password_confirm = cleaned_data.get("password_confirm") or ""
        if password or password_confirm:
            if password != password_confirm:
                raise ValidationError("Пароли не совпадают.")

        role = cleaned_data.get("sync_role")
        default_site_id = str(cleaned_data.get("default_site_id") or "")

        if not role:
            raise ValidationError("Роль обязательна.")
        if role == Role.ROOT:
            raise ValidationError("Root-пользователи не управляются через Django-admin.")
        if not default_site_id:
            raise ValidationError("Нужно выбрать склад.")

        site_ids = [default_site_id]

        self.instance.username = cleaned_data.get("username") or self.instance.username
        self.instance.email = cleaned_data.get("email") or ""
        self.instance.is_active = bool(cleaned_data.get("is_active", True))

        try:
            binding = self._get_binding()
            self._prepared_sync = self.service.prepare_sync(
                user=self.instance,
                full_name=cleaned_data.get("full_name") or "",
                role=role,
                site_ids=site_ids,
                default_site_id=default_site_id,
                syncserver_user_id=binding.syncserver_user_id if binding else None,
            )
        except SyncServerAPIError as exc:
            raise ValidationError(str(exc)) from exc

        return cleaned_data

    def _get_binding(self) -> SyncUserBinding | None:
        if not self.instance.pk:
            return None
        try:
            return self.instance.sync_binding
        except SyncUserBinding.DoesNotExist:
            return None


class SyncManagedUserCreationForm(SyncManagedUserAdminForm):
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(render_value=False),
        required=True,
    )
    password_confirm = forms.CharField(
        label="Подтвердите пароль",
        widget=forms.PasswordInput(render_value=False),
        required=True,
    )

    class Meta(SyncManagedUserAdminForm.Meta):
        fields = ("username", "email", "is_active")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = True
        self.fields["sync_user_token"].initial = ""
        self.instance.is_staff = False
        self.instance.is_superuser = False


class SuperuserLocalAdminForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class SyncManagedSiteAdminForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ("code", "name", "description", "is_active")

    def clean_code(self) -> str:
        return str(self.cleaned_data["code"]).strip()

    def clean_name(self) -> str:
        return str(self.cleaned_data["name"]).strip()


class SyncManagedDeviceAdminForm(forms.ModelForm):
    sync_device_token = forms.CharField(
        label="Device token",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "readonly": "readonly",
                "style": "background:#f3f4f6;color:#6b7280;",
            }
        ),
    )

    class Meta:
        model = SyncDeviceBinding
        fields = ("device_code", "device_name", "is_active", "sync_device_token")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.service = DeviceSyncService()
        if "sync_device_token" in self.fields:
            self.fields["sync_device_token"].initial = self.instance.sync_device_token

    def clean_device_code(self) -> str:
        return str(self.cleaned_data["device_code"]).strip()

    def clean_device_name(self) -> str:
        return str(self.cleaned_data["device_name"]).strip()
