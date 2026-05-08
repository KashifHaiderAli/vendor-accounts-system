from django.shortcuts import render

from authentication.decorators import permission_required_custom

from .hardware_fingerprint import get_hardware_fingerprint
from .middleware import has_valid_license


@permission_required_custom("licensing", "view")
def index(request):
    is_valid = False
    company_id = request.session.get("company_id")
    if company_id:
        is_valid = has_valid_license(company_id)
    return render(
        request,
        "placeholder.html",
        {
            "page_title": "License Status",
            "license_is_valid": is_valid,
        },
    )


def expired(request):
    return render(
        request,
        "licensing/license_expired.html",
        {"hardware_fingerprint": get_hardware_fingerprint()},
    )
