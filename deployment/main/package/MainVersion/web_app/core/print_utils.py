from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.db import connection

from authentication.auth_utils import dictfetchone
from .logo_utils import get_company_logo_path, get_company_logo_url
from .print_settings import PREPRINTED_INVOICE_SETTINGS


def should_show_logo(request=None):
    if request is None:
        return False
    return request.GET.get("logo") == "1" or request.GET.get("pdf") == "1"


def is_pdf_copy(request=None):
    return bool(request and request.GET.get("pdf") == "1")


def get_digital_signature_path():
    signature_path = Path(settings.BASE_DIR) / "DigitalSignature" / "DigitalSignature.png"
    return signature_path if signature_path.exists() else None


def get_digital_signature_url():
    return "/digital-signature/" if get_digital_signature_path() else ""


def build_print_context(company_id, request=None, document_title="", force_logo=False, force_pdf=False):
    show_logo = force_logo or should_show_logo(request)
    company = None
    if company_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
                company = dictfetchone(cursor)
        except Exception:
            company = None
    return {
        "print_company": company or {},
        "logo_url": get_company_logo_url(company_id),
        "logo_path": get_company_logo_path(company_id),
        "show_logo": show_logo,
        "is_pdf": force_pdf or is_pdf_copy(request),
        "print_mode": "digital" if (force_pdf or is_pdf_copy(request)) else "with_logo" if show_logo else "without_logo",
        "document_title": document_title,
        "preprinted_invoice_settings": PREPRINTED_INVOICE_SETTINGS,
        "digital_signature_url": get_digital_signature_url(),
    }
