from django.shortcuts import render

from .utils import build_page_context


def dashboard(request):
    cards = [
        {"label": "Today Sales", "value": "0.00", "tone": "primary"},
        {"label": "This Month Sales", "value": "0.00", "tone": "success"},
        {"label": "Customer Outstanding", "value": "0.00", "tone": "warning"},
        {"label": "Supplier Payable", "value": "0.00", "tone": "danger"},
        {"label": "Cash / Bank Balance", "value": "0.00", "tone": "info"},
        {"label": "License Status", "value": "Pending", "tone": "secondary"},
    ]
    context = build_page_context(
        "Dashboard",
        "Operational snapshot for sales, purchases, accounts, and licensing.",
    )
    context["dashboard_cards"] = cards
    return render(request, "dashboard.html", context)


def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)
