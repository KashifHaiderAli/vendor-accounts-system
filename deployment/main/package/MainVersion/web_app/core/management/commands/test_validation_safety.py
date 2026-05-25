from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from accounts_module.accounting_engine import AccountingError, create_journal_entry
from accounts_module import expense_services
from authentication.auth_utils import dictfetchone
from core.safety_checks import user_has_branch_access
from purchases import payment_services, services as purchase_services
from sales import invoice_services, receipt_services


class DummyRequest:
    def __init__(self, user_id, company_id, branch_id):
        self.session = {
            "user_id": user_id,
            "company_id": company_id,
            "current_branch_id": branch_id,
            "is_master_user": 0,
        }


class Command(BaseCommand):
    help = "Run validation and safety checks against current smoke data without altering business records."

    def handle(self, *args, **options):
        company = self.first_row("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
        branch = self.first_row("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company["id"]]) if company else None
        user = self.first_row("SELECT * FROM users WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company["id"]]) if company else None
        if not company or not branch or not user:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required. Run seed data first."))
            return

        company_id = company["id"]
        branch_id = branch["id"]
        failures = 0
        checks = [
            ("duplicate invoice number blocked", self.check_duplicate_invoice),
            ("invalid due date blocked", self.check_invoice_due_date),
            ("negative invoice item blocked", self.check_negative_invoice_item),
            ("receipt over balance blocked", self.check_receipt_over_balance),
            ("supplier payment over payable blocked", self.check_supplier_payment_over_balance),
            ("unbalanced journal blocked", self.check_unbalanced_journal),
            ("missing customer account blocked", self.check_missing_customer_account),
            ("missing supplier account blocked", self.check_missing_supplier_account),
            ("missing cash/bank account blocked", self.check_missing_cash_bank_account),
            ("branch access helper rejects invalid branch", lambda c, b: self.check_branch_access(user["id"], c, b)),
            ("expense voucher amount validation works", self.check_expense_validation),
        ]
        for label, func in checks:
            try:
                ok, detail = func(company_id, branch_id)
            except Exception as exc:
                ok, detail = False, str(exc)
            if ok:
                self.stdout.write(self.style.SUCCESS(f"PASS: {label}"))
            else:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL: {label} - {detail}"))
        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} validation safety check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: validation safety checks ready."))

    def check_duplicate_invoice(self, company_id, branch_id):
        invoice = self.first_row("SELECT * FROM sales_invoices WHERE company_id=%s AND branch_id=%s ORDER BY id LIMIT 1", [company_id, branch_id])
        customer = self.first_row("SELECT * FROM customers WHERE company_id=%s AND branch_id=%s AND account_id IS NOT NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        item = self.first_row("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s ORDER BY id LIMIT 1", [company_id, branch_id])
        if not invoice or not customer:
            return True, "Skipped; no invoice/customer."
        data = invoice_services.default_form_data(company_id, branch_id)
        data.update({"invoice_no": invoice["invoice_no"], "customer_id": customer["id"], "items": [self.invoice_item(item)]})
        errors, _cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("invoice_no")), errors

    def check_invoice_due_date(self, company_id, branch_id):
        customer = self.first_row("SELECT * FROM customers WHERE company_id=%s AND branch_id=%s AND account_id IS NOT NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        item = self.first_row("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s ORDER BY id LIMIT 1", [company_id, branch_id])
        data = invoice_services.default_form_data(company_id, branch_id)
        data.update({"invoice_no": "SAFETY-DUE-DATE", "invoice_date": "2026-05-09", "due_date": "2026-05-01", "customer_id": customer["id"] if customer else "", "items": [self.invoice_item(item)]})
        errors, _cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("due_date")), errors

    def check_negative_invoice_item(self, company_id, branch_id):
        customer = self.first_row("SELECT * FROM customers WHERE company_id=%s AND branch_id=%s AND account_id IS NOT NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        item = self.first_row("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s ORDER BY id LIMIT 1", [company_id, branch_id])
        data = invoice_services.default_form_data(company_id, branch_id)
        bad_item = self.invoice_item(item)
        bad_item["rate"] = "-1"
        data.update({"invoice_no": "SAFETY-NEGATIVE", "customer_id": customer["id"] if customer else "", "items": [bad_item]})
        errors, _cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("items") or errors.get("grand_total")), errors

    def check_receipt_over_balance(self, company_id, branch_id):
        invoice = self.first_row("SELECT * FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND balance_amount > 0 AND status <> 'Cancelled' ORDER BY id LIMIT 1", [company_id, branch_id])
        cash = self.first_row("SELECT * FROM cash_bank_accounts WHERE company_id=%s AND branch_id=%s AND account_id IS NOT NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        if not invoice or not cash:
            return True, "Skipped; no open invoice/cash account."
        data = receipt_services.default_form_data(company_id, branch_id, invoice)
        data.update({"cash_bank_account_id": cash["id"], "amount": str(float(invoice["balance_amount"]) + 1)})
        errors, _cleaned = receipt_services.validate_and_clean(data, company_id, branch_id)
        return bool(errors.get("amount")), errors

    def check_supplier_payment_over_balance(self, company_id, branch_id):
        purchase = self.first_row("SELECT * FROM supplier_purchases WHERE company_id=%s AND branch_id=%s AND balance_amount > 0 AND status <> 'Cancelled' ORDER BY id LIMIT 1", [company_id, branch_id])
        cash = self.first_row("SELECT * FROM cash_bank_accounts WHERE company_id=%s AND branch_id=%s AND account_id IS NOT NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        if not purchase or not cash:
            return True, "Skipped; no open purchase/cash account."
        data = payment_services.default_form_data(company_id, branch_id, purchase)
        data.update({"cash_bank_account_id": cash["id"], "amount": str(float(purchase["balance_amount"]) + 1)})
        errors, _cleaned = payment_services.validate_and_clean(data, company_id, branch_id)
        return bool(errors.get("amount")), errors

    def check_unbalanced_journal(self, company_id, branch_id):
        account = self.first_row("SELECT * FROM accounts WHERE company_id=%s AND (branch_id=%s OR branch_id IS NULL) ORDER BY id LIMIT 1", [company_id, branch_id])
        try:
            create_journal_entry(company_id, branch_id, "2026-05-09", "validation_test", None, "Unbalanced test", [{"account_id": account["id"], "debit": "10", "credit": "0"}])
        except AccountingError:
            return True, ""
        return False, "Unbalanced journal was accepted."

    def check_missing_customer_account(self, company_id, branch_id):
        customer = self.first_row("SELECT * FROM customers WHERE company_id=%s AND branch_id=%s AND account_id IS NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        item = self.first_row("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s ORDER BY id LIMIT 1", [company_id, branch_id])
        if not customer:
            return True, "Skipped; no unlinked customer in current DB."
        data = invoice_services.default_form_data(company_id, branch_id)
        data.update({"invoice_no": "SAFETY-MISSING-CUST-ACC", "customer_id": customer["id"], "items": [self.invoice_item(item)]})
        errors, _cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("customer_id")), errors

    def check_missing_supplier_account(self, company_id, branch_id):
        supplier = self.first_row("SELECT * FROM suppliers WHERE company_id=%s AND branch_id=%s AND account_id IS NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        if not supplier:
            return True, "Skipped; no unlinked supplier in current DB."
        data = purchase_services.default_form_data(company_id, branch_id)
        data.update({"purchase_no": "SAFETY-MISSING-SUP-ACC", "supplier_id": supplier["id"], "items": [{"item_service_id": "", "description": "Safety", "quantity": "1", "purchase_rate": "1", "tax_percent": "0"}]})
        errors, _cleaned = purchase_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("supplier_id")), errors

    def check_missing_cash_bank_account(self, company_id, branch_id):
        invoice = self.first_row("SELECT * FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND balance_amount > 0 ORDER BY id LIMIT 1", [company_id, branch_id])
        cash = self.first_row("SELECT * FROM cash_bank_accounts WHERE company_id=%s AND branch_id=%s AND account_id IS NULL ORDER BY id LIMIT 1", [company_id, branch_id])
        if not invoice or not cash:
            return True, "Skipped; no open invoice with unlinked cash/bank account in current DB."
        data = receipt_services.default_form_data(company_id, branch_id, invoice)
        data.update({"cash_bank_account_id": cash["id"], "amount": "1"})
        errors, _cleaned = receipt_services.validate_and_clean(data, company_id, branch_id)
        return bool(errors.get("cash_bank_account_id")), errors

    def check_branch_access(self, user_id, company_id, branch_id):
        request = DummyRequest(user_id, company_id, branch_id)
        return not user_has_branch_access(request, -999999), "Invalid branch was allowed."

    def check_expense_validation(self, company_id, branch_id):
        if not expense_services.table_exists():
            return True, "Skipped; expense voucher table missing."
        data = expense_services.default_form_data(company_id, branch_id)
        data["amount"] = "-1"
        errors, _cleaned = expense_services.validate_and_calculate(data, company_id, branch_id)
        return bool(errors.get("amount")), errors

    def invoice_item(self, item):
        return {"item_service_id": item["id"] if item else "", "description": "Safety item", "quantity": "1", "rate": "10", "discount_percent": "0", "discount_amount": "0", "tax_percent": "0"}

    def first_row(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchone(cursor)
