from datetime import date

from django.db import connection
from django.urls import reverse

from authentication.auth_utils import dictfetchone, get_user_allowed_branches, user_has_permission


SIDEBAR_GROUPS = [
    {
        "label": "Masters",
        "icon": "bi-collection",
        "items": [
            ("Customers", "customers", "masters:customers"),
            ("Suppliers", "suppliers", "masters:suppliers"),
            ("Items / Services", "item_services", "masters:items"),
            ("Cash / Bank Accounts", "cash_bank_accounts", "masters:cash_bank"),
            ("Expense Heads", "expense_heads", "masters:expense_heads"),
            ("Payment Terms", "payment_terms", "masters:payment_terms"),
        ],
    },
    {
        "label": "Sales",
        "icon": "bi-receipt",
        "items": [
            ("Quotations", "quotations", "sales:quotations"),
            ("Customer Confirmations / PO", "customer_confirmations", "sales:confirmations"),
            ("Delivery Challans", "delivery_challans", "sales:delivery_challans"),
            ("Sales Invoices / Cash Memo", "sales_invoices", "sales:invoices"),
            ("Sales Returns", "sales_returns", "sales:returns"),
            ("Customer Receipts", "customer_receipts", "sales:receipts"),
        ],
    },
    {
        "label": "Purchases",
        "icon": "bi-cart-check",
        "items": [
            ("Supplier Purchases", "supplier_purchases", "purchases:supplier_purchases"),
            ("Purchase Returns", "purchase_returns", "purchases:returns"),
            ("Supplier Payments", "supplier_payments", "purchases:supplier_payments"),
        ],
    },
    {
        "label": "Services",
        "icon": "bi-briefcase",
        "items": [
            ("Service Contracts", "service_contracts", "services:contracts"),
        ],
    },
    {
        "label": "Accounts",
        "icon": "bi-journal-richtext",
        "items": [
            ("Chart of Accounts", "accounting_reports", "accounts_module:chart"),
            ("Journal Entries", "accounting_reports", "accounts_module:journals"),
            ("Expense Vouchers", "expense_heads", "accounts_module:expenses"),
        ],
    },
    {
        "label": "Reports",
        "icon": "bi-bar-chart",
        "items": [
            ("Customer Reports", "customer_reports", "reports:customer_outstanding"),
            ("Supplier Reports", "supplier_reports", "reports:supplier_payable"),
            ("Sales Reports", "sales_reports", "reports:sales_invoices"),
            ("Purchase Reports", "purchase_reports", "reports:purchase_report"),
            ("Service Reports", "service_reports", "reports:service_contracts"),
            ("Accounting Reports", "accounting_reports", "reports:trial_balance"),
        ],
    },
    {
        "label": "System",
        "icon": "bi-shield-lock",
        "items": [
            ("Backup / Restore", "backup_restore", "backup:dashboard"),
            ("Audit Log", "audit_log", "backup:audit_log"),
            ("License Status", "licensing", "licensing:index"),
        ],
    },
    {
        "label": "Settings",
        "icon": "bi-sliders",
        "items": [
            ("Company Settings", "company_settings", "settings_module:company"),
            ("Branches", "branches", "settings_module:branches"),
            ("Users & Roles", "user_management", "masters:index"),
            ("Role Management", "role_management", "masters:index"),
            ("Numbering Settings", "numbering_settings", "settings_module:numbering"),
            ("Tax Settings", "tax_settings", "settings_module:tax"),
        ],
    },
]


def app_context(request):
    today = date.today()
    is_authenticated = bool(request.session.get("user_id"))
    allowed_branches = []
    sidebar_groups = []
    can_view_dashboard = False

    if is_authenticated:
        refresh_session_company_branch(request)
        allowed_branches = get_user_allowed_branches(request.session.get("user_id"))
        can_view_dashboard = user_has_permission(request, "dashboard", "view")
        sidebar_groups = build_sidebar_groups(request)

    return {
        "system_name": "Corporate Supplier Accounts System",
        "app_version": "0.1.0",
        "current_year": today.year,
        "current_date": today,
        "current_company_name": request.session.get("company_name", "Your Company Name"),
        "current_branch_name": request.session.get("current_branch_name", "No Branch Selected"),
        "logged_in_user_name": request.session.get("full_name", ""),
        "logged_in_role_name": request.session.get("role_name", ""),
        "is_authenticated_custom": is_authenticated,
        "is_master_user": int(request.session.get("is_master_user") or 0),
        "allowed_branches": allowed_branches,
        "sidebar_groups": sidebar_groups,
        "can_view_dashboard": can_view_dashboard,
        "user_has_permission": lambda permission_code, action="view": user_has_permission(
            request,
            permission_code,
            action,
        ),
    }


def build_sidebar_groups(request):
    groups = []
    for group in SIDEBAR_GROUPS:
        visible_items = []
        for label, permission_code, url_name in group["items"]:
            if user_has_permission(request, permission_code, "view") or (
                permission_code in {"audit_log", "backup_restore"} and is_admin_session(request)
            ):
                url = reverse(url_name)
                visible_items.append(
                    {
                        "label": label,
                        "permission_code": permission_code,
                        "url_name": url_name,
                        "url": url,
                        "active": request.path == url,
                    }
                )
        if visible_items:
            groups.append(
                {
                    "label": group["label"],
                    "icon": group["icon"],
                    "items": visible_items,
                    "active": any(item["active"] for item in visible_items),
                }
            )
    return groups


def is_admin_session(request):
    role_name = str(request.session.get("role_name") or "").lower()
    return int(request.session.get("is_master_user") or 0) == 1 or "admin" in role_name


def refresh_session_company_branch(request):
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    if not company_id:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT company_name FROM companies WHERE id = %s LIMIT 1",
            [company_id],
        )
        company = dictfetchone(cursor)
        if company:
            request.session["company_name"] = company["company_name"]
        if branch_id:
            cursor.execute(
                """
                SELECT branch_name
                FROM branches
                WHERE company_id = %s AND id = %s
                LIMIT 1
                """,
                [company_id, branch_id],
            )
            branch = dictfetchone(cursor)
            if branch:
                request.session["current_branch_name"] = branch["branch_name"]
