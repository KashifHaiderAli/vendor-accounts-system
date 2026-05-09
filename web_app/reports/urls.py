from django.urls import path

from . import views


app_name = "reports"

urlpatterns = [
    path("", views.index, name="index"),
    path("customers/ledger/", views.generic_report, {"report_key": "customer_ledger"}, name="customer_ledger"),
    path("customers/outstanding/", views.generic_report, {"report_key": "customer_outstanding"}, name="customer_outstanding"),
    path("customers/aging/", views.generic_report, {"report_key": "customer_aging"}, name="customer_aging"),
    path("customers/statement/", views.generic_report, {"report_key": "customer_statement"}, name="customer_statement"),
    path("customers/sales/", views.placeholder_report, {"report_key": "customer_sales"}, name="customer_sales"),
    path("customers/receipts/", views.placeholder_report, {"report_key": "customer_receipts"}, name="customer_receipts"),
    path("suppliers/ledger/", views.generic_report, {"report_key": "supplier_ledger"}, name="supplier_ledger"),
    path("suppliers/payable/", views.generic_report, {"report_key": "supplier_payable"}, name="supplier_payable"),
    path("suppliers/aging/", views.generic_report, {"report_key": "supplier_aging"}, name="supplier_aging"),
    path("suppliers/statement/", views.generic_report, {"report_key": "supplier_statement"}, name="supplier_statement"),
    path("suppliers/purchases/", views.placeholder_report, {"report_key": "supplier_purchases"}, name="supplier_purchases"),
    path("suppliers/payments/", views.placeholder_report, {"report_key": "supplier_payments_summary"}, name="supplier_payments_summary"),
    path("sales/quotations/", views.placeholder_report, {"report_key": "sales_quotations"}, name="sales_quotations"),
    path("sales/confirmations/", views.placeholder_report, {"report_key": "sales_confirmations"}, name="sales_confirmations"),
    path("sales/delivery-challans/", views.placeholder_report, {"report_key": "sales_challans"}, name="sales_challans"),
    path("sales/invoices/", views.generic_report, {"report_key": "sales_invoices"}, name="sales_invoices"),
    path("sales/returns/", views.placeholder_report, {"report_key": "sales_returns"}, name="sales_returns"),
    path("sales/receipts/", views.generic_report, {"report_key": "receipts"}, name="receipts"),
    path("sales/tax/", views.placeholder_report, {"report_key": "sales_tax"}, name="sales_tax"),
    path("purchases/purchases/", views.generic_report, {"report_key": "purchase_report"}, name="purchase_report"),
    path("purchases/returns/", views.placeholder_report, {"report_key": "purchase_returns"}, name="purchase_returns"),
    path("purchases/payments/", views.generic_report, {"report_key": "supplier_payments"}, name="supplier_payments"),
    path("purchases/tax/", views.placeholder_report, {"report_key": "purchase_tax"}, name="purchase_tax"),
    path("purchases/profit-by-invoice/", views.placeholder_report, {"report_key": "profit_by_invoice"}, name="profit_by_invoice"),
    path("purchases/profit-by-confirmation/", views.placeholder_report, {"report_key": "profit_by_confirmation"}, name="profit_by_confirmation"),
    path("services/contracts/", views.placeholder_report, {"report_key": "service_contracts"}, name="service_contracts"),
    path("services/expiring/", views.placeholder_report, {"report_key": "service_expiring"}, name="service_expiring"),
    path("services/billing-due/", views.placeholder_report, {"report_key": "service_billing_due"}, name="service_billing_due"),
    path("services/invoice-history/", views.placeholder_report, {"report_key": "service_invoice_history"}, name="service_invoice_history"),
    path("accounting/cash-book/", views.generic_report, {"report_key": "cash_book"}, name="cash_book"),
    path("accounting/bank-book/", views.generic_report, {"report_key": "bank_book"}, name="bank_book"),
    path("accounting/general-ledger/", views.generic_report, {"report_key": "general_ledger"}, name="general_ledger"),
    path("accounting/trial-balance/", views.generic_report, {"report_key": "trial_balance"}, name="trial_balance"),
    path("accounting/profit-loss/", views.generic_report, {"report_key": "profit_loss"}, name="profit_loss"),
    path("accounting/balance-sheet/", views.generic_report, {"report_key": "balance_sheet"}, name="balance_sheet"),
    path("accounting/journals/", views.placeholder_report, {"report_key": "journal_report"}, name="journal_report"),
]
