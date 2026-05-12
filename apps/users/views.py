from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect


def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    """
    Log out the current user and redirect to the configured login page.

    We intentionally allow GET here because the project already relies on
    redirect-based logout flows, and users may navigate to /users/logout/
    directly from the browser address bar.
    """
    logout(request)

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url:
        return redirect(next_url)

    return redirect(getattr(settings, "LOGOUT_REDIRECT_URL", "/users/login/"))
