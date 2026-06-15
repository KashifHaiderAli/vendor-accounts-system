from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect

from authentication.auth_utils import dictfetchall
from core.audit_utils import log_license_failure

from .hardware_fingerprint import get_hardware_fingerprint
from .license_utils import evaluate_license_record


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
            "/license/",
            "/license-expired/",
            "/static/",
            "/favicon.ico",
            "/digital-signature/",
        )
        return any(path.startswith(prefix) for prefix in exempt_prefixes)


def has_valid_license(company_id) -> bool:
    fingerprint = get_hardware_fingerprint()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT license_type, hardware_fingerprint, license_key, start_date, expiry_date, is_lifetime, is_active
            FROM license_records
            WHERE company_id = %s
              AND is_active = 1
            ORDER BY is_lifetime DESC, expiry_date DESC, id DESC
            """,
            [company_id],
        )
        rows = dictfetchall(cursor)

    for row in rows:
        if evaluate_license_record(row, fingerprint).valid:
            return True

    return False
