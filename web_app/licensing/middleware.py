from datetime import date

from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect

from core.audit_utils import log_license_failure

from .hardware_fingerprint import get_hardware_fingerprint


class LicenseValidationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        company_id = request.session.get("company_id")
        if not company_id:
            return self.get_response(request)

        if not has_valid_license(company_id):
            log_license_failure(request, f"License blocked path {request.path}.")
            messages.error(
                request,
                "License not found, expired, or hardware mismatch.",
            )
            return redirect("license_expired")

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


def has_valid_license(company_id) -> bool:
    fingerprint = get_hardware_fingerprint()
    today = date.today()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT license_type, start_date, expiry_date, is_lifetime, is_active
            FROM license_records
            WHERE company_id = %s
              AND is_active = 1
              AND hardware_fingerprint = %s
            ORDER BY is_lifetime DESC, expiry_date DESC, id DESC
            """,
            [company_id, fingerprint],
        )
        rows = cursor.fetchall()

    for license_type, start_date, expiry_date, is_lifetime, is_active in rows:
        if int(is_active or 0) != 1:
            continue
        if int(is_lifetime or 0) == 1:
            return True
        if str(license_type).lower() not in {"trial", "annual"}:
            continue
        if not start_date or not expiry_date:
            continue
        try:
            start = date.fromisoformat(str(start_date)[:10])
            expiry = date.fromisoformat(str(expiry_date)[:10])
        except ValueError:
            continue
        if start <= today <= expiry:
            return True

    return False
