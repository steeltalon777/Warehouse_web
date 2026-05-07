from django.urls import path

from .views import DocumentPdfView, GenerateOperationDocumentView

app_name = "documents"

urlpatterns = [
    path("operations/<str:operation_id>/generate/", GenerateOperationDocumentView.as_view(), name="operation_generate"),
    path("<str:document_id>/pdf/", DocumentPdfView.as_view(), name="pdf"),
]
