from django.shortcuts import render

from authentication.decorators import permission_required_custom
from licensing.middleware import has_valid_license

from .utils import build_page_context


@permission_required_custom("dashboard", "view")
def dashboard(request):
    cards = [
        {
            "label": "Today Sales",
            "value": "0.00",
            "tone": "primary",
            "icon": "bi-receipt",
            "hint": "No invoices posted today",
        },
        {
            "label": "This Month Sales",
            "value": "0.00",
            "tone": "success",
            "icon": "bi-graph-up-arrow",
            "hint": "Month-to-date placeholder",
        },
        {
            "label": "Customer Outstanding",
            "value": "0.00",
            "tone": "warning",
            "icon": "bi-person-lines-fill",
            "hint": "Receivables pending setup",
        },
        {
            "label": "Supplier Payable",
            "value": "0.00",
            "tone": "danger",
            "icon": "bi-truck",
            "hint": "Payables pending setup",
        },
        {
            "label": "Cash / Bank Balance",
            "value": "0.00",
            "tone": "info",
            "icon": "bi-bank",
            "hint": "Accounts pending setup",
        },
        {
            "label": "License Status",
            "value": "Valid"
            if has_valid_license(request.session.get("company_id"))
            else "Pending",
            "tone": "secondary",
            "icon": "bi-shield-check",
            "hint": "Validation arrives in Phase 3",
        },
    ]
    quick_actions = [
        {"label": "New Quotation", "icon": "bi-file-earmark-plus", "url": "/sales/"},
        {"label": "New Invoice", "icon": "bi-receipt-cutoff", "url": "/sales/"},
        {"label": "New Receipt", "icon": "bi-cash-coin", "url": "/sales/"},
        {"label": "New Purchase", "icon": "bi-cart-plus", "url": "/purchases/"},
        {"label": "Backup", "icon": "bi-cloud-arrow-up", "url": "/backup/"},
    ]
    activity_items = [
        "Dashboard shell is ready for live accounting data.",
        "Database connection is configured through web_app/.env.",
        "Authentication and role permissions are planned for Phase 3.",
    ]
    context = build_page_context(
        "Dashboard",
        "Operational snapshot for sales, purchases, accounts, and licensing.",
    )
    context["dashboard_cards"] = cards
    context["quick_actions"] = quick_actions
    context["activity_items"] = activity_items
    return render(request, "dashboard.html", context)


def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)
