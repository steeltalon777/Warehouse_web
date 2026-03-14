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
    username = forms.CharField(max_length=150)
    full_name = forms.CharField(max_length=255, required=False)
    role = forms.CharField(max_length=64, required=False)
    is_active = forms.BooleanField(required=False, initial=True)


class UserAccessForm(forms.Form):
    user_id = forms.CharField(max_length=64)
    site_id = forms.CharField(max_length=64)
    role = forms.CharField(max_length=64, required=False)
