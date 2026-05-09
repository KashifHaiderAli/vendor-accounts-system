from __future__ import annotations

from datetime import date, timedelta

from django.db import connection

from authentication.auth_utils import dictfetchall, dictfetchone
from authentication.auth_utils import user_has_permission
from licensing.middleware import has_valid_license


def money(value):
    return float(value or 0)


def table_exists(table_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [table_name])
        return cursor.fetchone() is not None


def scalar(sql, params=None, default=0):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def rows(sql, params=None):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchall(cursor)
    except Exception:
        return []


def dashboard_data(request):
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    today_text = today.isoformat()
    in_30 = (today + timedelta(days=30)).isoformat()
    in_15 = (today + timedelta(days=15)).isoformat()

    today_sales = scalar("SELECT COALESCE(SUM(grand_total),0) FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND invoice_date=%s AND status <> 'Cancelled'", [company_id, branch_id, today_text])
    month_sales = scalar("SELECT COALESCE(SUM(grand_total),0) FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND invoice_date >= %s AND invoice_date <= %s AND status <> 'Cancelled'", [company_id, branch_id, month_start, today_text])
    outstanding = scalar("SELECT COALESCE(SUM(balance_amount),0) FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND status <> 'Cancelled'", [company_id, branch_id])
    payable = scalar("SELECT COALESCE(SUM(balance_amount),0) FROM supplier_purchases WHERE company_id=%s AND branch_id=%s AND status <> 'Cancelled'", [company_id, branch_id])
    cash_bank = scalar(
        """
        SELECT COALESCE(SUM(jel.debit - jel.credit),0)
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id=jel.journal_entry_id
        JOIN cash_bank_accounts cb ON cb.account_id=jel.account_id
        WHERE je.company_id=%s AND je.branch_id=%s AND cb.company_id=%s AND cb.branch_id=%s AND cb.is_active=1
        """,
        [company_id, branch_id, company_id, branch_id],
    )
    receipts_today = scalar(
        """
        SELECT COALESCE(SUM(cr.amount),0)
        FROM customer_receipts cr
        LEFT JOIN journal_entries rev ON rev.reference_type='customer_receipt_cancel' AND rev.reference_id=cr.id
        WHERE cr.company_id=%s AND cr.branch_id=%s AND cr.receipt_date=%s AND rev.id IS NULL
        """,
        [company_id, branch_id, today_text],
    )
    payments_today = scalar(
        """
        SELECT COALESCE(SUM(sp.amount),0)
        FROM supplier_payments sp
        LEFT JOIN journal_entries rev ON rev.reference_type='supplier_payment_cancel' AND rev.reference_id=sp.id
        WHERE sp.company_id=%s AND sp.branch_id=%s AND sp.payment_date=%s AND rev.id IS NULL
        """,
        [company_id, branch_id, today_text],
    )
    active_contracts = scalar("SELECT COUNT(*) FROM service_contracts WHERE company_id=%s AND branch_id=%s AND status='Active'", [company_id, branch_id])
    expiring_contracts = scalar("SELECT COUNT(*) FROM service_contracts WHERE company_id=%s AND branch_id=%s AND status='Active' AND end_date IS NOT NULL AND end_date BETWEEN %s AND %s", [company_id, branch_id, today_text, in_30])

    license_info = get_license_info(company_id, branch_id, today_text, in_15)
    cards = [
        card("Today Sales", today_sales, "primary", "bi-receipt", "Posted invoices today"),
        card("This Month Sales", month_sales, "success", "bi-graph-up-arrow", "Month-to-date invoices"),
        card("Customer Outstanding", outstanding, "warning", "bi-person-lines-fill", "Open invoice balance"),
        card("Supplier Payable", payable, "danger", "bi-truck", "Open purchase balance"),
        card("Cash / Bank Balance", cash_bank, "info", "bi-bank", "Ledger balance"),
        card("Today Receipts", receipts_today, "success", "bi-cash-coin", "Non-reversed receipts"),
        card("Today Payments", payments_today, "danger", "bi-wallet2", "Non-reversed payments"),
        {"label": "Active Contracts", "value": str(active_contracts), "tone": "secondary", "icon": "bi-briefcase", "hint": f"{expiring_contracts} expiring soon"},
        {"label": "License Status", "value": license_info["label"], "tone": license_info["tone"], "icon": "bi-shield-check", "hint": license_info["hint"]},
    ]
    quick_actions = build_quick_actions(request)
    recent = {
        "invoices": rows("SELECT id, invoice_no, invoice_date, grand_total, status FROM sales_invoices WHERE company_id=%s AND branch_id=%s ORDER BY invoice_date DESC, id DESC LIMIT 5", [company_id, branch_id]),
        "receipts": rows("SELECT id, receipt_no, receipt_date, amount FROM customer_receipts WHERE company_id=%s AND branch_id=%s ORDER BY receipt_date DESC, id DESC LIMIT 5", [company_id, branch_id]),
        "purchases": rows("SELECT id, purchase_no, purchase_date, grand_total, status FROM supplier_purchases WHERE company_id=%s AND branch_id=%s ORDER BY purchase_date DESC, id DESC LIMIT 5", [company_id, branch_id]),
        "challans": rows("SELECT id, dc_no, dc_date, status FROM delivery_challans WHERE company_id=%s AND branch_id=%s ORDER BY dc_date DESC, id DESC LIMIT 5", [company_id, branch_id]),
        "activity": rows("SELECT action_type, module_name, description, activity_datetime FROM user_activity_log WHERE company_id=%s AND branch_id=%s ORDER BY activity_datetime DESC LIMIT 5", [company_id, branch_id]),
    }
    alerts = [
        {"label": "Overdue invoices", "value": scalar("SELECT COUNT(*) FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND due_date < %s AND balance_amount > 0 AND status <> 'Cancelled'", [company_id, branch_id, today_text])},
        {"label": "Contracts expiring in 30 days", "value": expiring_contracts},
        {"label": "Unpaid supplier purchases", "value": scalar("SELECT COUNT(*) FROM supplier_purchases WHERE company_id=%s AND branch_id=%s AND balance_amount > 0 AND status <> 'Cancelled'", [company_id, branch_id])},
        {"label": "Unsigned delivery challans", "value": scalar("SELECT COUNT(*) FROM delivery_challans WHERE company_id=%s AND branch_id=%s AND (signed_copy_path IS NULL OR signed_copy_path='') AND status NOT IN ('Cancelled','Invoiced')", [company_id, branch_id])},
    ]
    if license_info.get("expiring_soon"):
        alerts.append({"label": "License expiring soon", "value": license_info["hint"]})
    return {"dashboard_cards": cards, "quick_actions": quick_actions, "recent": recent, "alerts": alerts, "monthly_sales": monthly_series(company_id, branch_id, "sales_invoices", "invoice_date", "grand_total"), "monthly_receipts": monthly_series(company_id, branch_id, "customer_receipts", "receipt_date", "amount")}


