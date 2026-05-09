from __future__ import annotations

from .logo_utils import get_company_logo_path, get_company_logo_url
from .print_settings import PREPRINTED_INVOICE_SETTINGS


def build_print_context(company_id):
    return {
        "logo_url": get_company_logo_url(company_id),
        "logo_path": get_company_logo_path(company_id),
        "preprinted_invoice_settings": PREPRINTED_INVOICE_SETTINGS,
    }
