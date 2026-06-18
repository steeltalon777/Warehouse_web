import structlog
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect, render

from .forms import UserProfileForm
from apps.users.services import UserSyncService

logger = structlog.get_logger()


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


@login_required
def profile_view(request: HttpRequest):
    success = False
    if request.method == "POST":
        form = UserProfileForm(request.user, request.POST)
        if form.is_valid():
            user = request.user
            if form.cleaned_data.get("new_password"):
                user.set_password(form.cleaned_data["new_password"])
            user.first_name = form.cleaned_data.get("full_name") or ""
            user.email = form.cleaned_data.get("email") or ""
            user.save()

            # Sync to SyncServer (FIO/email only)
            try:
                binding = getattr(user, "sync_binding", None)
                if binding and binding.syncserver_user_id:
                    UserSyncService().sync_existing_binding(user=user, binding=binding)
            except Exception:
                logger.exception("Failed to sync profile to SyncServer")

            # Re-login after password change
            from django.contrib.auth import update_session_auth_hash
            if form.cleaned_data.get("new_password"):
                update_session_auth_hash(request, user)

            success = True
    else:
        form = UserProfileForm(request.user)

    return render(request, "users/profile.html", {"form": form, "success": success})
