from django.shortcuts import render

from .auth_utils import is_phase_two_placeholder_login_enabled


def login_view(request):
    return render(
        request,
        "authentication/login.html",
        {"placeholder_login": is_phase_two_placeholder_login_enabled()},
    )
