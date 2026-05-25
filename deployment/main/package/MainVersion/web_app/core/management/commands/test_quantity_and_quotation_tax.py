from __future__ import annotations

import re
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection
from django.template.loader import render_to_string

from accounts_module.accounting_utils import ensure_default_chart_of_accounts
from authentication.auth_utils import dictfetchone
from core.format_utils import format_quantity
from masters.master_utils import create_linked_account
from sales import services as quotation_services
from settings_module.services import now_text


class Command(BaseCommand):
    help = "Verify clean quantity display and quotation print tax total rendering."

    def handle(self, *args, **options):
        company, branch, user = self.get_context()
        if not company or not branch or not user:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required."))
            return
        company_id = company["id"]
        branch_id = branch["id"]
        user_id = user["id"]
        ensure_default_chart_of_accounts(company_id, branch_id)
        self.ensure_numbering(company_id, branch_id)
        customer_id = self.ensure_customer(company_id, branch_id, user_id)
        item_id = self.ensure_item(company_id, branch_id, user_id)

        data = quotation_services.default_form_data(company_id, branch_id)
        data.update(
            {
                "customer_mode": "existing",
                "customer_id": customer_id,
                "subject": f"AUTO-TEST Quantity Tax {now_text()}",
                "tax_option": "tax_exclusive",
                "status": "Draft",
            }
        )
        data["items"] = [
            {
                "item_service_id": item_id,
                "description": "AUTO-TEST Tax Product",
                "quantity": "1",
                "rate": "1000",
                "discount_percent": "0",
                "discount_amount": "0",
                "tax_percent": "18",
            }
        ]
        errors, cleaned = quotation_services.validate_and_calculate(data, company_id, branch_id)
        if errors:
            self.stdout.write(self.style.ERROR(f"FAIL: quotation validation failed: {errors}"))
            return
        quotation_id = quotation_services.save_quotation(company_id, branch_id, user_id, cleaned)
        quotation = quotation_services.get_quotation(company_id, branch_id, quotation_id)
        checks = []
        checks.append(("subtotal", Decimal(str(quotation["subtotal"])) == Decimal("1000")))
        checks.append(("tax_total", Decimal(str(quotation["tax_total"])) == Decimal("180")))
        checks.append(("grand_total", Decimal(str(quotation["grand_total"])) == Decimal("1180")))

        context = quotation_services.get_print_context(company_id, branch_id, quotation_id)
        rendered = render_to_string("sales/quotation_print.html", context)
        tax_column = re.search(r"<th[^>]*>\s*Tax(?:\s*%|\s*Total)?\s*</th>", rendered, flags=re.IGNORECASE)
        checks.append(("render contains Tax Total", "Tax Total" in rendered))
        checks.append(("render contains 180", "180" in rendered))
        checks.append(("render has no item tax column", tax_column is None))
        checks.append(("format 1.00", format_quantity("1.00") == "1"))
        checks.append(("format 2.50", format_quantity("2.50") == "2.5"))
        checks.append(("render quantity 1", ">1</td>" in rendered))

        failed = [name for name, ok in checks if not ok]
        for name, ok in checks:
            self.stdout.write(("PASS" if ok else "FAIL") + f": {name}")
        if failed:
            self.stdout.write(self.style.ERROR(f"FAIL: {len(failed)} quantity/tax check(s) failed: {', '.join(failed)}"))
            return
        self.stdout.write(self.style.SUCCESS("PASS: quantity formatting and quotation tax print checks passed."))

    def get_context(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company["id"]] if company else [])
            branch = dictfetchone(cursor)
            cursor.execute("SELECT * FROM users WHERE is_active=1 ORDER BY id LIMIT 1")
            user = dictfetchone(cursor)
        return company, branch, user

    def ensure_numbering(self, company_id, branch_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM numbering_settings WHERE company_id=%s AND branch_id=%s LIMIT 1", [company_id, branch_id])
            if cursor.fetchone():
                return
            timestamp = now_text()
            cursor.execute(
                """
                INSERT INTO numbering_settings (
                    company_id, branch_id, customer_prefix, supplier_prefix, item_prefix, quotation_prefix,
                    confirmation_prefix, delivery_challan_prefix, invoice_prefix, sales_return_prefix,
                    cash_memo_prefix, receipt_prefix, purchase_prefix, purchase_return_prefix,
                    supplier_payment_prefix, service_contract_prefix, expense_voucher_prefix,
                    use_year_in_number, number_padding, created_at, updated_at
                )
                VALUES (%s,%s,'CUS','SUP','ITM','QTN','CONF','DC','INV','SR','CM','RCPT','PUR','PR','SPAY','SC','EXP',1,4,%s,%s)
                """,
                [company_id, branch_id, timestamp, timestamp],
            )

    def ensure_customer(self, company_id, branch_id, user_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM customers WHERE company_id=%s AND branch_id=%s AND customer_code='AUTO-QTAX-CUS' LIMIT 1", [company_id, branch_id])
            row = cursor.fetchone()
            if row:
                return row[0]
        account_id = create_linked_account(company_id, branch_id, "AR-AUTO-QTAX-CUS", "AUTO-TEST Quotation Tax Customer", "Assets", "Accounts Receivable")
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customers (
                    company_id, branch_id, customer_code, company_name, contact_person, phone, mobile, email,
                    address, credit_limit, opening_balance, opening_balance_type, account_id, is_active,
                    remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s,%s,'AUTO-QTAX-CUS','AUTO-TEST Quotation Tax Customer','AUTO Contact','','03001234567',
                        'auto.qtax@example.com','Karachi',0,0,'Debit',%s,1,'AUTO quotation tax test',%s,%s,%s,%s)
                """,
                [company_id, branch_id, account_id, user_id, user_id, timestamp, timestamp],
            )
            return cursor.lastrowid

    def ensure_item(self, company_id, branch_id, user_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM item_services WHERE company_id=%s AND branch_id=%s AND item_code='AUTO-QTAX-ITEM' LIMIT 1", [company_id, branch_id])
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE item_services SET default_sale_rate=1000, default_tax_rate=18 WHERE id=%s", [row[0]])
                return row[0]
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO item_services (
                    company_id, branch_id, item_code, item_name, item_type, category,
                    default_purchase_rate, default_sale_rate, default_tax_rate,
                    warranty_or_service_description, is_active, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s,%s,'AUTO-QTAX-ITEM','AUTO-TEST Tax Product','product','AUTO',800,1000,18,
                        'AUTO quotation tax test item',1,'AUTO quotation tax test item',%s,%s,%s,%s)
                """,
                [company_id, branch_id, user_id, user_id, timestamp, timestamp],
            )
            return cursor.lastrowid
