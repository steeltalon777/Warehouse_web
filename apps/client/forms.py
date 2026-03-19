from django import forms


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
