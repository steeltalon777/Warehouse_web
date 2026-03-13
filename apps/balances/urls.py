from django.urls import path

from .views import BalancesBySiteView, BalancesListView

app_name = "balances"

urlpatterns = [
    path("", BalancesListView.as_view(), name="list"),
    path("by-site/", BalancesBySiteView.as_view(), name="by_site"),
]