def card(label, value, tone, icon, hint):
    return {"label": label, "value": f"{money(value):,.2f}", "tone": tone, "icon": icon, "hint": hint}


def build_quick_actions(request):
    actions = [
        ("New Quotation", "bi-file-earmark-text", "/sales/quotations/new/", "quotations"),
        ("New Invoice", "bi-receipt", "/sales/invoices/new/", "sales_invoices"),
        ("New Receipt", "bi-cash-coin", "/sales/receipts/new/", "customer_receipts"),
        ("New Purchase", "bi-bag-check", "/purchases/supplier-purchases/new/", "supplier_purchases"),
        ("New Expense Voucher", "bi-journal-plus", "/accounts/expenses/new/", "expense_heads"),
        ("New Service Contract", "bi-briefcase", "/services/contracts/new/", "service_contracts"),
        ("Backup", "bi-database-down", "/backup/", "backup_restore"),
    ]
    return [{"label": label, "icon": icon, "url": url} for label, icon, url, perm in actions if user_has_permission(request, perm, "add") or (perm == "backup_restore" and user_has_permission(request, perm, "view"))]


def get_license_info(company_id, branch_id, today_text, in_15):
    valid = has_valid_license(company_id)
    row = rows("SELECT * FROM license_records WHERE company_id=%s AND (branch_id=%s OR branch_id IS NULL) AND is_active=1 ORDER BY id DESC LIMIT 1", [company_id, branch_id])
    lic = row[0] if row else {}
    expiry = lic.get("expiry_date") or ""
    label = "Valid" if valid else "Expired"
    if valid and int(lic.get("is_lifetime") or 0) == 1:
        label = "Lifetime"
    elif valid and lic.get("license_type"):
        label = lic.get("license_type")
    return {"label": label, "tone": "success" if valid else "danger", "hint": f"Expires {expiry}" if expiry else "No expiry date", "expiring_soon": bool(valid and expiry and today_text <= expiry <= in_15)}


def monthly_series(company_id, branch_id, table, date_col, amount_col):
    data = []
    today = date.today()
    for offset in range(5, -1, -1):
        month = today.month - offset
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        start = date(year, month, 1)
        end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        value = scalar(f"SELECT COALESCE(SUM({amount_col}),0) FROM {table} WHERE company_id=%s AND branch_id=%s AND {date_col} >= %s AND {date_col} < %s", [company_id, branch_id, start.isoformat(), end.isoformat()])
        data.append({"label": start.strftime("%b"), "value": money(value)})
    max_value = max([item["value"] for item in data] or [1]) or 1
    for item in data:
        item["percent"] = int((item["value"] / max_value) * 100)
    return data
