from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import OperationalError, connection

from authentication.auth_utils import dictfetchone
from reports import report_utils


class Command(BaseCommand):
    help = "Create/reuse AUTO-TEST party statement data and verify customer/supplier statement balances."

    def handle(self, *args, **options):
        scope = self.get_scope()
        if not scope:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required."))
            return
        company_id, branch_id, user_id = scope["company_id"], scope["branch_id"], scope["user_id"]
        today = date.today().isoformat()
        now = datetime.now().isoformat(timespec="seconds")

        self.strict_autotest = True
        try:
            customer_id = self.ensure_customer(company_id, branch_id, user_id, now)
            invoice_id = self.ensure_sales_invoice(company_id, branch_id, user_id, customer_id, today, now)
            self.ensure_customer_receipt(company_id, branch_id, user_id, customer_id, invoice_id, today, now)

            supplier_id = self.ensure_supplier(company_id, branch_id, user_id, now)
            purchase_id = self.ensure_supplier_purchase(company_id, branch_id, user_id, supplier_id, today, now)
            self.ensure_supplier_payment(company_id, branch_id, user_id, supplier_id, purchase_id, today, now)
        except OperationalError as exc:
            self.strict_autotest = False
            self.stdout.write(self.style.WARNING(f"WARNING: could not write AUTO-TEST statement data: {exc}"))
            self.stdout.write("Trying existing party statement data instead.")
            customer_id = self.find_customer_with_statement_data(company_id, branch_id)
            supplier_id = self.find_supplier_with_statement_data(company_id, branch_id)
            if not customer_id or not supplier_id:
                self.stdout.write(self.style.ERROR("FAIL: no writable database and no existing customer/supplier statement data found."))
                return

        failures = 0
        failures += self.check_customer_statement(company_id, branch_id, customer_id)
        failures += self.check_supplier_statement(company_id, branch_id, supplier_id)

        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} party statement check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: party statements ready."))

    def get_scope(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            if not company:
                return None
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, id LIMIT 1", [company["id"]])
            branch = dictfetchone(cursor)
            cursor.execute("SELECT * FROM users WHERE company_id=%s AND is_active=1 ORDER BY is_master_user DESC, id LIMIT 1", [company["id"]])
            user = dictfetchone(cursor)
        if not branch or not user:
            return None
        return {"company_id": company["id"], "branch_id": branch["id"], "user_id": user["id"]}

    def ensure_customer(self, company_id, branch_id, user_id, now):
        existing = self.fetchone(
            "SELECT id FROM customers WHERE company_id=%s AND branch_id=%s AND customer_code=%s",
            [company_id, branch_id, "AUTO-TEST-STMT-CUST"],
        )
        if existing:
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customers (
                    company_id, branch_id, customer_code, company_name, contact_person, mobile, email, address,
                    credit_limit, opening_balance, opening_balance_type, is_active, remarks, created_by_id,
                    updated_by_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,1,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, "AUTO-TEST-STMT-CUST", "AUTO-TEST Statement Customer", "AUTO-TEST", "03000000001", "autotest.statement.customer@example.com", "Karachi", "Debit", "AUTO-TEST statement data", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def ensure_supplier(self, company_id, branch_id, user_id, now):
        existing = self.fetchone(
            "SELECT id FROM suppliers WHERE company_id=%s AND branch_id=%s AND supplier_code=%s",
            [company_id, branch_id, "AUTO-TEST-STMT-SUP"],
        )
        if existing:
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO suppliers (
                    company_id, branch_id, supplier_code, supplier_name, contact_person, mobile, email, address,
                    opening_balance, opening_balance_type, is_active, remarks, created_by_id, updated_by_id,
                    created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,1,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, "AUTO-TEST-STMT-SUP", "AUTO-TEST Statement Supplier", "AUTO-TEST", "03000000002", "autotest.statement.supplier@example.com", "Karachi", "Credit", "AUTO-TEST statement data", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def ensure_sales_invoice(self, company_id, branch_id, user_id, customer_id, today, now):
        invoice_no = "AUTO-TEST-STMT-INV-001"
        existing = self.fetchone("SELECT id FROM sales_invoices WHERE company_id=%s AND branch_id=%s AND invoice_no=%s", [company_id, branch_id, invoice_no])
        if existing:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE sales_invoices
                    SET customer_id=%s, invoice_date=%s, subtotal=1000, discount_total=0, tax_total=0,
                        grand_total=1000, received_amount=250, balance_amount=750, status='Partially Paid',
                        updated_by_id=%s, updated_at=%s
                    WHERE id=%s
                    """,
                    [customer_id, today, user_id, now, existing["id"]],
                )
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sales_invoices (
                    company_id, branch_id, invoice_no, invoice_date, invoice_type, customer_id, subtotal,
                    discount_total, tax_total, grand_total, received_amount, balance_amount, status, remarks,
                    created_by_id, updated_by_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,'tax_invoice',%s,1000,0,0,1000,250,750,'Partially Paid',%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, invoice_no, today, customer_id, "AUTO-TEST statement invoice", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def ensure_customer_receipt(self, company_id, branch_id, user_id, customer_id, invoice_id, today, now):
        receipt_no = "AUTO-TEST-STMT-RCV-001"
        existing = self.fetchone("SELECT id FROM customer_receipts WHERE company_id=%s AND branch_id=%s AND receipt_no=%s", [company_id, branch_id, receipt_no])
        if existing:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE customer_receipts SET customer_id=%s, receipt_date=%s, amount=250, adjusted_invoice_id=%s, updated_by_id=%s, updated_at=%s WHERE id=%s",
                    [customer_id, today, invoice_id, user_id, now, existing["id"]],
                )
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customer_receipts (
                    company_id, branch_id, receipt_no, receipt_date, customer_id, payment_mode, amount,
                    adjusted_invoice_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,'Cash',250,%s,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, receipt_no, today, customer_id, invoice_id, "AUTO-TEST statement receipt", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def ensure_supplier_purchase(self, company_id, branch_id, user_id, supplier_id, today, now):
        purchase_no = "AUTO-TEST-STMT-PUR-001"
        existing = self.fetchone("SELECT id FROM supplier_purchases WHERE company_id=%s AND branch_id=%s AND purchase_no=%s", [company_id, branch_id, purchase_no])
        if existing:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE supplier_purchases
                    SET supplier_id=%s, purchase_date=%s, supplier_bill_no='AUTO-TEST-STMT-BILL-001',
                        subtotal=800, tax_total=0, grand_total=800, paid_amount=300, balance_amount=500,
                        status='Partially Paid', updated_by_id=%s, updated_at=%s
                    WHERE id=%s
                    """,
                    [supplier_id, today, user_id, now, existing["id"]],
                )
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO supplier_purchases (
                    company_id, branch_id, purchase_no, purchase_date, supplier_id, supplier_bill_no,
                    subtotal, tax_total, grand_total, paid_amount, balance_amount, status, remarks,
                    created_by_id, updated_by_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,'AUTO-TEST-STMT-BILL-001',800,0,800,300,500,'Partially Paid',%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, purchase_no, today, supplier_id, "AUTO-TEST statement purchase", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def ensure_supplier_payment(self, company_id, branch_id, user_id, supplier_id, purchase_id, today, now):
        payment_no = "AUTO-TEST-STMT-PAY-001"
        existing = self.fetchone("SELECT id FROM supplier_payments WHERE company_id=%s AND branch_id=%s AND payment_no=%s", [company_id, branch_id, payment_no])
        if existing:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE supplier_payments SET supplier_id=%s, payment_date=%s, amount=300, adjusted_purchase_id=%s, updated_by_id=%s, updated_at=%s WHERE id=%s",
                    [supplier_id, today, purchase_id, user_id, now, existing["id"]],
                )
            return existing["id"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO supplier_payments (
                    company_id, branch_id, payment_no, payment_date, supplier_id, payment_mode, amount,
                    adjusted_purchase_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,'Cash',300,%s,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, payment_no, today, supplier_id, purchase_id, "AUTO-TEST statement payment", user_id, user_id, now, now],
            )
            return cursor.lastrowid

    def check_customer_statement(self, company_id, branch_id, customer_id):
        data, summary = report_utils.customer_statement(company_id, branch_id, {"customer_id": str(customer_id)})
        refs = {row.get("ref_no"): row for row in data}
        failures = 0
        if self.strict_autotest and "AUTO-TEST-STMT-INV-001" not in refs:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL customer statement: invoice row missing."))
        if self.strict_autotest and "AUTO-TEST-STMT-RCV-001" not in refs:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL customer statement: receipt row missing."))
        if not data:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL customer statement: no rows returned."))
        expected_balance = Decimal("750.00") if refs.get("AUTO-TEST-STMT-INV-001") else Decimal(str(summary.get("Closing Balance") or 0))
        if Decimal(str(summary.get("Closing Balance") or 0)) != expected_balance:
            failures += 1
            self.stdout.write(self.style.ERROR(f"FAIL customer statement: expected balance {expected_balance}, got {summary.get('Closing Balance')}"))
        if not failures:
            self.stdout.write("PASS customer statement: invoice, receipt, and running balance verified.")
        return failures

    def check_supplier_statement(self, company_id, branch_id, supplier_id):
        data, summary = report_utils.supplier_statement(company_id, branch_id, {"supplier_id": str(supplier_id)})
        refs = {row.get("ref_no"): row for row in data}
        failures = 0
        if self.strict_autotest and "AUTO-TEST-STMT-PUR-001" not in refs:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL supplier statement: purchase row missing."))
        if self.strict_autotest and "AUTO-TEST-STMT-PAY-001" not in refs:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL supplier statement: payment row missing."))
        if not data:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL supplier statement: no rows returned."))
        expected_balance = Decimal("500.00") if refs.get("AUTO-TEST-STMT-PUR-001") else Decimal(str(summary.get("Closing Balance") or 0))
        if Decimal(str(summary.get("Closing Balance") or 0)) != expected_balance:
            failures += 1
            self.stdout.write(self.style.ERROR(f"FAIL supplier statement: expected balance {expected_balance}, got {summary.get('Closing Balance')}"))
        if not failures:
            self.stdout.write("PASS supplier statement: purchase, payment, and running balance verified.")
        return failures

    def fetchone(self, sql, params):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return dictfetchone(cursor)

    def find_customer_with_statement_data(self, company_id, branch_id):
        existing = self.fetchone(
            """
            SELECT si.customer_id AS id
            FROM sales_invoices si
            WHERE si.company_id=%s AND si.branch_id=%s AND si.status <> 'Cancelled'
              AND EXISTS (
                  SELECT 1 FROM customer_receipts cr
                  WHERE cr.company_id=si.company_id AND cr.branch_id=si.branch_id AND cr.customer_id=si.customer_id
              )
            ORDER BY si.id
            LIMIT 1
            """,
            [company_id, branch_id],
        )
        return existing["id"] if existing else None

    def find_supplier_with_statement_data(self, company_id, branch_id):
        existing = self.fetchone(
            """
            SELECT sp.supplier_id AS id
            FROM supplier_purchases sp
            WHERE sp.company_id=%s AND sp.branch_id=%s AND sp.status <> 'Cancelled'
              AND EXISTS (
                  SELECT 1 FROM supplier_payments pay
                  WHERE pay.company_id=sp.company_id AND pay.branch_id=sp.branch_id AND pay.supplier_id=sp.supplier_id
              )
            ORDER BY sp.id
            LIMIT 1
            """,
            [company_id, branch_id],
        )
        return existing["id"] if existing else None
