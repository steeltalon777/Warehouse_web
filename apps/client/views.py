from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.common.permissions import can_use_client


@login_required
def dashboard(request):
    if not can_use_client(request.user):
        return HttpResponseForbidden("Нет доступа")

    return render(request, "client/dashboard.html")