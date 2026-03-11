from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from apps.common.permissions import can_manage_catalog
from apps.catalog.forms import CategoryForm, UnitForm, ItemForm
from apps.catalog.models import Category, Unit, Item

def catalog_home(request):
    if not request.user.is_authenticated or not can_manage_catalog(request.user):
        return HttpResponseForbidden("Нет доступа")

    return render(request, "catalog/home.html")


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "catalog/category_list.html"
    context_object_name = "categories"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Category.objects.select_related("parent").all()


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:category_list")

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:category_list")

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "catalog/category_confirm_delete.html"
    success_url = reverse_lazy("catalog:category_list")

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

class CategoryTreeView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "catalog/category_tree.html"
    context_object_name = "categories"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Category.objects.select_related("parent").all()

class UnitListView(LoginRequiredMixin, ListView):
    model = Unit
    template_name = "catalog/unit_list.html"
    context_object_name = "units"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class UnitCreateView(LoginRequiredMixin, CreateView):
    model = Unit
    form_class = UnitForm
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("catalog:unit_list")

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

class ItemListView(LoginRequiredMixin, ListView):
    model = Item
    template_name = "catalog/item_list.html"
    context_object_name = "items"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Item.objects.select_related("category", "unit").all()


class ItemCreateView(LoginRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("catalog:item_list")

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)