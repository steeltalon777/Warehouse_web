from django import forms


class CategoryForm(forms.Form):
    name = forms.CharField(max_length=200)
    parent_id = forms.ChoiceField(required=False)
    code = forms.CharField(max_length=100, required=False)
    sort_order = forms.IntegerField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "— Без родителя —")]
        choices.extend((str(item["id"]), item["name"]) for item in (category_choices or []))
        self.fields["parent_id"].choices = choices
        self.fields["parent_id"].widget.attrs.update(
            {
                "data-searchable-select": "true",
                "data-placeholder": "Начните вводить категорию...",
            }
        )

    def clean_parent_id(self):
        value = self.cleaned_data.get("parent_id")
        if value in (None, ""):
            return None
        return int(value)


class UnitForm(forms.Form):
    name = forms.CharField(max_length=100)
    symbol = forms.CharField(max_length=20)
    sort_order = forms.IntegerField(required=False)
    is_active = forms.BooleanField(required=False, initial=True)


class ItemForm(forms.Form):
    name = forms.CharField(max_length=255)
    sku = forms.CharField(max_length=100, required=False)
    category_id = forms.ChoiceField(required=False)
    unit_id = forms.ChoiceField(required=True)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, categories=None, units=None, **kwargs):
        super().__init__(*args, **kwargs)

        category_choices = [("", "— Автоматически: Без категории —")]
        category_choices.extend((str(item["id"]), item["name"]) for item in (categories or []))
        self.fields["category_id"].choices = category_choices
        self.fields["category_id"].widget.attrs.update(
            {
                "data-searchable-select": "true",
                "data-placeholder": "Начните вводить категорию...",
            }
        )
        self.fields["category_id"].help_text = (
            'Если категорию не выбрать, товар будет сохранён в системную категорию "Без категории".'
        )

        unit_choices = [
            (
                str(item["id"]),
                f'{item.get("symbol") or item.get("code") or "?"} — {item["name"]}',
            )
            for item in (units or [])
        ]
        self.fields["unit_id"].choices = unit_choices
        self.fields["unit_id"].widget.attrs.update(
            {
                "data-searchable-select": "true",
                "data-placeholder": "Начните вводить единицу измерения...",
            }
        )

    def clean_category_id(self):
        value = self.cleaned_data.get("category_id")
        if value in (None, ""):
            return None
        return int(value)

    def clean_unit_id(self):
        value = self.cleaned_data.get("unit_id")
        if value in (None, ""):
            raise forms.ValidationError("Выберите единицу измерения.")
        return int(value)
