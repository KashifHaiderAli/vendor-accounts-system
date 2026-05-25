from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import resolve, reverse

from authentication.auth_utils import dictfetchone


class Command(BaseCommand):
    help = "Smoke-check report submenu routes, key CSV exports, and print-friendly report pages."

    GROUP_ROUTE_NAMES = [
        "reports:index",
        "reports:customer_reports",
        "reports:supplier_reports",
        "reports:sales_reports",
        "reports:purchase_reports",
        "reports:item_reports",
        "reports:service_reports",
        "reports:accounting_reports",
        "reports:tax_reports",
        "reports:inventory_reports",
        "reports:system_reports",
    ]

    REPORT_ROUTE_NAMES = [
        "reports:customer_ledger",
        "reports:customer_statement",
        "reports:customer_outstanding",
        "reports:customer_aging",
        "reports:customer_sales",
        "reports:customer_receipts",
        "reports:supplier_ledger",
        "reports:supplier_statement",
        "reports:supplier_payable",
        "reports:supplier_aging",
        "reports:supplier_purchases",
        "reports:supplier_payments_summary",
        "reports:sales_quotations",
        "reports:sales_confirmations",
        "reports:sales_challans",
        "reports:sales_invoices",
        "reports:sales_returns",
        "reports:receipts",
        "reports:sales_tax",
        "reports:purchase_report",
        "reports:purchase_returns",
        "reports:supplier_payments",
        "reports:purchase_tax",
        "reports:profit_by_invoice",
        "reports:profit_by_confirmation",
        "reports:item_sales",
        "reports:item_purchases",
        "reports:item_profit",
        "reports:item_history",
        "reports:service_sales",
        "reports:service_contracts",
        "reports:service_expiring",
        "reports:service_billing_due",
        "reports:service_invoice_history",
        "reports:cash_book",
        "reports:bank_book",
        "reports:general_ledger",
        "reports:account_ledger",
        "reports:trial_balance",
        "reports:profit_loss",
        "reports:balance_sheet",
        "reports:journal_report",
        "reports:expense_report",
        "reports:income_report",
        "reports:tax_summary",
        "reports:tax_summary_root",
        "reports:inventory_stock_balance",
        "reports:inventory_item_ledger",
        "reports:inventory_stock_in",
        "reports:inventory_stock_out",
        "reports:inventory_low_stock",
        "reports:inventory_valuation",
        "reports:system_activity",
        "reports:system_login_logout",
        "reports:system_prints",
        "reports:system_exports",
        "reports:system_backup_restore",
        "reports:system_validation_failures",
    ]

    CONTENT_CHECKS = {
        "reports:index": ["Customer Reports", "Supplier Reports", "Sales Reports", "Accounting Reports"],
        "reports:customer_reports": ["Customer Ledger", "Customer Statement", "Customer Outstanding", "Customer Aging", "Customer-wise Sales", "Customer-wise Receipts"],
        "reports:supplier_reports": ["Supplier Ledger", "Supplier Statement", "Supplier Payable", "Supplier Aging", "Supplier-wise Purchase", "Supplier-wise Payment"],
        "reports:sales_reports": ["Quotation Report", "Confirmation / PO Report", "Delivery Challan Report", "Sales Invoice Report", "Sales Return Report", "Receipt Report", "Sales Tax Report"],
        "reports:purchase_reports": ["Purchase Report", "Purchase Return Report", "Supplier Payment Report", "Purchase Tax Report", "Profit by Invoice", "Profit by Confirmation / PO"],
        "reports:item_reports": ["Item-wise Sales", "Item-wise Purchase", "Item-wise Profit", "Item Transaction History", "Service-wise Sales"],
        "reports:service_reports": ["Service Contract List", "Expiring Contracts", "Billing Due Contracts", "Contract Invoice History"],
        "reports:accounting_reports": ["Cash Book", "Bank Book", "General Ledger", "Account Ledger", "Trial Balance", "Profit and Loss", "Balance Sheet", "Journal Entries", "Expense Report", "Income Report"],
        "reports:tax_reports": ["Tax Summary"],
        "reports:inventory_reports": ["Stock Balance", "Item Ledger", "Stock In", "Stock Out", "Low Stock", "Valuation"],
        "reports:system_reports": ["User Activity", "Login / Logout", "Document Prints", "Report Exports", "Backup / Restore", "Validation Failures"],
        "reports:customer_ledger": ['id="customer_id"', "Date From", "Date To", "Branch", "Please select a customer to view ledger."],
        "reports:customer_statement": ['id="customer_id"', "Date From", "Date To", "Branch", "Please select a customer to view statement."],
        "reports:supplier_ledger": ['id="supplier_id"', "Date From", "Date To", "Branch", "Please select a supplier to view ledger."],
        "reports:supplier_statement": ['id="supplier_id"', "Date From", "Date To", "Branch", "Please select a supplier to view statement."],
        "reports:item_history": ['id="item_service_id"', "Date From", "Date To", "Branch", "Please select an item to view transaction history."],
        "reports:account_ledger": ['id="account_id"', "Date From", "Date To", "Branch", "Please select an account to view ledger."],
    }

    def handle(self, *args, **options):
        context = self.get_login_context()
        if not context:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required."))
            return
        failures = 0
        for name in self.GROUP_ROUTE_NAMES + self.REPORT_ROUTE_NAMES:
            try:
                url = reverse(name)
            except Exception as exc:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {name}: reverse failed: {exc}"))
                continue
            response = self.call_url(url, context)
            if response.status_code >= 400:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {name}: status {response.status_code}"))
            else:
                self.stdout.write(f"PASS {name}: status {response.status_code}")
                failures += self.check_content(name, response)

        for name in ["reports:customer_outstanding", "reports:sales_invoices", "reports:purchase_report", "reports:trial_balance"]:
            url = reverse(name)
            for suffix in ["?export=csv", "?print=1"]:
                response = self.call_url(url + suffix, context)
                if response.status_code >= 400:
                    failures += 1
                    self.stdout.write(self.style.ERROR(f"FAIL {name}{suffix}: status {response.status_code}"))
                else:
                    self.stdout.write(f"PASS {name}{suffix}: status {response.status_code}")

        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} report route check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: report routes ready."))

    def check_content(self, route_name, response):
        expected = self.CONTENT_CHECKS.get(route_name)
        if not expected:
            return 0
        content = response.content.decode("utf-8", errors="ignore")
        missing = [label for label in expected if label not in content]
        if missing:
            self.stdout.write(self.style.ERROR(f"FAIL {route_name}: missing visible labels: {', '.join(missing)}"))
            return 1
        if route_name == "reports:index":
            forbidden = [
                'href="/reports/customers/outstanding/"',
                'href="/reports/suppliers/payable/"',
                'href="/reports/sales/invoices/"',
                'href="/reports/purchases/purchases/"',
                'href="/reports/accounting/trial-balance/"',
            ]
            bad = [value for value in forbidden if value in content]
            required = [
                'href="/reports/customers/"',
                'href="/reports/suppliers/"',
                'href="/reports/sales/"',
                'href="/reports/purchases/"',
                'href="/reports/accounting/"',
            ]
            missing_links = [value for value in required if value not in content]
            if bad or missing_links:
                if bad:
                    self.stdout.write(self.style.ERROR(f"FAIL {route_name}: sidebar/index still contains direct report links: {', '.join(bad)}"))
                if missing_links:
                    self.stdout.write(self.style.ERROR(f"FAIL {route_name}: missing group links: {', '.join(missing_links)}"))
                return 1
        self.stdout.write(f"PASS {route_name}: visible labels present")
        return 0

    def call_url(self, url, session_context):
        factory = RequestFactory(HTTP_HOST="127.0.0.1")
        request = factory.get(url)
        request.session = dict(session_context)
        request._messages = FallbackStorage(request)
        match = resolve(request.path_info)
        return match.func(request, *match.args, **match.kwargs)

    def get_login_context(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.*, r.role_name, c.company_name
                FROM users u
                JOIN user_roles r ON r.id=u.role_id
                JOIN companies c ON c.id=u.company_id
                WHERE u.is_active=1
                ORDER BY u.is_master_user DESC, u.id
                LIMIT 1
                """
            )
            user = dictfetchone(cursor)
            if not user:
                return None
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, id LIMIT 1", [user["company_id"]])
            branch = dictfetchone(cursor)
            if not branch:
                return None
        return {
            "user_id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role_id": user["role_id"],
            "role_name": user["role_name"],
            "company_id": user["company_id"],
            "company_name": user["company_name"],
            "current_branch_id": branch["id"],
            "current_branch_name": branch["branch_name"],
            "is_master_user": int(user.get("is_master_user") or 0),
        }
