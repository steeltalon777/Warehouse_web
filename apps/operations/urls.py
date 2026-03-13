from django.urls import path

from .views import OperationCreateView, OperationDetailView, OperationsListView

app_name = "operations"

urlpatterns = [
    path("", OperationsListView.as_view(), name="list"),
    path("create/", OperationCreateView.as_view(), name="create"),
    path("<str:operation_id>/", OperationDetailView.as_view(), name="detail"),
]
