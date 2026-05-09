from __future__ import annotations

from dataclasses import dataclass, field

from django.core.management.base import BaseCommand
from django.db import connection

from accounts_module.accounting_utils import ensure_default_chart_of_accounts
from accounts_module import expense_services
from authentication.auth_utils import dictfetchone
from masters.master_utils import create_linked_account
from purchases import payment_services, return_services as purchase_return_services, services as purchase_services
from sales import delivery_services, invoice_services, receipt_services, return_services as sales_return_services, services as sales_services
from services import contract_services
from settings_module.services import now_text


@dataclass
class Counter:
    created: int = 0
    skipped: int = 0


@dataclass
class SmokeStats:
    buckets: dict[str, Counter] = field(default_factory=dict)

    def add(self, bucket, created):
        counter = self.buckets.setdefault(bucket, Counter())
        if created:
            counter.created += 1
        else:
            counter.skipped += 1


class Command(BaseCommand):
    help = "Create idempotent development smoke test data for completed modules."

    def handle(self, *args, **options):
        stats = SmokeStats()
        company = self.first_row("SELECT * FROM companies WHERE is_active = 1 ORDER BY id LIMIT 1")
        branch = self.first_row("SELECT * FROM branches WHERE company_id = %s AND is_active = 1 ORDER BY id LIMIT 1", [company["id"]]) if company else None
        user = self.first_row("SELECT * FROM users WHERE is_master_user = 1 AND is_active = 1 ORDER BY id LIMIT 1")
        if not company or not branch or not user:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and master admin user are required."))
            return

        company_id = company["id"]
        branch_id = branch["id"]
        user_id = user["id"]
        ensure_default_chart_of_accounts(company_id, branch_id)
        self.ensure_numbering_settings(company_id, branch_id)

        terms_15 = self.ensure_payment_term(company_id, branch_id, user_id, "Smoke 15 Days", 15, stats)
        self.ensure_payment_term(company_id, branch_id, user_id, "Smoke Cash", 0, stats)

        customer_1 = self.ensure_customer(company_id, branch_id, user_id, "SMK-CUS001", "Smoke Customer One Pvt Ltd", terms_15, stats)
        self.ensure_customer(company_id, branch_id, user_id, "SMK-CUS002", "Smoke Walk-in Corporate Client", terms_15, stats)
        supplier_1 = self.ensure_supplier(company_id, branch_id, user_id, "SMK-SUP001", "Smoke Supplier One", stats)
        self.ensure_supplier(company_id, branch_id, user_id, "SMK-SUP002", "Smoke Supplier Two", stats)

        item_1 = self.ensure_item(company_id, branch_id, user_id, "SMK-ITM001", "Smoke Router Product", "product", "1500", "2200", "5", stats)
        item_2 = self.ensure_item(company_id, branch_id, user_id, "SMK-ITM002", "Smoke Switch Product", "product", "2500", "3400", "5", stats)
        self.ensure_item(company_id, branch_id, user_id, "SMK-SRV001", "Smoke Configuration Service", "service", "500", "1000", "0", stats)

        cash_account = self.ensure_cash_bank(company_id, branch_id, user_id, "Smoke Cash Account", "cash", stats)
        self.ensure_cash_bank(company_id, branch_id, user_id, "Smoke Bank Account", "bank", stats)
        self.ensure_expense_head(company_id, branch_id, user_id, "SMK-EXP001", "Smoke Office Expense", stats)

        quotation = self.ensure_smoke_quotation(company_id, branch_id, user_id, customer_1, [item_1, item_2], stats)
        self.ensure_unregistered_quotation(company_id, branch_id, user_id, [item_1], stats)
        confirmation_po = self.ensure_po_confirmation(company_id, branch_id, user_id, quotation, stats)
        self.ensure_phone_confirmation(company_id, branch_id, user_id, customer_1, stats)
        purchase = self.ensure_supplier_purchase(company_id, branch_id, user_id, supplier_1, item_1, confirmation_po, stats)
        challan = self.ensure_delivery_challan(company_id, branch_id, user_id, confirmation_po, stats)
        invoice = self.ensure_sales_invoice(company_id, branch_id, user_id, challan, stats)
        self.ensure_customer_receipt(company_id, branch_id, user_id, invoice, cash_account, stats)
        self.ensure_supplier_payment(company_id, branch_id, user_id, purchase, cash_account, stats)
        self.ensure_sales_return(company_id, branch_id, user_id, invoice, stats)
        self.ensure_purchase_return(company_id, branch_id, user_id, purchase, stats)
        contract = self.ensure_service_contract(company_id, branch_id, user_id, customer_1, stats)
        self.ensure_contract_invoice(company_id, branch_id, user_id, contract, stats)
        self.ensure_expense_voucher(company_id, branch_id, user_id, cash_account, stats)

        for bucket, counter in stats.buckets.items():
            self.stdout.write(f"{bucket}: created={counter.created}, skipped={counter.skipped}")
        self.stdout.write(self.style.SUCCESS("PASS: smoke test data ready"))

    def first_row(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchone(cursor)

    def ensure_numbering_settings(self, company_id, branch_id):
        if self.first_row("SELECT id FROM numbering_settings WHERE company_id = %s AND branch_id = %s LIMIT 1", [company_id, branch_id]):
            return
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO numbering_settings (
                    company_id, branch_id, customer_prefix, supplier_prefix, item_prefix,
                    quotation_prefix, confirmation_prefix, delivery_challan_prefix, invoice_prefix,
                    sales_return_prefix, cash_memo_prefix, receipt_prefix, purchase_prefix,
                    purchase_return_prefix, supplier_payment_prefix, service_contract_prefix,
                    expense_voucher_prefix, use_year_in_number, number_padding, created_at, updated_at
                )
                VALUES (%s, %s, 'CUS', 'SUP', 'ITM', 'QTN', 'CONF', 'DC', 'INV',
                        'SR', 'CM', 'RCPT', 'PUR', 'PR', 'SPAY', 'SC', 'EXP', 1, 4, %s, %s)
                """,
                [company_id, branch_id, timestamp, timestamp],
            )

    def ensure_payment_term(self, company_id, branch_id, user_id, name, days, stats):
        existing = self.first_row(
            "SELECT id FROM payment_terms WHERE company_id = %s AND branch_id = %s AND lower(name) = lower(%s) LIMIT 1",
            [company_id, branch_id, name],
        )
        if existing:
            stats.add("payment_terms", False)
            return existing["id"]
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO payment_terms (company_id, branch_id, name, days, description, is_active, created_by_id, updated_by_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                """,
                [company_id, branch_id, name, days, "Smoke test payment term.", user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("payment_terms", True)
        return record_id

    def ensure_customer(self, company_id, branch_id, user_id, code, name, terms_id, stats):
        existing = self.first_row("SELECT id FROM customers WHERE company_id = %s AND branch_id = %s AND customer_code = %s LIMIT 1", [company_id, branch_id, code])
        if existing:
            stats.add("customers", False)
            return existing["id"]
        timestamp = now_text()
        account_id = create_linked_account(company_id, branch_id, f"AR-{code}", name, "Assets", "Accounts Receivable")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customers (
                    company_id, branch_id, customer_code, company_name, contact_person, phone, mobile, email, address,
                    payment_terms_id, credit_limit, opening_balance, opening_balance_type, account_id, is_active,
                    remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'Smoke Contact', '021 34567890', '+92 300 1234567', %s, 'Smoke customer address',
                        %s, 50000, 0, 'Debit', %s, 1, 'Smoke test customer.', %s, %s, %s, %s)
                """,
                [company_id, branch_id, code, name, f"{code.lower()}@example.com", terms_id, account_id, user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("customers", True)
        return record_id

    def ensure_supplier(self, company_id, branch_id, user_id, code, name, stats):
        existing = self.first_row("SELECT id FROM suppliers WHERE company_id = %s AND branch_id = %s AND supplier_code = %s LIMIT 1", [company_id, branch_id, code])
        if existing:
            stats.add("suppliers", False)
            return existing["id"]
        timestamp = now_text()
        account_id = create_linked_account(company_id, branch_id, f"AP-{code}", name, "Liability", "Accounts Payable")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO suppliers (
                    company_id, branch_id, supplier_code, supplier_name, contact_person, phone, mobile, email, address,
                    opening_balance, opening_balance_type, account_id, is_active, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'Smoke Supplier Contact', '021 34567890', '+92 300 1234567', %s, 'Smoke supplier address',
                        0, 'Credit', %s, 1, 'Smoke test supplier.', %s, %s, %s, %s)
                """,
                [company_id, branch_id, code, name, f"{code.lower()}@example.com", account_id, user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("suppliers", True)
        return record_id

    def ensure_item(self, company_id, branch_id, user_id, code, name, item_type, purchase_rate, sale_rate, tax_rate, stats):
        existing = self.first_row("SELECT id FROM item_services WHERE company_id = %s AND branch_id = %s AND item_code = %s LIMIT 1", [company_id, branch_id, code])
        if existing:
            stats.add("items", False)
            return existing["id"]
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO item_services (
                    company_id, branch_id, item_code, item_name, item_type, category,
                    default_purchase_rate, default_sale_rate, default_tax_rate,
                    warranty_or_service_description, is_active, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'Smoke', %s, %s, %s, 'Smoke test item/service.', 1, 'Smoke item.', %s, %s, %s, %s)
                """,
                [company_id, branch_id, code, name, item_type, purchase_rate, sale_rate, tax_rate, user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("items", True)
        return record_id

    def ensure_cash_bank(self, company_id, branch_id, user_id, name, account_type, stats):
        existing = self.first_row("SELECT id FROM cash_bank_accounts WHERE company_id = %s AND branch_id = %s AND lower(account_name) = lower(%s) LIMIT 1", [company_id, branch_id, name])
        if existing:
            stats.add("cash_bank", False)
            return existing["id"]
        parent = "Cash" if account_type == "cash" else "Bank"
        code = "CASH-SMK" if account_type == "cash" else "BANK-SMK"
        account_id = create_linked_account(company_id, branch_id, code, name, "Assets", parent)
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cash_bank_accounts (
                    company_id, branch_id, account_name, account_type, bank_name, account_number, opening_balance,
                    account_id, is_active, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, 'SMOKE-001', 0, %s, 1, 'Smoke cash/bank.', %s, %s, %s, %s)
                """,
                [company_id, branch_id, name, account_type, "Smoke Bank" if account_type == "bank" else "", account_id, user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("cash_bank", True)
        return record_id

    def ensure_expense_head(self, company_id, branch_id, user_id, code, name, stats):
        existing = self.first_row("SELECT id FROM expense_heads WHERE company_id = %s AND branch_id = %s AND expense_code = %s LIMIT 1", [company_id, branch_id, code])
        if existing:
            stats.add("expense_heads", False)
            return existing["id"]
        account_id = create_linked_account(company_id, branch_id, f"EXP-{code}", name, "Expense", "Office Expenses")
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO expense_heads (
                    company_id, branch_id, expense_code, expense_name, category, account_id, is_active,
                    remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'Smoke', %s, 1, 'Smoke expense head.', %s, %s, %s, %s)
                """,
                [company_id, branch_id, code, name, account_id, user_id, user_id, timestamp, timestamp],
            )
            record_id = cursor.lastrowid
        stats.add("expense_heads", True)
        return record_id

    def ensure_smoke_quotation(self, company_id, branch_id, user_id, customer_id, item_ids, stats):
        existing = self.first_row("SELECT id FROM quotations WHERE company_id = %s AND branch_id = %s AND subject = 'Smoke Existing Customer Quotation' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("quotations", False)
            return existing["id"]
        data = sales_services.default_form_data(company_id, branch_id)
        data.update({"customer_mode": "existing", "customer_id": customer_id, "subject": "Smoke Existing Customer Quotation", "status": "Printed"})
        data["items"] = [
            {"item_service_id": item_ids[0], "description": "Smoke Router Product", "quantity": "2", "rate": "2200", "discount_percent": "0", "discount_amount": "0", "tax_percent": "5"},
            {"item_service_id": item_ids[1], "description": "Smoke Switch Product", "quantity": "1", "rate": "3400", "discount_percent": "0", "discount_amount": "0", "tax_percent": "5"},
        ]
        errors, cleaned = sales_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke quotation validation failed: {errors}")
        record_id = sales_services.save_quotation(company_id, branch_id, user_id, cleaned)
        stats.add("quotations", True)
        return record_id

    def ensure_unregistered_quotation(self, company_id, branch_id, user_id, item_ids, stats):
        existing = self.first_row("SELECT id FROM quotations WHERE company_id = %s AND branch_id = %s AND subject = 'Smoke Unregistered Party Quotation' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("quotations", False)
            return existing["id"]
        data = sales_services.default_form_data(company_id, branch_id)
        data.update({"customer_mode": "new", "customer_name": "Smoke Unregistered Party", "customer_mobile": "+92 300 7654321", "subject": "Smoke Unregistered Party Quotation", "status": "Draft"})
        data["items"] = [{"item_service_id": item_ids[0], "description": "Smoke Router Product", "quantity": "1", "rate": "2200", "discount_percent": "0", "discount_amount": "0", "tax_percent": "5"}]
        errors, cleaned = sales_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke unregistered quotation validation failed: {errors}")
        record_id = sales_services.save_quotation(company_id, branch_id, user_id, cleaned)
        stats.add("quotations", True)
        return record_id

    def ensure_po_confirmation(self, company_id, branch_id, user_id, quotation_id, stats):
        existing = self.first_row("SELECT id FROM customer_confirmations WHERE company_id = %s AND branch_id = %s AND quotation_id = %s AND status <> 'Cancelled' LIMIT 1", [company_id, branch_id, quotation_id])
        if existing:
            stats.add("confirmations", False)
            return existing["id"]
        quotation = sales_services.get_quotation(company_id, branch_id, quotation_id)
        data = sales_services.default_confirmation_form_data(company_id, branch_id, quotation)
        data.update({"confirmation_type": "PO", "po_number": "SMK-PO-001", "po_date": today_text(), "confirmation_note": "Smoke PO confirmation."})
        errors, cleaned, _ = sales_services.validate_confirmation_data(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke PO confirmation validation failed: {errors}")
        record_id = sales_services.save_confirmation(company_id, branch_id, user_id, cleaned)
        stats.add("confirmations", True)
        return record_id

    def ensure_phone_confirmation(self, company_id, branch_id, user_id, customer_id, stats):
        existing = self.first_row("SELECT id FROM customer_confirmations WHERE company_id = %s AND branch_id = %s AND confirmation_note = 'Smoke phone confirmation.' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("confirmations", False)
            return existing["id"]
        data = sales_services.default_confirmation_form_data(company_id, branch_id)
        data.update({"customer_id": customer_id, "confirmation_type": "Phone", "po_number": "", "confirmation_note": "Smoke phone confirmation.", "total_amount": "1500"})
        errors, cleaned, _ = sales_services.validate_confirmation_data(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke phone confirmation validation failed: {errors}")
        record_id = sales_services.save_confirmation(company_id, branch_id, user_id, cleaned)
        stats.add("confirmations", True)
        return record_id

    def ensure_supplier_purchase(self, company_id, branch_id, user_id, supplier_id, item_id, confirmation_id, stats):
        existing = self.first_row("SELECT id FROM supplier_purchases WHERE company_id = %s AND branch_id = %s AND supplier_bill_no = 'SMK-BILL-001' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("purchases", False)
            return existing["id"]
        data = purchase_services.default_form_data(company_id, branch_id)
        data.update({"supplier_id": supplier_id, "supplier_bill_no": "SMK-BILL-001", "supplier_bill_date": today_text(), "confirmation_id": confirmation_id, "remarks": "Smoke supplier purchase."})
        data["items"] = [{"item_service_id": item_id, "description": "Smoke Router Product", "quantity": "2", "purchase_rate": "1500", "tax_percent": "5"}]
        errors, cleaned = purchase_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke supplier purchase validation failed: {errors}")
        record_id = purchase_services.save_purchase(company_id, branch_id, user_id, cleaned)
        stats.add("purchases", True)
        return record_id

    def ensure_delivery_challan(self, company_id, branch_id, user_id, confirmation_id, stats):
        existing = self.first_row("SELECT id FROM delivery_challans WHERE company_id = %s AND branch_id = %s AND confirmation_id = %s LIMIT 1", [company_id, branch_id, confirmation_id])
        if existing:
            stats.add("delivery_challans", False)
            return existing["id"]
        confirmation = delivery_services.get_confirmation(company_id, branch_id, confirmation_id)
        data = delivery_services.default_form_data(company_id, branch_id, confirmation=confirmation)
        data.update({"delivered_by": "Smoke Delivery Person", "remarks": "Smoke delivery challan."})
        errors, cleaned = delivery_services.validate_and_clean(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke delivery challan validation failed: {errors}")
        record_id = delivery_services.save_challan(company_id, branch_id, user_id, cleaned)
        stats.add("delivery_challans", True)
        return record_id

    def ensure_sales_invoice(self, company_id, branch_id, user_id, challan_id, stats):
        existing = self.first_row("SELECT id FROM sales_invoices WHERE company_id = %s AND branch_id = %s AND delivery_challan_id = %s AND status <> 'Cancelled' LIMIT 1", [company_id, branch_id, challan_id])
        if existing:
            stats.add("invoices", False)
            return existing["id"]
        dc = invoice_services.get_delivery_challan(company_id, branch_id, challan_id)
        data = invoice_services.default_form_data(company_id, branch_id, "tax_invoice", dc=dc)
        data.update({"remarks": "Smoke sales invoice."})
        if data.get("items"):
            data["items"][0]["rate"] = "2200"
            data["items"][0]["tax_percent"] = "5"
        errors, cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke sales invoice validation failed: {errors}")
        record_id = invoice_services.save_invoice(company_id, branch_id, user_id, cleaned)
        stats.add("invoices", True)
        return record_id

    def ensure_customer_receipt(self, company_id, branch_id, user_id, invoice_id, cash_bank_id, stats):
        existing = self.first_row("SELECT id FROM customer_receipts WHERE company_id = %s AND branch_id = %s AND adjusted_invoice_id = %s LIMIT 1", [company_id, branch_id, invoice_id])
        if existing:
            stats.add("receipts", False)
            return existing["id"]
        invoice = receipt_services.get_invoice(company_id, branch_id, invoice_id)
        if not invoice or receipt_services.money(invoice.get("balance_amount")) <= 0:
            stats.add("receipts", False)
            return None
        data = receipt_services.default_form_data(company_id, branch_id, invoice)
        data.update({"cash_bank_account_id": cash_bank_id, "amount": "1000.00", "remarks": "Smoke customer receipt."})
        if receipt_services.money(invoice.get("balance_amount")) < receipt_services.money(data["amount"]):
            data["amount"] = receipt_services.format_money(invoice.get("balance_amount"))
        errors, cleaned = receipt_services.validate_and_clean(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke customer receipt validation failed: {errors}")
        record_id = receipt_services.save_receipt(company_id, branch_id, user_id, cleaned)
        stats.add("receipts", True)
        return record_id

    def ensure_supplier_payment(self, company_id, branch_id, user_id, purchase_id, cash_bank_id, stats):
        existing = self.first_row("SELECT id FROM supplier_payments WHERE company_id = %s AND branch_id = %s AND adjusted_purchase_id = %s LIMIT 1", [company_id, branch_id, purchase_id])
        if existing:
            stats.add("supplier_payments", False)
            return existing["id"]
        purchase = payment_services.get_purchase(company_id, branch_id, purchase_id)
        if not purchase or payment_services.money(purchase.get("balance_amount")) <= 0:
            stats.add("supplier_payments", False)
            return None
        data = payment_services.default_form_data(company_id, branch_id, purchase)
        data.update({"cash_bank_account_id": cash_bank_id, "amount": "500.00", "remarks": "Smoke supplier payment."})
        if payment_services.money(purchase.get("balance_amount")) < payment_services.money(data["amount"]):
            data["amount"] = payment_services.format_money(purchase.get("balance_amount"))
        errors, cleaned = payment_services.validate_and_clean(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke supplier payment validation failed: {errors}")
        record_id = payment_services.save_payment(company_id, branch_id, user_id, cleaned)
        stats.add("supplier_payments", True)
        return record_id

    def ensure_sales_return(self, company_id, branch_id, user_id, invoice_id, stats):
        existing = self.first_row("SELECT id FROM sales_returns WHERE company_id = %s AND branch_id = %s AND sales_invoice_id = %s AND return_reason = 'Smoke sales return.' LIMIT 1", [company_id, branch_id, invoice_id])
        if existing:
            stats.add("sales_returns", False)
            return existing["id"]
        invoice = sales_return_services.get_invoice(company_id, branch_id, invoice_id)
        if not invoice:
            stats.add("sales_returns", False)
            return None
        data = sales_return_services.default_form_data(company_id, branch_id, invoice)
        data.update({"return_reason": "Smoke sales return.", "remarks": "Smoke credit note."})
        if data.get("items"):
            data["items"] = [data["items"][0]]
            data["items"][0]["quantity"] = "1"
        errors, cleaned = sales_return_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            stats.add("sales_returns", False)
            return None
        record_id = sales_return_services.save_return(company_id, branch_id, user_id, cleaned)
        stats.add("sales_returns", True)
        return record_id

    def ensure_purchase_return(self, company_id, branch_id, user_id, purchase_id, stats):
        existing = self.first_row("SELECT id FROM purchase_returns WHERE company_id = %s AND branch_id = %s AND supplier_purchase_id = %s AND return_reason = 'Smoke purchase return.' LIMIT 1", [company_id, branch_id, purchase_id])
        if existing:
            stats.add("purchase_returns", False)
            return existing["id"]
        purchase = purchase_return_services.get_purchase(company_id, branch_id, purchase_id)
        if not purchase:
            stats.add("purchase_returns", False)
            return None
        data = purchase_return_services.default_form_data(company_id, branch_id, purchase)
        data.update({"return_reason": "Smoke purchase return.", "remarks": "Smoke debit note."})
        if data.get("items"):
            data["items"] = [data["items"][0]]
            data["items"][0]["quantity"] = "1"
        errors, cleaned = purchase_return_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            stats.add("purchase_returns", False)
            return None
        record_id = purchase_return_services.save_return(company_id, branch_id, user_id, cleaned)
        stats.add("purchase_returns", True)
        return record_id

    def ensure_service_contract(self, company_id, branch_id, user_id, customer_id, stats):
        existing = self.first_row("SELECT id FROM service_contracts WHERE company_id = %s AND branch_id = %s AND service_type = 'Smoke Support Contract' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("service_contracts", False)
            return existing["id"]
        data = contract_services.default_form_data(company_id, branch_id)
        data.update({"customer_id": customer_id, "service_type": "Smoke Support Contract", "billing_cycle": "Monthly", "contract_amount": "2500", "tax_applicable": 1, "contract_details": "Smoke monthly support contract.", "remarks": "Smoke service contract."})
        errors, cleaned = contract_services.validate_contract(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke service contract validation failed: {errors}")
        record_id = contract_services.save_contract(company_id, branch_id, user_id, cleaned)
        stats.add("service_contracts", True)
        return record_id

    def ensure_contract_invoice(self, company_id, branch_id, user_id, contract_id, stats):
        if not contract_id:
            stats.add("contract_invoices", False)
            return None
        contract = contract_services.get_contract(company_id, branch_id, contract_id)
        existing = self.first_row("SELECT id FROM sales_invoices WHERE company_id = %s AND branch_id = %s AND remarks = %s LIMIT 1", [company_id, branch_id, f"Generated from service contract {contract['contract_no']}."])
        if existing:
            stats.add("contract_invoices", False)
            return existing["id"]
        class FakeRequest:
            session = {"company_id": company_id, "current_branch_id": branch_id, "user_id": user_id}
        try:
            record_id = contract_services.generate_invoice_from_contract(FakeRequest(), contract)
        except ValueError:
            stats.add("contract_invoices", False)
            return None
        stats.add("contract_invoices", True)
        return record_id

    def ensure_expense_voucher(self, company_id, branch_id, user_id, cash_bank_id, stats):
        if not expense_services.table_exists():
            stats.add("expense_vouchers", False)
            return None
        existing = self.first_row("SELECT id FROM expense_vouchers WHERE company_id=%s AND branch_id=%s AND remarks='Smoke expense voucher.' LIMIT 1", [company_id, branch_id])
        if existing:
            stats.add("expense_vouchers", False)
            return existing["id"]
        expense = self.first_row("SELECT id FROM expense_heads WHERE company_id=%s AND branch_id=%s AND expense_code='SMK-EXP001' LIMIT 1", [company_id, branch_id])
        if not expense:
            stats.add("expense_vouchers", False)
            return None
        data = expense_services.default_form_data(company_id, branch_id)
        data.update({"expense_head_id": expense["id"], "cash_bank_account_id": cash_bank_id, "payment_mode": "Cash", "amount": "750.00", "tax_percent": "0", "remarks": "Smoke expense voucher."})
        errors, cleaned = expense_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            raise RuntimeError(f"Smoke expense voucher validation failed: {errors}")
        record_id = expense_services.save_voucher(company_id, branch_id, user_id, cleaned)
        stats.add("expense_vouchers", True)
        return record_id


def today_text():
    return sales_services.today_iso()
