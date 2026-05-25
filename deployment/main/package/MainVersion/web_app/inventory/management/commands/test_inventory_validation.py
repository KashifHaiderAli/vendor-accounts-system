from django.core.management.base import BaseCommand
from django.db import connection, transaction

from authentication.auth_utils import dictfetchone
from core.inventory_utils import (
    InventoryError,
    create_stock_movement,
    get_available_stock,
    inventory_ready,
    reverse_stock_movements,
    validate_available_stock,
)
from settings_module.services import now_text


class RollbackInventoryValidation(Exception):
    pass


class Command(BaseCommand):
    help = "Run lightweight inventory validation checks against a rolled-back test transaction."

    def handle(self, *args, **options):
        if not inventory_ready():
            self.stdout.write(self.style.ERROR("FAIL: run upgrade_schema_inventory first."))
            return
        company, branch, user, product, service = self.bootstrap()
        if not all([company, branch, user, product, service]):
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, user, product, and service are required."))
            return
        try:
            with transaction.atomic():
                today = now_text()[:10]
                suffix = now_text().replace("-", "").replace(":", "").replace(" ", "")
                create_stock_movement(company["id"], branch["id"], product["id"], today, "purchase_in", "inventory_test_purchase", 900001, f"INV-TST-{suffix}", 5, 0, 100, "Inventory validation test", user["id"])
                self.assert_stock(company, branch, product, "after purchase", "5.00")
                create_stock_movement(company["id"], branch["id"], product["id"], today, "delivery_out", "inventory_test_dc", 900002, f"INV-TST-{suffix}", 0, 3, 100, "Inventory validation test", user["id"])
                self.assert_stock(company, branch, product, "after dc", "2.00")
                self.expect_error(lambda: validate_available_stock(company["id"], branch["id"], product["id"], 3, "test over issue"), "over issue blocked")
                create_stock_movement(company["id"], branch["id"], product["id"], today, "sales_return_in", "inventory_test_sales_return", 900003, f"INV-TST-{suffix}", 1, 0, 100, "Inventory validation test", user["id"])
                self.assert_stock(company, branch, product, "after sales return", "3.00")
                create_stock_movement(company["id"], branch["id"], product["id"], today, "purchase_return_out", "inventory_test_purchase_return", 900004, f"INV-TST-{suffix}", 0, 2, 100, "Inventory validation test", user["id"])
                self.assert_stock(company, branch, product, "after purchase return", "1.00")
                self.expect_error(lambda: validate_available_stock(company["id"], branch["id"], product["id"], 2, "test purchase return"), "over purchase return blocked")
                create_stock_movement(company["id"], branch["id"], product["id"], today, "invoice_out", "inventory_test_invoice", 900005, f"INV-TST-{suffix}", 0, 1, 100, "Inventory validation test", user["id"])
                self.assert_stock(company, branch, product, "after direct invoice", "0.00")
                validate_available_stock(company["id"], branch["id"], service["id"], 999, "service no stock")
                reverse_stock_movements("inventory_test_dc", 900002, "Inventory validation reversal", user["id"])
                self.assert_stock(company, branch, product, "after dc cancel reversal", "3.00")
                self.expect_error(lambda: reverse_stock_movements("inventory_test_purchase", 900001, "Inventory validation reversal", user["id"]), "purchase cancel consumed blocked")
                raise RollbackInventoryValidation()
        except RollbackInventoryValidation:
            pass
        self.stdout.write(self.style.SUCCESS("PASS: inventory validation checks passed"))

    def bootstrap(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company["id"]] if company else [])
            branch = dictfetchone(cursor)
            cursor.execute("SELECT * FROM users WHERE is_active=1 ORDER BY id LIMIT 1")
            user = dictfetchone(cursor)
            cursor.execute("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s AND lower(COALESCE(item_type,'')) <> 'service' ORDER BY id LIMIT 1", [company["id"], branch["id"]] if company and branch else [])
            product = dictfetchone(cursor)
            cursor.execute("SELECT * FROM item_services WHERE company_id=%s AND branch_id=%s AND lower(COALESCE(item_type,'')) = 'service' ORDER BY id LIMIT 1", [company["id"], branch["id"]] if company and branch else [])
            service = dictfetchone(cursor)
        return company, branch, user, product, service

    def assert_stock(self, company, branch, product, label, expected):
        actual = get_available_stock(company["id"], branch["id"], product["id"])
        if str(actual) != expected:
            raise AssertionError(f"{label}: expected {expected}, got {actual}")
        self.stdout.write(f"PASS: {label} = {actual}")

    def expect_error(self, func, label):
        try:
            func()
        except InventoryError:
            self.stdout.write(f"PASS: {label}")
            return
        raise AssertionError(f"FAIL: {label}")
