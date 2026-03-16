from django import forms


class SiteForm(forms.Form):
    code = forms.CharField(max_length=64)
    name = forms.CharField(max_length=255)
    is_active = forms.BooleanField(required=False, initial=True)


class DeviceForm(forms.Form):
    code = forms.CharField(max_length=64)
    name = forms.CharField(max_length=255)
    site_id = forms.CharField(max_length=64)
    is_active = forms.BooleanField(required=False, initial=True)


class UserCreateForm(forms.Form):

    username = forms.CharField(label="Логин", max_length=150)

    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput()
    )

    password_confirm = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput()
    )

    full_name = forms.CharField(
        label="ФИО",
        max_length=255,
        required=False
    )

    email = forms.EmailField(
        label="Email",
        required=False
    )

    site_id = forms.CharField(
        label="Склад",
        max_length=64
    )

    role = forms.CharField(
        label="Роль",
        max_length=64
    )

    is_active = forms.BooleanField(
        label="Активен",
        required=False,
        initial=True
    )

    def clean(self):
        cleaned = super().clean()

        password = cleaned.get("password")
        password_confirm = cleaned.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Пароли не совпадают")

        return cleaned


class UserAccessForm(forms.Form):

    user_id = forms.CharField(max_length=64)

    site_id = forms.CharField(max_length=64)

    role = forms.CharField(
        max_length=64,
        required=False
    )