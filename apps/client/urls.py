from django.urls import path

from apps.client import views

app_name = "client"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]