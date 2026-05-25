from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


class AuthenticationRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        if not request.session.get("user_id"):
            messages.info(request, "Please login to continue.")
            login_url = reverse("authentication:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")

        return self.get_response(request)

    @staticmethod
    def _is_exempt_path(path):
        exempt_prefixes = (
            "/login/",
            "/logout/",
            "/license-expired/",
            "/static/",
        )
        return any(path.startswith(prefix) for prefix in exempt_prefixes)
