from django.contrib import messages
from django.shortcuts import redirect, render

from core.audit_utils import log_login, log_logout, log_permission_denied

from .auth_utils import (
    fetch_user_for_login,
    resolve_login_branch,
    set_current_branch,
    store_login_session,
    update_last_login,
    verify_password,
)
from .decorators import login_required_custom


def login_view(request):
    if request.session.get("user_id") and request.method == "GET":
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            messages.error(request, "Please enter both username and password.")
            return render(request, "authentication/login.html", {"username": username})

        user = fetch_user_for_login(username)
        if not user:
            messages.error(request, "Invalid username or password.")
            return render(request, "authentication/login.html", {"username": username})

        if int(user.get("is_active") or 0) != 1:
            messages.error(request, "This user account is inactive.")
            return render(request, "authentication/login.html", {"username": username})

        if int(user.get("role_is_active") or 0) != 1:
            messages.error(request, "This user's role is inactive.")
            return render(request, "authentication/login.html", {"username": username})

        if not verify_password(password, user["password_hash"], user["password_salt"]):
            messages.error(request, "Invalid username or password.")
            return render(request, "authentication/login.html", {"username": username})

        branch = resolve_login_branch(user)
        if not branch:
            messages.error(request, "No active branch is assigned to this user.")
            return render(request, "authentication/login.html", {"username": username})

        store_login_session(request, user, branch)
        update_last_login(user["id"])
        log_login(request, user["id"], user["company_id"], branch["id"])
        messages.success(request, "Login successful.")
        return redirect(request.GET.get("next") or "dashboard")

    return render(request, "authentication/login.html")


def logout_view(request):
    log_logout(request)
    request.session.flush()
    messages.success(request, "Logout successful.")
    return redirect("authentication:login")


@login_required_custom
def switch_branch_view(request, branch_id):
    if set_current_branch(request, branch_id):
        branch_name = request.session.get("current_branch_name", "selected branch")
        messages.success(request, f"Branch switched to {branch_name}.")
    else:
        log_permission_denied(request, "Branch Access", f"Branch switch denied for branch_id={branch_id}.")
        messages.error(request, "You are not assigned to the selected branch.")
    return redirect(request.META.get("HTTP_REFERER") or "dashboard")
