from __future__ import annotations

from django.contrib import messages
from django.shortcuts import render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom
from core.print_utils import build_print_context
from core.audit_utils import log_export_report
from core.utils import build_page_context

from .export_utils import csv_response
from . import report_utils as reports


REPORT_CATEGORIES = [
    ("Customer Reports", "bi-people", "Customer ledgers, statements, outstanding, aging, sales, and receipts.", "reports:customer_outstanding", ("customer_reports", "customers")),
    ("Supplier Reports", "bi-truck", "Supplier ledgers, payable, aging, purchases, and payments.", "reports:supplier_payable", ("supplier_reports", "suppliers")),
    ("Sales Reports", "bi-receipt", "Quotations, confirmations, challans, invoices, returns, receipts, and tax.", "reports:sales_invoices", ("sales_reports", "sales_invoices")),
    ("Purchase Reports", "bi-bag-check", "Purchases, purchase returns, supplier payments, tax, and profit views.", "reports:purchase_report", ("purchase_reports", "supplier_purchases")),
    ("Service Reports", "bi-briefcase", "Contracts, expiring contracts, billing due, and invoice history.", "reports:service_contracts", ("service_reports", "service_contracts")),
    ("Accounting Reports", "bi-journal-richtext", "Cash book, bank book, ledger, trial balance, profit and loss, and balance sheet.", "reports:trial_balance", ("accounting_reports", "accounting_reports")),
]


def col(key, label, kind="text"):
    return {"key": key, "label": label, "kind": kind}


