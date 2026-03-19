from django.urls import path

from .views import BalancesBySiteView, BalancesListView, BalancesSummaryView

app_name = "balances"

urlpatterns = [
    path("", BalancesListView.as_view(), name="list"),
    path("summary/", BalancesSummaryView.as_view(), name="summary"),
    path("by-site/", BalancesBySiteView.as_view(), name="by_site"),
]

