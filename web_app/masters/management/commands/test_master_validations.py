from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from core import validators


class Command(BaseCommand):
    help = "Run lightweight master data validation checks without changing database schema or records."

    def handle(self, *args, **options):
        checks = [
            ("required field error", self.check_required()),
            ("negative decimal error", self.check_negative_decimal()),
            ("invalid email error", self.check_invalid_email()),
            ("tax rate over 100 error", self.check_tax_rate()),
            ("invalid choice error", self.check_invalid_choice()),
            ("duplicate code detection", self.check_duplicate_code()),
        ]

        failed = False
        for label, result in checks:
            if result:
                self.stdout.write(self.style.SUCCESS(f"PASS: {label}"))
            else:
                failed = True
                self.stdout.write(self.style.ERROR(f"FAIL: {label}"))

        if failed:
            self.stdout.write(self.style.ERROR("FAIL"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("PASS"))

    def check_required(self):
        return validators.validate_required("", "Customer Code") == "Customer Code is required."

    def check_negative_decimal(self):
        _, error = validators.validate_decimal("-1", "Credit Limit", min_value=0)
        return error == "Credit Limit cannot be negative."

    def check_invalid_email(self):
        return validators.validate_email("not-an-email") == "Enter a valid email address."

    def check_tax_rate(self):
        _, error = validators.validate_decimal("101", "Tax Rate", min_value=0, max_value=100)
        return error == "Tax Rate must be between 0 and 100."

    def check_invalid_choice(self):
        return validators.validate_choice("Sideways", ["Debit", "Credit"], "Opening Balance Type") is not None

    def check_duplicate_code(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account_code, company_id, branch_id
                FROM accounts
                WHERE account_code IS NOT NULL
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        if not row:
            self.stdout.write("SKIP: duplicate code detection (no account rows found)")
            return True
        account_code, company_id, branch_id = row
        error = validators.validate_unique_code(
            connection,
            "accounts",
            "account_code",
            account_code,
            company_id,
            branch_id,
        )
        return error is not None
