from __future__ import annotations

from django.contrib import messages
from django.shortcuts import render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom
from core.print_utils import build_print_context
from core.audit_utils import log_export_report
from core.edition_utils import is_tax_enabled
from core.utils import build_page_context

from .export_utils import csv_response
from . import report_utils as reports


REPORT_CATEGORIES = [
    ("Customer Reports", "bi-people", "Customer ledgers, statements, outstanding, aging, sales, and receipts.", "reports:customer_reports", ("customer_reports", "customers")),
    ("Supplier Reports", "bi-truck", "Supplier ledgers, payable, aging, purchases, and payments.", "reports:supplier_reports", ("supplier_reports", "suppliers")),
    ("Sales Reports", "bi-receipt", "Quotations, confirmations, challans, invoices, returns, receipts, and tax.", "reports:sales_reports", ("sales_reports", "sales_invoices")),
    ("Purchase Reports", "bi-bag-check", "Purchases, purchase returns, supplier payments, tax, and profit views.", "reports:purchase_reports", ("purchase_reports", "supplier_purchases")),
    ("Item / Product Reports", "bi-box-seam", "Item sales, purchases, profit, transaction history, and service sales.", "reports:item_reports", ("sales_reports", "purchase_reports")),
    ("Service Reports", "bi-briefcase", "Contracts, expiring contracts, billing due, and invoice history.", "reports:service_reports", ("service_reports", "service_contracts")),
    ("Accounting Reports", "bi-journal-richtext", "Cash book, bank book, ledger, trial balance, profit and loss, and balance sheet.", "reports:accounting_reports", ("accounting_reports", "accounting_reports")),
    ("Tax Summary", "bi-percent", "Output tax, input tax, and net tax payable or receivable.", "reports:tax_reports", ("accounting_reports", "accounting_reports")),
    ("Inventory Reports", "bi-boxes", "Stock balance, item ledger, stock in/out, low stock, and valuation.", "reports:inventory_reports", ("sales_reports", "purchase_reports")),
    ("System / Audit Reports", "bi-shield-check", "Activity, login/logout, print, export, backup/restore, and validation logs.", "reports:system_reports", ("audit_log", "audit_log")),
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
        "missing_filter_message": "Please select a customer to view ledger.",
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
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Document No"), col("against_invoice", "Against Invoice"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_customer": True,
        "missing_filter_message": "Please select a customer to view statement.",
    },
    "supplier_ledger": {
        "title": "Supplier Ledger",
        "permission": ("supplier_reports", "suppliers"),
        "function": reports.supplier_ledger,
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("reference_type", "Reference"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_supplier": True,
        "missing_filter_message": "Please select a supplier to view ledger.",
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
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Document No"), col("against_purchase", "Against Purchase"), col("supplier_bill_no", "Supplier Bill No"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_supplier": True,
        "missing_filter_message": "Please select a supplier to view statement.",
    },
    "customer_sales": {
        "title": "Customer-wise Sales",
        "permission": ("customer_reports", "sales_invoices"),
        "function": reports.customer_sales_summary,
        "columns": [col("customer", "Customer"), col("invoice_count", "Invoice Count", "money"), col("sales_total", "Sales Total", "money"), col("tax_total", "Tax Total", "money"), col("received", "Received", "money"), col("balance", "Balance", "money")],
    },
    "customer_receipts": {
        "title": "Customer-wise Receipts",
        "permission": ("customer_reports", "customer_receipts"),
        "function": reports.customer_receipts_summary,
        "columns": [col("customer", "Customer"), col("receipt_count", "Receipt Count", "money"), col("total_received", "Total Received", "money")],
    },
    "supplier_purchases": {
        "title": "Supplier-wise Purchase",
        "permission": ("supplier_reports", "supplier_purchases"),
        "function": reports.supplier_purchase_summary,
        "columns": [col("supplier", "Supplier"), col("purchase_count", "Purchase Count", "money"), col("purchase_total", "Purchase Total", "money"), col("tax_total", "Tax Total", "money"), col("paid", "Paid", "money"), col("balance", "Balance", "money")],
    },
    "supplier_payments_summary": {
        "title": "Supplier-wise Payment",
        "permission": ("supplier_reports", "supplier_payments"),
        "function": reports.supplier_payment_summary,
        "columns": [col("supplier", "Supplier"), col("payment_count", "Payment Count", "money"), col("total_paid", "Total Paid", "money")],
    },
    "sales_quotations": {
        "title": "Quotation Report",
        "permission": ("sales_reports", "quotations"),
        "function": reports.quotation_report,
        "columns": [col("quotation_no", "Quotation No"), col("date", "Date"), col("customer_party", "Customer / Party"), col("subject", "Subject"), col("valid_till", "Valid Till"), col("grand_total", "Grand Total", "money"), col("status", "Status")],
    },
    "sales_confirmations": {
        "title": "Confirmation / PO Report",
        "permission": ("sales_reports", "customer_confirmations"),
        "function": reports.confirmation_report,
        "columns": [col("confirmation_no", "Confirmation No"), col("date", "Date"), col("customer_party", "Customer / Party"), col("type", "Type"), col("po_number", "PO No"), col("total", "Total", "money"), col("status", "Status")],
    },
    "sales_challans": {
        "title": "Delivery Challan Report",
        "permission": ("sales_reports", "delivery_challans"),
        "function": reports.delivery_challan_report,
        "columns": [col("dc_no", "DC No"), col("date", "Date"), col("customer_party", "Customer / Party"), col("po_number", "PO No"), col("delivered_by", "Delivered By"), col("received_by", "Received By"), col("signed_copy", "Signed Copy"), col("status", "Status")],
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
    "sales_returns": {
        "title": "Sales Return Report",
        "permission": ("sales_reports", "sales_returns"),
        "function": reports.sales_return_report,
        "columns": [col("return_no", "Return No"), col("date", "Date"), col("customer", "Customer"), col("invoice_no", "Invoice No"), col("grand_total", "Grand Total", "money"), col("refund_amount", "Refund Amount", "money"), col("status", "Status")],
    },
    "sales_tax": {
        "title": "Sales Tax Report",
        "permission": ("sales_reports", "sales_invoices"),
        "function": reports.sales_tax_report,
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Ref No"), col("customer", "Customer"), col("taxable_amount", "Taxable Amount", "money"), col("output_tax", "Output Tax", "money"), col("status", "Status")],
    },
    "purchase_returns": {
        "title": "Purchase Return Report",
        "permission": ("purchase_reports", "purchase_returns"),
        "function": reports.purchase_return_report,
        "columns": [col("return_no", "Return No"), col("date", "Date"), col("supplier", "Supplier"), col("purchase_no", "Purchase No"), col("supplier_bill_no", "Supplier Bill No"), col("grand_total", "Grand Total", "money"), col("refund_amount", "Refund Amount", "money"), col("status", "Status")],
    },
    "supplier_payments": {
        "title": "Supplier Payment Report",
        "permission": ("purchase_reports", "supplier_payments"),
        "function": reports.supplier_payment_report,
        "columns": [col("payment_no", "Payment No"), col("payment_date", "Date"), col("supplier", "Supplier"), col("payment_mode", "Mode"), col("cash_bank", "Cash/Bank"), col("cheque_reference_no", "Reference"), col("amount", "Amount", "money"), col("adjusted_purchase", "Purchase")],
    },
    "purchase_tax": {
        "title": "Purchase Tax Report",
        "permission": ("purchase_reports", "supplier_purchases"),
        "function": reports.purchase_tax_report,
        "columns": [col("date", "Date"), col("type", "Type"), col("ref_no", "Ref No"), col("supplier", "Supplier"), col("taxable_amount", "Taxable Amount", "money"), col("input_tax", "Input Tax", "money"), col("status", "Status")],
    },
    "profit_by_invoice": {
        "title": "Profit by Invoice",
        "permission": ("purchase_reports", "sales_invoices"),
        "function": reports.profit_by_invoice_report,
        "columns": [col("invoice_no", "Invoice No"), col("date", "Date"), col("customer", "Customer"), col("sales_total", "Sales Total", "money"), col("purchase_cost", "Purchase Cost", "money"), col("gross_profit", "Gross Profit", "money"), col("profit_percent", "Profit %", "money")],
    },
    "profit_by_confirmation": {
        "title": "Profit by Confirmation / PO",
        "permission": ("purchase_reports", "customer_confirmations"),
        "function": reports.profit_by_confirmation_report,
        "columns": [col("confirmation_no", "Confirmation No"), col("customer_party", "Customer / Party"), col("po_number", "PO No"), col("sales_total", "Sales Total", "money"), col("purchase_cost", "Purchase Cost", "money"), col("gross_profit", "Gross Profit", "money"), col("profit_percent", "Profit %", "money")],
    },
    "item_sales": {
        "title": "Item-wise Sales Report",
        "permission": ("sales_reports", "sales_invoices"),
        "function": reports.item_sales_report,
        "columns": [col("item_code", "Item Code"), col("item_name", "Item / Service"), col("item_type", "Type"), col("qty_sold", "Qty Sold", "money"), col("gross_amount", "Gross", "money"), col("discount", "Discount", "money"), col("tax", "Tax", "money"), col("net_total", "Net Total", "money")],
    },
    "item_purchases": {
        "title": "Item-wise Purchase Report",
        "permission": ("purchase_reports", "supplier_purchases"),
        "function": reports.item_purchase_report,
        "columns": [col("item_code", "Item Code"), col("item_name", "Item / Service"), col("item_type", "Type"), col("qty_purchased", "Qty Purchased", "money"), col("purchase_amount", "Purchase Amount", "money"), col("tax", "Tax", "money"), col("net_total", "Net Total", "money")],
    },
    "item_profit": {
        "title": "Item-wise Profit Report",
        "permission": ("sales_reports", "purchase_reports"),
        "function": reports.item_profit_report,
        "columns": [col("item", "Item"), col("qty_sold", "Qty Sold", "money"), col("sales_amount", "Sales Amount", "money"), col("purchase_cost", "Purchase Cost", "money"), col("gross_profit", "Gross Profit", "money"), col("profit_percent", "Profit %", "money"), col("cost_note", "Cost Note")],
    },
    "item_history": {
        "title": "Item Transaction History",
        "permission": ("sales_reports", "purchase_reports"),
        "function": reports.item_history_report,
        "columns": [col("date", "Date"), col("type", "Type"), col("document_no", "Document No"), col("party", "Party"), col("qty_in", "Qty In", "money"), col("qty_out", "Qty Out", "money"), col("rate", "Rate", "money"), col("amount", "Amount", "money")],
        "needs_item": True,
        "missing_filter_message": "Please select an item to view transaction history.",
    },
    "service_sales": {
        "title": "Service-wise Sales Report",
        "permission": ("sales_reports", "sales_invoices"),
        "function": reports.service_sales_report,
        "columns": [col("service", "Service"), col("qty_count", "Qty / Count", "money"), col("sales_amount", "Sales Amount", "money"), col("tax", "Tax", "money"), col("net_total", "Net Total", "money")],
    },
    "service_contracts": {
        "title": "Service Contract List",
        "permission": ("service_reports", "service_contracts"),
        "function": reports.service_contract_report,
        "columns": [col("contract_no", "Contract No"), col("customer", "Customer"), col("service_type", "Service Type"), col("start", "Start"), col("end", "End"), col("cycle", "Cycle"), col("amount", "Amount", "money"), col("next_billing", "Next Billing"), col("status", "Status")],
    },
    "service_expiring": {
        "title": "Expiring Contracts",
        "permission": ("service_reports", "service_contracts"),
        "function": reports.service_expiring_report,
        "columns": [col("contract_no", "Contract No"), col("customer", "Customer"), col("service_type", "Service Type"), col("start", "Start"), col("end", "End"), col("cycle", "Cycle"), col("amount", "Amount", "money"), col("next_billing", "Next Billing"), col("status", "Status")],
    },
    "service_billing_due": {
        "title": "Billing Due Contracts",
        "permission": ("service_reports", "service_contracts"),
        "function": reports.service_billing_due_report,
        "columns": [col("contract_no", "Contract No"), col("customer", "Customer"), col("service_type", "Service Type"), col("start", "Start"), col("end", "End"), col("cycle", "Cycle"), col("amount", "Amount", "money"), col("next_billing", "Next Billing"), col("status", "Status")],
    },
    "service_invoice_history": {
        "title": "Contract Invoice History",
        "permission": ("service_reports", "service_contracts"),
        "function": reports.service_invoice_history_report,
        "columns": [col("contract_no", "Contract No"), col("customer", "Customer"), col("invoice_no", "Invoice No"), col("invoice_date", "Invoice Date"), col("amount", "Amount", "money"), col("status", "Status")],
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
    "journal_report": {
        "title": "Journal Entries Report",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.journal_report,
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("reference_type", "Reference Type"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money")],
    },
    "expense_report": {
        "title": "Expense Report",
        "permission": ("accounting_reports", "expense_heads"),
        "function": reports.expense_report,
        "columns": [col("voucher_no", "Voucher No"), col("voucher_date", "Date"), col("expense_head", "Expense Head"), col("cash_bank", "Cash/Bank"), col("payment_mode", "Mode"), col("amount", "Amount", "money"), col("tax", "Tax", "money"), col("total", "Total", "money"), col("status", "Status"), col("remarks", "Remarks")],
    },
    "income_report": {
        "title": "Income Report",
        "permission": ("accounting_reports", "sales_invoices"),
        "function": reports.income_report,
        "columns": [col("invoice_no", "Invoice No"), col("invoice_date", "Date"), col("customer", "Customer"), col("invoice_type", "Type"), col("subtotal", "Subtotal", "money"), col("discount_total", "Discount", "money"), col("tax_total", "Tax", "money"), col("grand_total", "Grand Total", "money"), col("status", "Status")],
    },
    "tax_summary": {
        "title": "Tax Summary Report",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.tax_summary_report,
        "columns": [col("section", "Tax Section"), col("amount", "Amount", "money")],
    },
    "account_ledger": {
        "title": "Account Ledger",
        "permission": ("accounting_reports", "accounting_reports"),
        "function": reports.account_ledger_report,
        "columns": [col("date", "Date"), col("entry_no", "Entry No"), col("account", "Account"), col("description", "Description"), col("debit", "Debit", "money"), col("credit", "Credit", "money"), col("balance", "Balance", "money")],
        "needs_account": True,
        "missing_filter_message": "Please select an account to view ledger.",
    },
    "inventory_stock_balance": {
        "title": "Stock Balance",
        "permission": ("sales_reports", "purchase_reports"),
        "function": reports.inventory_stock_balance_report,
        "columns": [col("item_code", "Item Code"), col("item_name", "Item Name"), col("unit", "Unit"), col("qty_in", "Qty In", "money"), col("qty_out", "Qty Out", "money"), col("available_qty", "Available Qty", "money"), col("average_cost", "Average Cost", "money"), col("stock_value", "Stock Value", "money"), col("minimum_level", "Minimum Level", "money"), col("status", "Status")],
    },
    "inventory_item_ledger": {
        "title": "Item Ledger",
        "permission": ("sales_reports", "purchase_reports"),
        "function": reports.inventory_item_ledger_report,
        "columns": [col("date", "Date"), col("type", "Type"), col("source_no", "Source No"), col("party", "Party"), col("qty_in", "Qty In", "money"), col("qty_out", "Qty Out", "money"), col("balance", "Balance", "money"), col("unit_cost", "Unit Cost", "money"), col("remarks", "Remarks")],
    },
    "inventory_stock_in": {
        "title": "Stock In",
        "permission": ("sales_reports", "purchase_reports"),
        "function": lambda company_id, branch_id, filters: reports.inventory_stock_flow_report(company_id, branch_id, filters, "in"),
        "columns": [col("date", "Date"), col("type", "Type"), col("source_no", "Source No"), col("item_code", "Item Code"), col("item_name", "Item Name"), col("qty_in", "Qty In", "money"), col("unit_cost", "Unit Cost", "money"), col("remarks", "Remarks")],
    },
    "inventory_stock_out": {
        "title": "Stock Out",
        "permission": ("sales_reports", "purchase_reports"),
        "function": lambda company_id, branch_id, filters: reports.inventory_stock_flow_report(company_id, branch_id, filters, "out"),
        "columns": [col("date", "Date"), col("type", "Type"), col("source_no", "Source No"), col("item_code", "Item Code"), col("item_name", "Item Name"), col("qty_out", "Qty Out", "money"), col("unit_cost", "Unit Cost", "money"), col("remarks", "Remarks")],
    },
    "inventory_low_stock": {
        "title": "Low Stock",
        "permission": ("sales_reports", "purchase_reports"),
        "function": lambda company_id, branch_id, filters: reports.inventory_stock_balance_report(company_id, branch_id, {**filters, "status": "low"}),
        "columns": [col("item_code", "Item Code"), col("item_name", "Item Name"), col("unit", "Unit"), col("available_qty", "Available Qty", "money"), col("minimum_level", "Minimum Level", "money"), col("stock_value", "Stock Value", "money"), col("status", "Status")],
    },
    "inventory_valuation": {
        "title": "Stock Valuation",
        "permission": ("sales_reports", "purchase_reports"),
        "function": reports.inventory_stock_balance_report,
        "columns": [col("item_code", "Item Code"), col("item_name", "Item Name"), col("available_qty", "Available Qty", "money"), col("average_cost", "Average Cost", "money"), col("stock_value", "Stock Value", "money"), col("status", "Status")],
    },
    "system_activity": {
        "title": "User Activity Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.user_activity_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("action", "Action"), col("module", "Module"), col("record_type", "Record Type"), col("record_id", "Record ID"), col("description", "Description"), col("ip", "IP")],
    },
    "system_login_logout": {
        "title": "Login / Logout Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.login_logout_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("action", "Action"), col("ip", "IP"), col("description", "User Agent / Details")],
    },
    "system_prints": {
        "title": "Document Print Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.print_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("module", "Module"), col("record_type", "Document Type"), col("record_id", "Document ID"), col("description", "Description")],
    },
    "system_exports": {
        "title": "Report Export Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.export_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("module", "Report Name"), col("action", "Format"), col("description", "Description")],
    },
    "system_backup_restore": {
        "title": "Backup / Restore Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.backup_restore_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("action", "Action"), col("module", "Module"), col("description", "File / Path / Status")],
    },
    "system_validation_failures": {
        "title": "Validation Failure Report",
        "permission": ("audit_log", "audit_log"),
        "function": reports.validation_failure_report,
        "columns": [col("datetime", "Date/Time"), col("user", "User"), col("action", "Action"), col("module", "Module"), col("record_type", "Record Type"), col("record_id", "Record ID"), col("description", "Description"), col("ip", "IP")],
    },
}

REPORT_FILTERS = {
    "customer_ledger": ["branch", "customer", "date_from", "date_to"],
    "customer_statement": ["branch", "customer", "date_from", "date_to"],
    "customer_outstanding": ["branch", "customer", "date_to", "status"],
    "customer_aging": ["branch", "customer", "as_of_date"],
    "customer_sales": ["branch", "customer", "date_from", "date_to", "status"],
    "customer_receipts": ["branch", "customer", "date_from", "date_to", "payment_mode"],
    "supplier_ledger": ["branch", "supplier", "date_from", "date_to"],
    "supplier_statement": ["branch", "supplier", "date_from", "date_to"],
    "supplier_payable": ["branch", "supplier", "date_to", "status"],
    "supplier_aging": ["branch", "supplier", "as_of_date"],
    "supplier_purchases": ["branch", "supplier", "date_from", "date_to", "status"],
    "supplier_payments_summary": ["branch", "supplier", "date_from", "date_to", "payment_mode"],
    "sales_quotations": ["branch", "customer", "date_from", "date_to", "status"],
    "sales_confirmations": ["branch", "customer", "date_from", "date_to", "confirmation_type", "status"],
    "sales_challans": ["branch", "customer", "date_from", "date_to", "status"],
    "sales_invoices": ["branch", "customer", "date_from", "date_to", "invoice_type", "status"],
    "receipts": ["branch", "customer", "date_from", "date_to", "payment_mode"],
    "sales_returns": ["branch", "customer", "date_from", "date_to", "status"],
    "sales_tax": ["branch", "date_from", "date_to"],
    "purchase_report": ["branch", "supplier", "date_from", "date_to", "status"],
    "purchase_returns": ["branch", "supplier", "date_from", "date_to", "status"],
    "supplier_payments": ["branch", "supplier", "date_from", "date_to", "payment_mode"],
    "purchase_tax": ["branch", "date_from", "date_to"],
    "profit_by_invoice": ["branch", "customer", "date_from", "date_to"],
    "profit_by_confirmation": ["branch", "customer", "date_from", "date_to"],
    "item_sales": ["branch", "item", "customer", "date_from", "date_to"],
    "item_purchases": ["branch", "item", "supplier", "date_from", "date_to"],
    "item_profit": ["branch", "item", "date_from", "date_to"],
    "item_history": ["branch", "item", "date_from", "date_to"],
    "service_sales": ["branch", "item", "date_from", "date_to"],
    "service_contracts": ["branch", "customer", "status"],
    "service_expiring": ["branch", "customer", "date_from", "date_to"],
    "service_billing_due": ["branch", "customer", "date_to"],
    "service_invoice_history": ["branch", "customer", "date_from", "date_to"],
    "cash_book": ["branch", "cash_bank", "date_from", "date_to"],
    "bank_book": ["branch", "cash_bank", "date_from", "date_to"],
    "general_ledger": ["branch", "account", "date_from", "date_to"],
    "account_ledger": ["branch", "account", "date_from", "date_to"],
    "trial_balance": ["branch", "date_from", "date_to"],
    "profit_loss": ["branch", "date_from", "date_to"],
    "balance_sheet": ["branch", "as_of_date"],
    "journal_report": ["branch", "date_from", "date_to", "reference_type"],
    "expense_report": ["branch", "expense_head", "cash_bank", "date_from", "date_to", "payment_mode", "status"],
    "income_report": ["branch", "customer", "date_from", "date_to", "invoice_type", "status"],
    "tax_summary": ["branch", "date_from", "date_to"],
    "inventory_stock_balance": ["branch", "item", "as_of_date"],
    "inventory_item_ledger": ["branch", "item", "date_from", "date_to"],
    "inventory_stock_in": ["branch", "item", "date_from", "date_to"],
    "inventory_stock_out": ["branch", "item", "date_from", "date_to"],
    "inventory_low_stock": ["branch", "item", "as_of_date"],
    "inventory_valuation": ["branch", "item", "as_of_date"],
    "system_activity": ["branch", "user", "date_from", "date_to", "action", "module"],
    "system_login_logout": ["branch", "user", "date_from", "date_to"],
    "system_prints": ["branch", "user", "date_from", "date_to", "module"],
    "system_exports": ["branch", "user", "date_from", "date_to", "module"],
    "system_backup_restore": ["branch", "user", "date_from", "date_to", "action"],
    "system_validation_failures": ["branch", "user", "date_from", "date_to", "module"],
}

for key, filter_names in REPORT_FILTERS.items():
    if key in REPORTS:
        REPORTS[key]["filters"] = filter_names


REPORT_GROUPS = {
    "customers": {
        "title": "Customer Reports",
        "description": "Customer ledgers, business statements, outstanding invoices, aging, sales, and receipts.",
        "links": [
            ("Customer Ledger", "bi-person-lines-fill", "reports:customer_ledger", ("customer_reports", "customers")),
            ("Customer Statement", "bi-file-earmark-text", "reports:customer_statement", ("customer_reports", "customers")),
            ("Customer Outstanding", "bi-currency-dollar", "reports:customer_outstanding", ("customer_reports", "sales_invoices")),
            ("Customer Aging", "bi-hourglass-split", "reports:customer_aging", ("customer_reports", "sales_invoices")),
            ("Customer-wise Sales", "bi-graph-up", "reports:customer_sales", ("customer_reports", "sales_invoices")),
            ("Customer-wise Receipts", "bi-cash-coin", "reports:customer_receipts", ("customer_reports", "customer_receipts")),
        ],
    },
    "suppliers": {
        "title": "Supplier Reports",
        "description": "Supplier ledgers, statements, payable, aging, purchases, and payments.",
        "links": [
            ("Supplier Ledger", "bi-truck", "reports:supplier_ledger", ("supplier_reports", "suppliers")),
            ("Supplier Statement", "bi-file-earmark-text", "reports:supplier_statement", ("supplier_reports", "suppliers")),
            ("Supplier Payable", "bi-wallet2", "reports:supplier_payable", ("supplier_reports", "supplier_purchases")),
            ("Supplier Aging", "bi-hourglass-split", "reports:supplier_aging", ("supplier_reports", "supplier_purchases")),
            ("Supplier-wise Purchase", "bi-bag-check", "reports:supplier_purchases", ("supplier_reports", "supplier_purchases")),
            ("Supplier-wise Payment", "bi-cash-stack", "reports:supplier_payments_summary", ("supplier_reports", "supplier_payments")),
        ],
    },
    "sales": {
        "title": "Sales Reports",
        "description": "Quotations, confirmations, delivery challans, invoices, returns, receipts, and sales tax.",
        "links": [
            ("Quotation Report", "bi-file-earmark-text", "reports:sales_quotations", ("sales_reports", "quotations")),
            ("Confirmation / PO Report", "bi-check2-square", "reports:sales_confirmations", ("sales_reports", "customer_confirmations")),
            ("Delivery Challan Report", "bi-truck", "reports:sales_challans", ("sales_reports", "delivery_challans")),
            ("Sales Invoice Report", "bi-receipt", "reports:sales_invoices", ("sales_reports", "sales_invoices")),
            ("Sales Return Report", "bi-arrow-counterclockwise", "reports:sales_returns", ("sales_reports", "sales_returns")),
            ("Receipt Report", "bi-cash-coin", "reports:receipts", ("sales_reports", "customer_receipts")),
            ("Sales Tax Report", "bi-percent", "reports:sales_tax", ("sales_reports", "sales_invoices")),
        ],
    },
    "purchases": {
        "title": "Purchase Reports",
        "description": "Purchases, returns, supplier payments, input tax, and profit reports.",
        "links": [
            ("Purchase Report", "bi-bag-check", "reports:purchase_report", ("purchase_reports", "supplier_purchases")),
            ("Purchase Return Report", "bi-arrow-counterclockwise", "reports:purchase_returns", ("purchase_reports", "purchase_returns")),
            ("Supplier Payment Report", "bi-cash-stack", "reports:supplier_payments", ("purchase_reports", "supplier_payments")),
            ("Purchase Tax Report", "bi-percent", "reports:purchase_tax", ("purchase_reports", "supplier_purchases")),
            ("Profit by Invoice", "bi-graph-up-arrow", "reports:profit_by_invoice", ("purchase_reports", "sales_invoices")),
            ("Profit by Confirmation / PO", "bi-clipboard-data", "reports:profit_by_confirmation", ("purchase_reports", "customer_confirmations")),
        ],
    },
    "items": {
        "title": "Item / Product Reports",
        "description": "Transaction, sales, purchase, and profit reports. Inventory stock ledger lives under Inventory Reports.",
        "links": [
            ("Item-wise Sales", "bi-receipt", "reports:item_sales", ("sales_reports", "sales_invoices")),
            ("Item-wise Purchases", "bi-bag-check", "reports:item_purchases", ("purchase_reports", "supplier_purchases")),
            ("Item-wise Profit", "bi-graph-up-arrow", "reports:item_profit", ("sales_reports", "purchase_reports")),
            ("Item Transaction History", "bi-clock-history", "reports:item_history", ("sales_reports", "purchase_reports")),
            ("Service-wise Sales", "bi-tools", "reports:service_sales", ("sales_reports", "sales_invoices")),
        ],
    },
    "services": {
        "title": "Service Reports",
        "description": "Service contract lists, expiring contracts, billing due, and invoice history.",
        "links": [
            ("Service Contract List", "bi-briefcase", "reports:service_contracts", ("service_reports", "service_contracts")),
            ("Expiring Contracts", "bi-calendar-x", "reports:service_expiring", ("service_reports", "service_contracts")),
            ("Billing Due Contracts", "bi-calendar-check", "reports:service_billing_due", ("service_reports", "service_contracts")),
            ("Contract Invoice History", "bi-receipt", "reports:service_invoice_history", ("service_reports", "service_contracts")),
        ],
    },
    "accounting": {
        "title": "Accounting Reports",
        "description": "Cash book, bank book, ledgers, trial balance, profit/loss, balance sheet, journals, expenses, and income.",
        "links": [
            ("Cash Book", "bi-cash", "reports:cash_book", ("accounting_reports", "accounting_reports")),
            ("Bank Book", "bi-bank", "reports:bank_book", ("accounting_reports", "accounting_reports")),
            ("General Ledger", "bi-journal-text", "reports:general_ledger", ("accounting_reports", "accounting_reports")),
            ("Account Ledger", "bi-list-columns", "reports:account_ledger", ("accounting_reports", "accounting_reports")),
            ("Trial Balance", "bi-scale", "reports:trial_balance", ("accounting_reports", "accounting_reports")),
            ("Profit and Loss", "bi-graph-up", "reports:profit_loss", ("accounting_reports", "accounting_reports")),
            ("Balance Sheet", "bi-columns-gap", "reports:balance_sheet", ("accounting_reports", "accounting_reports")),
            ("Journal Entries", "bi-journal-richtext", "reports:journal_report", ("accounting_reports", "accounting_reports")),
            ("Expense Report", "bi-wallet2", "reports:expense_report", ("accounting_reports", "expense_heads")),
            ("Income Report", "bi-currency-dollar", "reports:income_report", ("accounting_reports", "sales_invoices")),
        ],
    },
    "tax": {
        "title": "Tax Summary",
        "description": "Output tax, input tax, expense tax, and net payable or receivable.",
        "links": [
            ("Tax Summary", "bi-percent", "reports:tax_summary", ("accounting_reports", "accounting_reports")),
        ],
    },
    "inventory": {
        "title": "Inventory Reports",
        "description": "Quantity-only stock balance, item ledger, stock in/out, low stock, and valuation.",
        "links": [
            ("Stock Balance", "bi-boxes", "reports:inventory_stock_balance", ("sales_reports", "purchase_reports")),
            ("Item Ledger", "bi-card-list", "reports:inventory_item_ledger", ("sales_reports", "purchase_reports")),
            ("Stock In", "bi-box-arrow-in-down", "reports:inventory_stock_in", ("sales_reports", "purchase_reports")),
            ("Stock Out", "bi-box-arrow-up", "reports:inventory_stock_out", ("sales_reports", "purchase_reports")),
            ("Low Stock", "bi-exclamation-triangle", "reports:inventory_low_stock", ("sales_reports", "purchase_reports")),
            ("Valuation", "bi-calculator", "reports:inventory_valuation", ("sales_reports", "purchase_reports")),
        ],
    },
    "system": {
        "title": "System / Audit Reports",
        "description": "Read-only audit reports for activity, login/logout, document prints, exports, backup/restore, and validation failures.",
        "links": [
            ("User Activity", "bi-activity", "reports:system_activity", ("audit_log", "audit_log")),
            ("Login / Logout", "bi-box-arrow-in-right", "reports:system_login_logout", ("audit_log", "audit_log")),
            ("Document Prints", "bi-printer", "reports:system_prints", ("audit_log", "audit_log")),
            ("Report Exports", "bi-file-earmark-arrow-down", "reports:system_exports", ("audit_log", "audit_log")),
            ("Backup / Restore", "bi-database-check", "reports:system_backup_restore", ("audit_log", "audit_log")),
            ("Validation Failures", "bi-exclamation-triangle", "reports:system_validation_failures", ("audit_log", "audit_log")),
        ],
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
    tax_enabled = is_tax_enabled(request=request, company_id=request.session.get("company_id"))
    context["report_categories"] = [row for row in REPORT_CATEGORIES if tax_enabled or row[3] != "reports:tax_reports"]
    context["priority_links"] = []
    return render(request, "reports/index.html", context)


@login_required_custom
def report_group(request, group_key):
    if group_key == "tax" and not is_tax_enabled(request=request, company_id=request.session.get("company_id")):
        return render(request, "reports/group_menu.html", {"group": {"title": "Summary", "description": "This report is disabled in this edition."}, "links": []})
    group = REPORT_GROUPS.get(group_key)
    if not group:
        return render(request, "errors/404.html", status=404)
    context = build_page_context(group["title"], group["description"])
    context["group"] = group
    tax_enabled = is_tax_enabled(request=request, company_id=request.session.get("company_id"))
    context["links"] = [
        row for row in group["links"]
        if tax_enabled or row[2] not in {"reports:sales_tax", "reports:purchase_tax", "reports:tax_summary"}
    ]
    return render(request, "reports/group_menu.html", context)


@login_required_custom
def generic_report(request, report_key):
    if report_key in {"sales_tax", "purchase_tax", "tax_summary"} and not is_tax_enabled(request=request, company_id=request.session.get("company_id")):
        return render(request, "reports/generic_table_report.html", {"report_title": "Summary", "columns": [], "rows": [], "summary": {}, "filters": {}, "filter_options": {}, "active_filters": [], "empty_message": "This report is disabled in this edition."})
    if report_key not in REPORTS:
        return placeholder_report(request, report_key)
    definition = REPORTS[report_key]
    if not has_report_permission(request, definition["permission"]):
        return render(request, "errors/403.html", status=403)

    company_id, branch_id, allowed_branches = reports.current_scope(request)
    filters = reports.report_filters(request, company_id, branch_id)
    data, summary = definition["function"](company_id, branch_id, filters)
    columns = definition["columns"]
    tax_enabled = is_tax_enabled(request=request, company_id=company_id)
    if not tax_enabled:
        columns = [
            column for column in columns
            if "tax" not in str(column.get("key", "")).lower()
            and "tax" not in str(column.get("label", "")).lower()
        ]
        summary = {key: value for key, value in summary.items() if "tax" not in str(key).lower()}

    missing_filter_message = None
    if definition.get("needs_customer") and not filters.get("customer_id"):
        missing_filter_message = definition.get("missing_filter_message") or "Please select a customer to view this report."
    if definition.get("needs_supplier") and not filters.get("supplier_id"):
        missing_filter_message = definition.get("missing_filter_message") or "Please select a supplier to view this report."
    if definition.get("needs_item") and not filters.get("item_service_id"):
        missing_filter_message = definition.get("missing_filter_message") or "Please select an item to view this report."
    if definition.get("needs_account") and not filters.get("account_id"):
        missing_filter_message = definition.get("missing_filter_message") or "Please select an account to view this report."
    if missing_filter_message:
        messages.info(request, missing_filter_message)

    if request.GET.get("export") == "csv":
        log_export_report(request, definition["title"], "CSV")
        return csv_response(f"{report_key}.csv", columns, data)

    context = build_page_context(definition["title"], "Filter, print, or export this report.")
    print_context = build_print_context(company_id, request, definition["title"])
    context.update(
        {
            **print_context,
            "report_key": report_key,
            "report_title": definition["title"],
            "columns": columns,
            "rows": display_rows(columns, data),
            "raw_rows": data,
            "summary": summary,
            "print_detail": report_print_detail(definition["title"], filters, allowed_branches, summary),
            "filters": filters,
            "active_filters": definition.get("filters", ["branch", "date_from", "date_to"]),
            "allowed_branches": allowed_branches,
            "print_mode": request.GET.get("print") == "1",
            "missing_filter_message": missing_filter_message,
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
    print_context = build_print_context(company_id, request, title)
    context.update(
        {
            **print_context,
            "report_key": report_key,
            "report_title": title,
            "columns": columns,
            "rows": display_rows(columns, data),
            "raw_rows": data,
            "summary": {"Status": "Placeholder"},
            "print_detail": report_print_detail(title, reports.report_filters(request, company_id, branch_id), allowed_branches, {"Status": "Placeholder"}),
            "filters": reports.report_filters(request, company_id, branch_id),
            "allowed_branches": allowed_branches,
            "print_mode": request.GET.get("print") == "1",
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
    if primary == "audit_log":
        role_name = str(request.session.get("role_name") or "").lower()
        return int(request.session.get("is_master_user") or 0) == 1 or "admin" in role_name or user_has_permission(request, "audit_log", "view")
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


def report_print_detail(title, filters, allowed_branches, summary):
    branch_name = selected_lookup_name(allowed_branches, filters.get("branch_id")) or "Current Branch"
    party = selected_lookup_name(filters.get("customers") or [], filters.get("customer_id"))
    if not party:
        party = selected_lookup_name(filters.get("suppliers") or [], filters.get("supplier_id"))
    period = " to ".join([value for value in [filters.get("date_from"), filters.get("date_to")] if value]) or "All Dates"
    return {
        "party": party,
        "period": period,
        "branch": branch_name,
        "opening_balance": summary.get("Opening Balance", ""),
        "closing_balance": summary.get("Closing Balance", ""),
        "title": title,
    }


def selected_lookup_name(rows, selected_id):
    if not selected_id:
        return ""
    selected = str(selected_id)
    for row in rows:
        if str(row.get("id")) == selected:
            return row.get("name") or row.get("branch_name") or ""
    return ""
