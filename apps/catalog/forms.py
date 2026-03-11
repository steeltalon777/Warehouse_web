from django import forms

from apps.catalog.models import Category, Unit, Item


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "code", "sort_order", "is_active"]


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ["code", "name"]


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["name", "sku", "category", "unit", "is_active"]