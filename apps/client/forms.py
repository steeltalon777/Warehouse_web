from django import forms


class SyncUserForm(forms.Form):
    username = forms.CharField(max_length=150)
    full_name = forms.CharField(max_length=255, required=False)
    password = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput(render_value=True))
    role_id = forms.ChoiceField(required=False)
    site_id = forms.ChoiceField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, roles=None, sites=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role_id"].choices = [("", "— Не выбрано —")] + [
            (str(role.get("id") or role.get("code")), role.get("name") or role.get("code"))
            for role in (roles or [])
        ]
        self.fields["site_id"].choices = [("", "— Не выбрано —")] + [
            (str(site.get("id") or site.get("code")), site.get("name") or site.get("code"))
            for site in (sites or [])
        ]


class OperationCreateForm(forms.Form):
    item_id = forms.CharField(max_length=64)
    operation_type = forms.ChoiceField(
        choices=[
            ("receipt", "Приход"),
            ("issue", "Расход"),
            ("transfer", "Перемещение"),
            ("adjustment", "Корректировка"),
        ]
    )
    quantity = forms.DecimalField(max_digits=14, decimal_places=3)
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
