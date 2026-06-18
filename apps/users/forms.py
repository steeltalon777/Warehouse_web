import structlog
from django import forms
from django.core.exceptions import ValidationError

logger = structlog.get_logger()


class UserProfileForm(forms.Form):
    current_password = forms.CharField(
        label="Текущий пароль",
        widget=forms.PasswordInput(render_value=False),
        required=True,
    )
    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Оставьте пустым, чтобы не менять пароль.",
    )
    new_password_confirm = forms.CharField(
        label="Подтвердите новый пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
    )
    full_name = forms.CharField(
        label="ФИО",
        max_length=255,
        required=False,
    )
    email = forms.EmailField(
        label="Email",
        required=False,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = user.first_name
        self.fields["email"].initial = user.email

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password")
        if not self.user.check_password(password):
            raise ValidationError("Неверный текущий пароль.")
        return password

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("new_password") or ""
        confirm = cleaned.get("new_password_confirm") or ""
        if pwd or confirm:
            if pwd != confirm:
                raise ValidationError("Новый пароль и подтверждение не совпадают.")
            if len(pwd) < 8:
                raise ValidationError("Новый пароль должен быть не менее 8 символов.")
        return cleaned