REPORTS = {
    "customer_ledger": {
        "title": "Customer Ledger",
        "permission": ("customer_reports", "customers"),
        "function": reports.customer_ledger,
        "columns": [
            col("date", "Date"), col("entry_no", "Entry No"), col("reference_type", "Reference"),
            col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money"),
        ],
        "needs_customer": True,
    },
    "customer_outstanding": {
        "title": "Customer Outstanding",
        "permission": ("customer_reports", "sales_invoices"),
        "function": reports.customer_outstanding,
        "columns": [
            col("customer", "Customer"), col("invoice_no", "Invoice No"), col("invoice_date", "Date"), col("due_date", "Due Date"),
            col("grand_total", "Grand Total", "money"), col("received_amount", "Received", "money"), col("balance_amount", "Balance", "money"), col("status", "Status"),
        ],
    },
    "customer_aging": {
        "title": "Customer Aging",
        "permission": ("customer_reports", "sales_invoices"),
        "function": reports.customer_aging,
        "columns": [col("customer", "Customer"), col("total", "Total", "money"), col("b0_30", "0-30", "money"), col("b31_60", "31-60", "money"), col("b61_90", "61-90", "money"), col("b90_plus", "90+", "money")],
    },
    "customer_statement": {
        "title": "Customer Statement",
        "permission": ("customer_reports", "customers"),
        "function": reports.customer_statement,
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Ref No"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_customer": True,
    },
    "supplier_ledger": {
        "title": "Supplier Ledger",
        "permission": ("supplier_reports", "suppliers"),
        "function": reports.supplier_ledger,
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("reference_type", "Reference"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_supplier": True,
    },
    "supplier_payable": {
        "title": "Supplier Payable",
        "permission": ("supplier_reports", "supplier_purchases"),
        "function": reports.supplier_payable,
        "columns": [col("supplier", "Supplier"), col("purchase_no", "Purchase No"), col("purchase_date", "Date"), col("supplier_bill_no", "Bill No"), col("grand_total", "Grand Total", "money"), col("paid_amount", "Paid", "money"), col("balance_amount", "Balance", "money"), col("status", "Status")],
    },
    "supplier_aging": {
        "title": "Supplier Aging",
        "permission": ("supplier_reports", "supplier_purchases"),
        "function": reports.supplier_aging,
        "columns": [col("supplier", "Supplier"), col("total", "Total", "money"), col("b0_30", "0-30", "money"), col("b31_60", "31-60", "money"), col("b61_90", "61-90", "money"), col("b90_plus", "90+", "money")],
    },
    "supplier_statement": {
        "title": "Supplier Statement",
        "permission": ("supplier_reports", "suppliers"),
        "function": reports.supplier_statement,
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Ref No"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_supplier": True,
    },
    "sales_invoices": {
        "title": "Sales Invoice Report",
        "permission": ("sales_reports", "sales_invoices"),
        "function": reports.sales_invoice_report,
        "columns": [col("invoice_no", "Invoice No"), col("invoice_date", "Date"), col("invoice_type", "Type"), col("customer", "Customer"), col("po_number", "PO No"), col("grand_total", "Grand Total", "money"), col("received_amount", "Received", "money"), col("balance_amount", "Balance", "money"), col("status", "Status")],
    },
    "receipts": {
        "title": "Receipt Report",
        "permission": ("sales_reports", "customer_receipts"),
        "function": reports.receipt_report,
        "columns": [col("receipt_no", "Receipt No"), col("receipt_date", "Date"), col("customer", "Customer"), col("payment_mode", "Mode"), col("cash_bank", "Cash/Bank"), col("cheque_reference_no", "Reference"), col("amount", "Amount", "money"), col("adjusted_invoice", "Invoice")],
    },
    "purchase_report": {
        "title": "Purchase Report",
        "permission": ("purchase_reports", "supplier_purchases"),
        "function": reports.purchase_report,
        "columns": [col("purchase_no", "Purchase No"), col("purchase_date", "Date"), col("supplier", "Supplier"), col("supplier_bill_no", "Bill No"), col("grand_total", "Grand Total", "money"), col("paid_amount", "Paid", "money"), col("balance_amount", "Balance", "money"), col("status", "Status")],
    },
    "supplier_payments": {
        "title": "Supplier Payment Report",
        "permission": ("purchase_reports", "supplier_payments"),
        "function": reports.supplier_payment_report,
        "columns": [col("payment_no", "Payment No"), col("payment_date", "Date"), col("supplier", "Supplier"), col("payment_mode", "Mode"), col("cash_bank", "Cash/Bank"), col("cheque_reference_no", "Reference"), col("amount", "Amount", "money"), col("adjusted_purchase", "Purchase")],
    },
    "cash_book": {
        "title": "Cash Book",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": lambda company_id, branch_id, filters: reports.cash_bank_book(company_id, branch_id, filters, "cash"),
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("account", "Cash Account"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
    },
    "bank_book": {
        "title": "Bank Book",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": lambda company_id, branch_id, filters: reports.cash_bank_book(company_id, branch_id, filters, "bank"),
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("account", "Bank Account"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
    },
    "general_ledger": {
        "title": "General Ledger",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.general_ledger,
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("account", "Account"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
    },
    "trial_balance": {
        "title": "Trial Balance",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.trial_balance,
        "columns": [col("account_code", "Code"), col("account_name", "Account"), col("account_type", "Type"), col("balance_debit", "Debit", "money"), col("balance_credit", "Credit", "money")],
    },
    "profit_loss": {
        "title": "Profit and Loss",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.profit_loss,
        "columns": [col("section", "Section"), col("amount", "Amount", "money")],
    },
    "balance_sheet": {
        "title": "Balance Sheet",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.balance_sheet,
        "columns": [col("section", "Section"), col("amount", "Amount", "money")],
    },
}


PLACEHOLDER_REPORTS = {
    "customer_sales": ("Customer-wise Sales", "customer_reports", "sales_invoices"),
    "customer_receipts": ("Customer-wise Receipts", "customer_reports", "customer_receipts"),
    "supplier_purchases": ("Supplier-wise Purchases", "supplier_reports", "supplier_purchases"),
    "supplier_payments_summary": ("Supplier-wise Payments", "supplier_reports", "supplier_payments"),
    "sales_quotations": ("Quotation Report", "sales_reports", "quotations"),
    "sales_confirmations": ("Confirmation / PO Report", "sales_reports", "customer_confirmations"),
    "sales_challans": ("Delivery Challan Report", "sales_reports", "delivery_challans"),
    "sales_returns": ("Sales Return Report", "sales_reports", "sales_returns"),
    "sales_tax": ("Sales Tax Report", "sales_reports", "sales_invoices"),
    "purchase_returns": ("Purchase Return Report", "purchase_reports", "purchase_returns"),
    "purchase_tax": ("Purchase Tax Report", "purchase_reports", "supplier_purchases"),
    "profit_by_invoice": ("Profit by Invoice", "purchase_reports", "sales_invoices"),
    "profit_by_confirmation": ("Profit by Confirmation / PO", "purchase_reports", "customer_confirmations"),
    "service_contracts": ("Service Contract List", "service_reports", "service_contracts"),
    "service_expiring": ("Expiring Contracts", "service_reports", "service_contracts"),
    "service_billing_due": ("Billing Due Contracts", "service_reports", "service_contracts"),
    "service_invoice_history": ("Contract Invoice History", "service_reports", "service_contracts"),
    "journal_report": ("Journal Entries Report", "accounting_reports", "accounting_reports"),
}


@login_required_custom
def index(request):
    context = build_page_context("Reports", "Branch-aware reporting with print-friendly views and CSV export.")
    context["report_categories"] = [
        category for category in REPORT_CATEGORIES if has_report_permission(request, category[4])
    ]
    priority = [
        ("Customer Ledger", "bi-person-lines-fill", "reports:customer_ledger", ("customer_reports", "customers")),
        ("Customer Outstanding", "bi-currency-dollar", "reports:customer_outstanding", ("customer_reports", "sales_invoices")),
        ("Supplier Payable", "bi-truck", "reports:supplier_payable", ("supplier_reports", "supplier_purchases")),
        ("Sales Invoices", "bi-receipt", "reports:sales_invoices", ("sales_reports", "sales_invoices")),
        ("Purchases", "bi-bag-check", "reports:purchase_report", ("purchase_reports", "supplier_purchases")),
        ("Trial Balance", "bi-scale", "reports:trial_balance", ("accounting_reports", "accounting_reports")),
    ]
    context["priority_links"] = [item for item in priority if has_report_permission(request, item[3])]
    return render(request, "reports/index.html", context)


@login_required_custom
def generic_report(request, report_key):
    if report_key not in REPORTS:
        return placeholder_report(request, report_key)
    definition = REPORTS[report_key]
    if not has_report_permission(request, definition["permission"]):
        return render(request, "errors/403.html", status=403)

    company_id, branch_id, allowed_branches = reports.current_scope(request)
    filters = reports.report_filters(request, company_id, branch_id)
    data, summary = definition["function"](company_id, branch_id, filters)
    columns = definition["columns"]

    if definition.get("needs_customer") and not filters.get("customer_id"):
        messages.info(request, "Select a customer to view this report.")
    if definition.get("needs_supplier") and not filters.get("supplier_id"):
        messages.info(request, "Select a supplier to view this report.")

    if request.GET.get("export") == "csv":
        log_export_report(request, definition["title"], "CSV")
        return csv_response(f"{report_key}.csv", columns, data)

    context = build_page_context(definition["title"], "Filter, print, or export this report.")
    context.update(
        {
            "report_key": report_key,
            "report_title": definition["title"],
            "columns": columns,
            "rows": display_rows(columns, data),
            "raw_rows": data,
            "summary": summary,
            "filters": filters,
            "allowed_branches": allowed_branches,
            "print_mode": request.GET.get("print") == "1",
            **build_print_context(company_id),
        }
    )
    template = "reports/print_report.html" if context["print_mode"] else "reports/generic_table_report.html"
    if context["print_mode"]:
        log_export_report(request, definition["title"], "PRINT")
    return render(request, template, context)


@login_required_custom
def placeholder_report(request, report_key):
    title, permission_code, fallback_code = PLACEHOLDER_REPORTS.get(report_key, ("Report", "reports", "reports"))
    if not has_report_permission(request, (permission_code, fallback_code)):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id, allowed_branches = reports.current_scope(request)
    columns = [col("note", "Report")]
    data = [{"note": "This report is available as a route and will be expanded from the shared reporting framework."}]
    context = build_page_context(title, "Reserved report route.")
    context.update(
        {
            "report_key": report_key,
            "report_title": title,
            "columns": columns,
            "rows": display_rows(columns, data),
            "raw_rows": data,
            "summary": {"Status": "Placeholder"},
            "filters": reports.report_filters(request, company_id, branch_id),
            "allowed_branches": allowed_branches,
            "print_mode": request.GET.get("print") == "1",
            **build_print_context(company_id),
        }
    )
    if request.GET.get("export") == "csv":
        log_export_report(request, title, "CSV")
        return csv_response(f"{report_key}.csv", columns, data)
    template = "reports/print_report.html" if context["print_mode"] else "reports/generic_table_report.html"
    if context["print_mode"]:
        log_export_report(request, title, "PRINT")
    return render(request, template, context)


def has_report_permission(request, permissions):
    primary, fallback = permissions
    return user_has_permission(request, primary, "view") or user_has_permission(request, fallback, "view")


def display_rows(columns, data):
    display = []
    for row in data:
        display.append(
            {
                "cells": [
                    {
                        "value": row.get(column["key"], ""),
                        "kind": column.get("kind", "text"),
                    }
                    for column in columns
                ]
            }
        )
    return display
