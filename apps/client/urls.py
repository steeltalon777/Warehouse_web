from django.urls import path

from apps.client import views

app_name = "client"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("root/users/", views.root_users, name="root_users"),
    path("root/users/create/", views.root_user_create, name="root_user_create"),
    path("root/users/<str:user_id>/edit/", views.root_user_edit, name="root_user_edit"),
    path("catalog/", views.storekeeper_catalog, name="storekeeper_catalog"),
    path("balances/", views.balances_view, name="balances"),
    path("operations/", views.operations_view, name="operations"),
    path("operations/create/", views.operation_create, name="operation_create"),
]
