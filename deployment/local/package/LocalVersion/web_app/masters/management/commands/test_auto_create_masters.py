from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from masters import auto_create
from sales import invoice_services


class Command(BaseCommand):
    help = "Smoke-test confirmed auto creation of customers, suppliers, and items from transaction forms."

    def handle(self, *args, **options):
        company_id, branch_id, user_id = self.scope()
        marker = "AUTO-TEST Auto Create"

        with transaction.atomic():
            sales_data = {
                "customer_mode": "new",
                "customer_id": "",
                "customer_name": f"{marker} Customer",
                "items": [
                    {"item_service_id": "", "description": f"{marker} Sales Item", "rate": "1234.50"},
                    {"item_service_id": "", "description": f"{marker} Sales Item", "rate": "1234.50"},
                ],
            }
            errors, _, created = auto_create.resolve_sales_customer_and_items(
                sales_data.copy(),
                company_id,
                branch_id,
                user_id,
                {},
                "auto-create test",
            )
            self.assert_true("customer_id" in errors and "items" in errors, "missing confirmation blocks sales auto-create")
            self.assert_true(not created, "missing confirmation creates nothing")

            errors, resolved, created = auto_create.resolve_sales_customer_and_items(
                sales_data,
                company_id,
                branch_id,
                user_id,
                {"auto_create_customer_confirmed": "1", "auto_create_items_confirmed": "1"},
                "auto-create test",
            )
            self.assert_true(not errors, "confirmed sales auto-create has no errors")
            self.assert_true(resolved.get("customer_id"), "confirmed customer id populated")
            self.assert_true(all(row.get("item_service_id") for row in resolved["items"]), "confirmed sales item ids populated")
            self.assert_equal(len([row["item_service_id"] for row in resolved["items"]]), 2, "two sales rows retained")
            self.assert_equal(len(set(row["item_service_id"] for row in resolved["items"])), 1, "duplicate typed sales item reused")
            self.assert_true(any(row["type"] == "customer" for row in created), "customer creation recorded")
            self.assert_true(any(row["type"] == "item" for row in created), "sales item creation recorded")
            self.assert_money("item_services", resolved["items"][0]["item_service_id"], "default_sale_rate", "1234.50")

            duplicate_errors, duplicate_resolved, duplicate_created = auto_create.resolve_sales_customer_and_items(
                {
                    "customer_mode": "new",
                    "customer_id": "",
                    "customer_name": f"  {marker} Customer  ",
                    "items": [{"item_service_id": "", "description": f"{marker} Sales Item", "rate": "9999.00"}],
                },
                company_id,
                branch_id,
                user_id,
                {},
                "auto-create test",
            )
            self.assert_true(not duplicate_errors, "existing sales masters resolve without confirmation")
            self.assert_equal(str(duplicate_resolved["customer_id"]), str(resolved["customer_id"]), "existing customer reused")
            self.assert_true(not duplicate_created, "existing sales masters not duplicated")

            purchase_data = {
                "supplier_id": "",
                "supplier_name": f"{marker} Supplier",
                "items": [{"item_service_id": "", "description": f"{marker} Purchase Item", "purchase_rate": "765.25"}],
            }
            errors, _, created = auto_create.resolve_purchase_supplier_and_items(
                purchase_data.copy(),
                company_id,
                branch_id,
                user_id,
                {},
                "auto-create test",
            )
            self.assert_true("supplier_id" in errors and "items" in errors, "missing confirmation blocks purchase auto-create")
            self.assert_true(not created, "missing purchase confirmation creates nothing")

            errors, purchase_resolved, created = auto_create.resolve_purchase_supplier_and_items(
                purchase_data,
                company_id,
                branch_id,
                user_id,
                {"auto_create_supplier_confirmed": "1", "auto_create_items_confirmed": "1"},
                "auto-create test",
            )
            self.assert_true(not errors, "confirmed purchase auto-create has no errors")
            self.assert_true(purchase_resolved.get("supplier_id"), "confirmed supplier id populated")
            self.assert_true(purchase_resolved["items"][0].get("item_service_id"), "confirmed purchase item id populated")
            self.assert_true(any(row["type"] == "supplier" for row in created), "supplier creation recorded")
            self.assert_true(any(row["type"] == "item" for row in created), "purchase item creation recorded")
            self.assert_money("item_services", purchase_resolved["items"][0]["item_service_id"], "default_purchase_rate", "765.25")

            invoice_errors, invoice_data = invoice_services.validate_and_calculate(
                {
                    "invoice_no": "AUTO-TEST-INVOICE-MANUAL-ITEM",
                    "invoice_date": "2026-01-01",
                    "invoice_type": "cash_memo",
                    "customer_id": resolved["customer_id"],
                    "delivery_challan_id": "",
                    "confirmation_id": "",
                    "po_number": "",
                    "payment_terms_id": "",
                    "due_date": "",
                    "remarks": "",
                    "status": "Draft",
                    "items": [
                        {
                            "item_service_id": "",
                            "description": f"{marker} Invoice Manual Item",
                            "quantity": "1",
                            "rate": "100",
                            "discount_percent": "0",
                            "discount_amount": "0",
                            "tax_percent": "0",
                        }
                    ],
                },
                company_id,
                branch_id,
            )
            self.assert_true("items" in invoice_errors, "invoice manual item is blocked")
            self.assert_true(
                invoice_data["items"][0]["errors"].get("item_service_id", "").startswith("Invoice item must be selected"),
                "invoice item validation explains inventory master requirement",
            )
            self.assert_missing_item(company_id, branch_id, f"{marker} Invoice Manual Item", "invoice validation did not create item")

            transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("PASS: auto-create confirmation, duplicate prevention, and default rates verified."))

    def scope(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = cursor.fetchone()
            if not company:
                raise CommandError("No active company found.")
            cursor.execute("SELECT id FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company[0]])
            branch = cursor.fetchone()
            if not branch:
                raise CommandError("No active branch found.")
            cursor.execute("SELECT id FROM users WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company[0]])
            user = cursor.fetchone()
            if not user:
                raise CommandError("No active user found.")
        return company[0], branch[0], user[0]

    def assert_true(self, condition, label):
        if not condition:
            raise CommandError(f"FAIL: {label}")
        self.stdout.write(f"PASS: {label}")

    def assert_equal(self, actual, expected, label):
        if actual != expected:
            raise CommandError(f"FAIL: {label} ({actual!r} != {expected!r})")
        self.stdout.write(f"PASS: {label}")

    def assert_money(self, table, record_id, field, expected):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {field} FROM {table} WHERE id=%s", [record_id])
            row = cursor.fetchone()
        self.assert_equal(f"{float(row[0] or 0):.2f}", expected, f"{field} saved as {expected}")

    def assert_missing_item(self, company_id, branch_id, item_name, label):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM item_services WHERE company_id=%s AND branch_id=%s AND lower(trim(item_name))=lower(trim(%s)) LIMIT 1",
                [company_id, branch_id, item_name],
            )
            row = cursor.fetchone()
        if row:
            raise CommandError(f"FAIL: {label}")
        self.stdout.write(f"PASS: {label}")
