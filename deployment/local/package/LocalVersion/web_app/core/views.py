from django.http import FileResponse, Http404
from django.shortcuts import render

from authentication.decorators import permission_required_custom
from .dashboard_utils import dashboard_data
from .logo_utils import get_company_logo_path

from .utils import build_page_context


@permission_required_custom("dashboard", "view")
def dashboard(request):
    context = build_page_context(
        "Dashboard",
        "Live branch snapshot for sales, purchases, cash flow, contracts, and alerts.",
    )
    context.update(dashboard_data(request))
    return render(request, "dashboard.html", context)


def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def company_logo(request):
    logo_path = get_company_logo_path(request.session.get("company_id"))
    if not logo_path:
        raise Http404("Company logo was not found.")
    return FileResponse(open(logo_path, "rb"))
