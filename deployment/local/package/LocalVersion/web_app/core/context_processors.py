from datetime import date

from django.db import connection
from django.urls import reverse

from authentication.auth_utils import dictfetchone, get_user_allowed_branches, user_has_permission
from core.edition_utils import get_app_version_label, get_edition_name, is_tax_enabled


SIDEBAR_GROUPS = [
    {
        "label": "Masters",
        "icon": "bi-collection",
        "url_name": "masters:index",
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
        "url_name": "sales:index",
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
        "url_name": "purchases:index",
        "items": [
            ("Supplier Purchases", "supplier_purchases", "purchases:supplier_purchases"),
            ("Purchase Returns", "purchase_returns", "purchases:returns"),
            ("Supplier Payments", "supplier_payments", "purchases:supplier_payments"),
        ],
    },
    {
        "label": "Services",
        "icon": "bi-briefcase",
        "url_name": "services:index",
        "items": [
            ("Service Contracts", "service_contracts", "services:contracts"),
        ],
    },
    {
        "label": "Inventory",
        "icon": "bi-boxes",
        "url_name": "inventory:index",
        "items": [
            ("Inventory Dashboard", "inventory", "inventory:index"),
            ("Stock Balance", "inventory", "inventory:stock_balance"),
            ("Item Ledger", "inventory", "inventory:item_ledger"),
            ("Stock In", "inventory", "inventory:stock_in"),
            ("Stock Out", "inventory", "inventory:stock_out"),
            ("Low Stock", "inventory", "inventory:low_stock"),
            ("Stock Adjustments", "inventory", "inventory:adjustments"),
        ],
    },
    {
        "label": "Accounts",
        "icon": "bi-journal-richtext",
        "url_name": "accounts_module:index",
        "items": [
            ("Chart of Accounts", "accounting_reports", "accounts_module:chart"),
            ("Journal Entries", "accounting_reports", "accounts_module:journals"),
            ("Expense Vouchers", "expense_heads", "accounts_module:expenses"),
        ],
    },
    {
        "label": "Reports",
        "icon": "bi-bar-chart",
        "url_name": "reports:index",
        "items": [
            ("Customer Reports", "customer_reports", "reports:customer_reports"),
            ("Supplier Reports", "supplier_reports", "reports:supplier_reports"),
            ("Sales Reports", "sales_reports", "reports:sales_reports"),
            ("Purchase Reports", "purchase_reports", "reports:purchase_reports"),
            ("Item / Product Reports", "sales_reports", "reports:item_reports"),
            ("Service Reports", "service_reports", "reports:service_reports"),
            ("Accounting Reports", "accounting_reports", "reports:accounting_reports"),
            ("Tax Summary", "accounting_reports", "reports:tax_reports"),
            ("Inventory Reports", "inventory", "reports:inventory_reports"),
            ("System / Audit Reports", "audit_log", "reports:system_reports"),
        ],
    },
    {
        "label": "System",
        "icon": "bi-shield-lock",
        "url_name": "backup:index",
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
            ("Users & Roles", "user_management", "settings_module:users_roles"),
            ("Role Management", "role_management", "settings_module:role_management"),
            ("Numbering Settings", "numbering_settings", "settings_module:numbering"),
            ("Tax Settings", "tax_settings", "settings_module:tax"),
            ("Inventory Settings", "company_settings", "settings_module:inventory"),
        ],
    },
]


def app_context(request):
    today = date.today()
    is_authenticated = bool(request.session.get("user_id"))
    tax_enabled = is_tax_enabled(request=request, company_id=request.session.get("company_id"))
    allowed_branches = []
    sidebar_groups = []
    can_view_dashboard = False

    if is_authenticated:
        refresh_session_company_branch(request)
        allowed_branches = get_user_allowed_branches(request.session.get("user_id"))
        can_view_dashboard = user_has_permission(request, "dashboard", "view")
        sidebar_groups = build_sidebar_groups(request)

    return {
        "system_name": "Corporate Supplier Accounts System" if tax_enabled else "Local Vendor Accounting System",
        "app_version": "0.1.0",
        "edition_name": get_edition_name(),
        "app_version_label": get_app_version_label(),
        "tax_enabled": tax_enabled,
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
    tax_enabled = is_tax_enabled(request=request, company_id=request.session.get("company_id"))
    groups = []
    for group in SIDEBAR_GROUPS:
        visible_items = []
        for label, permission_code, url_name in group["items"]:
            if not tax_enabled and url_name in {"reports:tax_reports", "settings_module:tax"}:
                continue
            if user_has_permission(request, permission_code, "view") or (
                permission_code == "inventory" and is_admin_session(request)
            ) or (
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
            group_url_name = group.get("url_name")
            group_url = reverse(group_url_name) if group_url_name else ""
            groups.append(
                {
                    "label": group["label"],
                    "icon": group["icon"],
                    "url": group_url,
                    "items": visible_items,
                    "active": any(item["active"] for item in visible_items) or (bool(group_url) and request.path == group_url),
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
