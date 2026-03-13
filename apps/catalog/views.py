from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.catalog.forms import CategoryForm, ItemForm, UnitForm
from apps.catalog.services import CatalogService
from apps.common.permissions import can_manage_catalog
from apps.sync_client.client import SyncServerClient


class CatalogHomeView(LoginRequiredMixin, TemplateView):
    template_name = "catalog/home.html"

    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        return super().dispatch(request, *args, **kwargs)


class CatalogAccessMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not can_manage_catalog(request.user):
            return HttpResponseForbidden("Нет доступа")
        site_id = (
                request.session.get("active_site")
                or getattr(getattr(request.user, "profile", None), "site_id", None)
        )
        self.service = CatalogService(SyncServerClient(user_id=request.user.id, site_id=site_id))
        return super().dispatch(request, *args, **kwargs)


class CategoryListView(CatalogAccessMixin, TemplateView):
    template_name = "catalog/category_list.html"

    def get(self, request, *args, **kwargs):
        result = self.service.list_categories()
        if not result.ok:
            messages.error(request, result.form_error)
            categories = []
        else:
            categories = result.data
        return render(request, self.template_name, {"categories": categories})


class CategoryCreateView(CatalogAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:category_list")

    def get(self, request):
        categories = self.service.list_categories().data or []
        form = CategoryForm(category_choices=categories)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        categories = self.service.list_categories().data or []
        form = CategoryForm(request.POST, category_choices=categories)
        if form.is_valid():
            result = self.service.create_category(form.cleaned_data)
            if result.ok:
                messages.success(request, "Категория создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class CategoryUpdateView(CatalogAccessMixin, View):
    template_name = "catalog/category_form.html"
    success_url = reverse_lazy("catalog:category_list")

    def _get_category(self, pk: str):
        result = self.service.list_categories()
        if not result.ok:
            return None, result
        for category in result.data:
            if str(category["id"]) == str(pk):
                return category, result
        return None, None

    def get(self, request, pk):
        categories = self.service.list_categories().data or []
        category, list_result = self._get_category(pk)
        if category is None:
            if list_result and not list_result.ok:
                messages.error(request, list_result.form_error)
            raise Http404("Категория не найдена")
        form = CategoryForm(initial=category, category_choices=[c for c in categories if str(c["id"]) != str(pk)])
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        categories = self.service.list_categories().data or []
        form = CategoryForm(request.POST, category_choices=[c for c in categories if str(c["id"]) != str(pk)])
        if form.is_valid():
            result = self.service.update_category(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "Категория обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("Категория не найдена")
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "update"})


class CategoryDeleteView(CatalogAccessMixin, View):
    template_name = "catalog/category_confirm_delete.html"
    success_url = reverse_lazy("catalog:category_list")

    def get(self, request, pk):
        return render(request, self.template_name, {"category_id": pk})

    def post(self, request, pk):
        result = self.service.update_category(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "Категория деактивирована.")
            return redirect(self.success_url)
        if result.not_found:
            raise Http404("Категория не найдена")
        messages.error(request, result.form_error)
        return render(request, self.template_name, {"category_id": pk})


class CategoryTreeView(CatalogAccessMixin, TemplateView):
    template_name = "catalog/category_tree.html"

    def get(self, request, *args, **kwargs):
        result = self.service.categories_tree()
        if not result.ok:
            messages.error(request, result.form_error)
            tree = []
        else:
            tree = result.data
        return render(request, self.template_name, {"categories": tree})


class UnitListView(CatalogAccessMixin, TemplateView):
    template_name = "catalog/unit_list.html"

    def get(self, request, *args, **kwargs):
        result = self.service.list_units()
        if not result.ok:
            messages.error(request, result.form_error)
            units = []
        else:
            units = result.data
        return render(request, self.template_name, {"units": units})


class UnitCreateView(CatalogAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("catalog:unit_list")

    def get(self, request):
        return render(request, self.template_name, {"form": UnitForm(), "mode": "create"})

    def post(self, request):
        form = UnitForm(request.POST)
        if form.is_valid():
            result = self.service.create_unit(form.cleaned_data)
            if result.ok:
                messages.success(request, "Единица создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class UnitUpdateView(CatalogAccessMixin, View):
    template_name = "catalog/unit_form.html"
    success_url = reverse_lazy("catalog:unit_list")

    def _find_unit(self, pk: str):
        result = self.service.list_units()
        if not result.ok:
            return None, result
        for unit in result.data:
            if str(unit["id"]) == str(pk):
                return unit, result
        return None, None

    def get(self, request, pk):
        unit, result = self._find_unit(pk)
        if unit is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("Единица не найдена")
        form = UnitForm(initial=unit)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        form = UnitForm(request.POST)
        if form.is_valid():
            result = self.service.update_unit(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "Единица обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("Единица не найдена")
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "update"})


class ItemListView(CatalogAccessMixin, TemplateView):
    template_name = "catalog/item_list.html"

    def get(self, request, *args, **kwargs):
        category_id = request.GET.get("category_id") or None
        search = request.GET.get("search") or None
        items_result = self.service.list_items(category_id=category_id, search=search)
        categories_result = self.service.list_categories()

        if not items_result.ok:
            messages.error(request, items_result.form_error)
            items = []
        else:
            items = items_result.data

        categories = categories_result.data if categories_result.ok else []
        return render(
            request,
            self.template_name,
            {"items": items, "categories": categories, "selected_category_id": category_id or "", "search": search or ""},
        )


class ItemCreateView(CatalogAccessMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("catalog:item_list")

    def _catalog_data(self):
        categories = self.service.list_categories().data or []
        units = self.service.list_units().data or []
        return categories, units

    def get(self, request):
        categories, units = self._catalog_data()
        form = ItemForm(categories=categories, units=units)
        return render(request, self.template_name, {"form": form, "mode": "create"})

    def post(self, request):
        categories, units = self._catalog_data()
        form = ItemForm(request.POST, categories=categories, units=units)
        if form.is_valid():
            result = self.service.create_item(form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ создана.")
                return redirect(self.success_url)
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "create"})


class ItemUpdateView(CatalogAccessMixin, View):
    template_name = "catalog/item_form.html"
    success_url = reverse_lazy("catalog:item_list")

    def _find_item(self, pk: str):
        result = self.service.list_items()
        if not result.ok:
            return None, result
        for item in result.data:
            if str(item["id"]) == str(pk):
                return item, result
        return None, None

    def get(self, request, pk):
        categories = self.service.list_categories().data or []
        units = self.service.list_units().data or []
        item, result = self._find_item(pk)
        if item is None:
            if result and not result.ok:
                messages.error(request, result.form_error)
            raise Http404("ТМЦ не найдена")
        form = ItemForm(initial=item, categories=categories, units=units)
        return render(request, self.template_name, {"form": form, "mode": "update"})

    def post(self, request, pk):
        categories = self.service.list_categories().data or []
        units = self.service.list_units().data or []
        form = ItemForm(request.POST, categories=categories, units=units)
        if form.is_valid():
            result = self.service.update_item(str(pk), form.cleaned_data)
            if result.ok:
                messages.success(request, "ТМЦ обновлена.")
                return redirect(self.success_url)
            if result.not_found:
                raise Http404("ТМЦ не найдена")
            form.add_error(None, result.form_error)
        return render(request, self.template_name, {"form": form, "mode": "update"})


class ItemDeactivateView(CatalogAccessMixin, View):
    success_url = reverse_lazy("catalog:item_list")

    def post(self, request, pk):
        result = self.service.update_item(str(pk), {"is_active": False})
        if result.ok:
            messages.success(request, "ТМЦ деактивирована.")
        elif result.not_found:
            raise Http404("ТМЦ не найдена")
        else:
            messages.error(request, result.form_error)
        return redirect(self.success_url)
