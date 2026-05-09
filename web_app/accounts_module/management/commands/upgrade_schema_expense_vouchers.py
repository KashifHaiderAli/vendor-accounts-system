from django.core.management.base import BaseCommand
from django.db import connection

from accounts_module.expense_schema import expense_voucher_schema_sql


class Command(BaseCommand):
    help = "Create expense voucher tables for existing SQLite databases using raw SQL."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expense_vouchers'")
            existed = cursor.fetchone() is not None
            for statement in expense_voucher_schema_sql():
                cursor.execute(statement)
        if existed:
            self.stdout.write(self.style.SUCCESS("PASS: expense_vouchers table already exists; indexes verified."))
        else:
            self.stdout.write(self.style.SUCCESS("PASS: expense_vouchers table created successfully."))
