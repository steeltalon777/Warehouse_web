from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError

from apps.users.models import Role, Site, SyncDeviceBinding, SyncUserBinding
from apps.users.services import DeviceSyncService, UserSyncService

User = get_user_model()


class ScrollableCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """CheckboxSelectMultiple with a scrollable container for the admin form."""

    class Media:
        css = {
            "all": ("css/scrollable-checkboxes.css",),
        }

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        css_class = context["widget"]["attrs"].get("class", "")
        context["widget"]["attrs"]["class"] = f"{css_class} scrollable-checkboxes".strip()
        return context


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
    site_ids = forms.MultipleChoiceField(
        label="Склады",
        choices=[],
        required=True,
        widget=ScrollableCheckboxSelectMultiple,
        help_text="Выберите один или несколько складов, к которым привязан пользователь.",
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
        self.fields["site_ids"].choices = self.site_choices
        self.fields["password"].help_text = ""
        self.fields["password"].initial = ""
        self.fields["password_confirm"].initial = ""
        self.fields["full_name"].initial = self.instance.first_name
        self._new_password = ""

        binding = self._get_binding()
        if binding:
            self.fields["sync_role"].initial = binding.sync_role
            self.fields["site_ids"].initial = [str(s) for s in (binding.site_ids or [])]
            self.fields["sync_user_token"].initial = binding.sync_user_token

        self._desired_intent = None

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        password = self._new_password
        password_confirm = cleaned_data.get("password_confirm") or ""
        if password or password_confirm:
            if password != password_confirm:
                raise ValidationError("Пароли не совпадают.")

        role = cleaned_data.get("sync_role")
        site_ids_list = [str(sid) for sid in (cleaned_data.get("site_ids") or [])]

        if not role:
            raise ValidationError("Роль обязательна.")
        if role == Role.ROOT:
            raise ValidationError("Root-пользователи не управляются через Django-admin.")
        if not site_ids_list:
            raise ValidationError("Нужно выбрать хотя бы один склад.")

        default_site_id = site_ids_list[0]

        self.instance.username = cleaned_data.get("username") or self.instance.username
        self.instance.email = cleaned_data.get("email") or ""
        self.instance.is_active = bool(cleaned_data.get("is_active", True))

        self._desired_intent = {
            "full_name": cleaned_data.get("full_name") or "",
            "role": role,
            "site_ids": site_ids_list,
            "default_site_id": default_site_id,
        }

        return cleaned_data

    def clean_password(self) -> str:
        """Preserve the stored hash when the password field is left empty."""
        self._new_password = self.cleaned_data.get("password", "")
        return self._new_password or self.instance.password

    def _get_binding(self) -> SyncUserBinding | None:
        if not self.instance.pk:
            return None
        try:
            return self.instance.sync_binding
        except SyncUserBinding.DoesNotExist:
            return None

    def save(self, commit: bool = True):
        user = super(UserChangeForm, self).save(commit=False)
        if self._new_password:
            user.set_password(self._new_password)
        if commit:
            user.save()
            if hasattr(self, "save_m2m"):
                self.save_m2m()
        return user


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
            self.fields["sync_device_token"].initial = self.instance.sync_device_token or ""

    def clean_device_code(self) -> str:
        return str(self.cleaned_data["device_code"]).strip()

    def clean_device_name(self) -> str:
        return str(self.cleaned_data["device_name"]).strip()


class SyncManagedDeviceCreationForm(SyncManagedDeviceAdminForm):
    class Meta(SyncManagedDeviceAdminForm.Meta):
        fields = ("device_code", "device_name", "is_active")
