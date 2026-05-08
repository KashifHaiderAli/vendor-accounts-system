from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection


QUOTATION_CUSTOMER_COLUMNS = [
    ("customer_name", "TEXT"),
    ("customer_phone", "TEXT"),
    ("customer_mobile", "TEXT"),
    ("customer_email", "TEXT"),
    ("customer_address", "TEXT"),
    ("customer_ntn", "TEXT"),
    ("customer_strn", "TEXT"),
    ("is_customer_saved", "INTEGER NOT NULL DEFAULT 0"),
]


class Command(BaseCommand):
    help = "Add quotation customer snapshot fields to an existing DB App SQLite database."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(quotations)")
            existing = {row[1] for row in cursor.fetchall()}
            for column_name, column_type in QUOTATION_CUSTOMER_COLUMNS:
                if column_name in existing:
                    self.stdout.write(self.style.SUCCESS(f"PASS: quotations.{column_name} already exists"))
                    continue
                cursor.execute(f"ALTER TABLE quotations ADD COLUMN {column_name} {column_type}")
                self.stdout.write(self.style.SUCCESS(f"PASS: added quotations.{column_name}"))
            cursor.execute(
                """
                UPDATE quotations
                SET customer_name = COALESCE(NULLIF(customer_name, ''), (
                        SELECT company_name FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_phone = COALESCE(NULLIF(customer_phone, ''), (
                        SELECT phone FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_mobile = COALESCE(NULLIF(customer_mobile, ''), (
                        SELECT mobile FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_email = COALESCE(NULLIF(customer_email, ''), (
                        SELECT email FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_address = COALESCE(NULLIF(customer_address, ''), (
                        SELECT address FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_ntn = COALESCE(NULLIF(customer_ntn, ''), (
                        SELECT ntn FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    customer_strn = COALESCE(NULLIF(customer_strn, ''), (
                        SELECT strn FROM customers WHERE customers.id = quotations.customer_id
                    )),
                    is_customer_saved = 1
                WHERE customer_id IS NOT NULL
                """
            )
            self.stdout.write(self.style.SUCCESS("PASS: existing linked quotations refreshed with customer snapshots"))
        self.stdout.write(self.style.SUCCESS("PASS: quotation customer fields are ready"))
