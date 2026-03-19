from django import forms


class DeviceForm(forms.Form):
    code = forms.CharField(max_length=64)
    name = forms.CharField(max_length=255)
    site_id = forms.CharField(max_length=64)
    is_active = forms.BooleanField(required=False, initial=True)
