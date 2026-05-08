from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect, render

from .auth_utils import user_has_permission


def login_required_custom(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            messages.info(request, "Please login to continue.")
            return redirect("authentication:login")
        return view_func(request, *args, **kwargs)

    return wrapper


def permission_required_custom(permission_code, action="view"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.session.get("user_id"):
                messages.info(request, "Please login to continue.")
                return redirect("authentication:login")
            if not user_has_permission(request, permission_code, action):
                messages.error(request, "You do not have permission to access this page.")
                return render(request, "errors/403.html", status=403)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
