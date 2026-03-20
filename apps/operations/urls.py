from django.urls import path

from .views import (
    CancelOperationView,
    OperationCreateView,
    OperationDetailView,
    OperationItemSearchView,
    OperationsListView,
    SubmitOperationView,
)

app_name = "operations"

urlpatterns = [
    path("", OperationsListView.as_view(), name="list"),
    path("create/", OperationCreateView.as_view(), name="create"),
    path("item-search/", OperationItemSearchView.as_view(), name="item_search"),
    path("<str:operation_id>/", OperationDetailView.as_view(), name="detail"),
    path("<str:operation_id>/submit/", SubmitOperationView.as_view(), name="submit"),
    path("<str:operation_id>/cancel/", CancelOperationView.as_view(), name="cancel"),
]
