from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from core import validators


class Command(BaseCommand):
    help = "Run lightweight master data validation checks without changing database schema or records."

    def handle(self, *args, **options):
        checks = [
            ("phone valid", self.check_phone_valid()),
            ("phone alphabet fail", self.check_phone_alpha_fail()),
            ("mobile valid", self.check_mobile_valid()),
            ("mobile alphabet fail", self.check_mobile_alpha_fail()),
            ("mobile too short fail", self.check_mobile_short_fail()),
            ("email valid", self.check_email_valid()),
            ("email invalid fail", self.check_invalid_email()),
            ("website valid", self.check_website_valid()),
            ("website invalid fail", self.check_website_invalid()),
            ("money valid", self.check_money_valid()),
            ("money alphabet fail", self.check_money_alpha_fail()),
            ("money negative fail", self.check_money_negative_fail()),
            ("percentage valid", self.check_percentage_valid()),
            ("percentage negative fail", self.check_percentage_negative_fail()),
            ("percentage over 100 fail", self.check_percentage_over_fail()),
            ("integer valid", self.check_integer_valid()),
            ("integer decimal fail", self.check_integer_decimal_fail()),
            ("integer negative fail", self.check_integer_negative_fail()),
            ("date valid", self.check_date_valid()),
            ("date invalid fail", self.check_date_invalid()),
            ("choice valid", self.check_choice_valid()),
            ("choice invalid fail", self.check_invalid_choice()),
            ("required text fail", self.check_required()),
            ("max length fail", self.check_max_length()),
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

    def check_phone_valid(self):
        _, error = validators.validate_phone("+92 300 1234567")
        return error is None

    def check_phone_alpha_fail(self):
        _, error = validators.validate_phone("phone123")
        return error is not None

    def check_mobile_valid(self):
        _, error = validators.validate_mobile("+923001234567")
        return error is None

    def check_mobile_alpha_fail(self):
        _, error = validators.validate_mobile("mobile123")
        return error is not None

    def check_mobile_short_fail(self):
        _, error = validators.validate_mobile("123")
        return error is not None

    def check_email_valid(self):
        value, error = validators.validate_email("INFO@EXAMPLE.COM")
        return error is None and value == "info@example.com"

    def check_invalid_email(self):
        _, error = validators.validate_email("not-an-email")
        return error == "Enter a valid email address."

    def check_website_valid(self):
        _, error = validators.validate_website("www.example.com")
        return error is None

    def check_website_invalid(self):
        _, error = validators.validate_website("example dot com")
        return error is not None

    def check_money_valid(self):
        value, error = validators.validate_money("123.45", "Amount")
        return error is None and str(value) == "123.45"

    def check_money_alpha_fail(self):
        _, error = validators.validate_money("abc", "Amount")
        return error is not None

    def check_money_negative_fail(self):
        _, error = validators.validate_money("-1", "Amount")
        return error == "Amount cannot be negative."

    def check_percentage_valid(self):
        _, error = validators.validate_percentage("17.5", "Tax Rate")
        return error is None

    def check_percentage_negative_fail(self):
        _, error = validators.validate_percentage("-1", "Tax Rate")
        return error == "Tax Rate cannot be negative."

    def check_percentage_over_fail(self):
        _, error = validators.validate_percentage("101", "Tax Rate")
        return error == "Tax Rate must be between 0 and 100."

    def check_integer_valid(self):
        value, error = validators.validate_integer("12", "Days")
        return error is None and value == 12

    def check_integer_decimal_fail(self):
        _, error = validators.validate_integer("1.5", "Days")
        return error == "Days must be a whole number."

    def check_integer_negative_fail(self):
        _, error = validators.validate_integer("-1", "Days", min_value=0)
        return error == "Days cannot be negative."

    def check_date_valid(self):
        value, error = validators.validate_date("2026-05-08", "Date")
        return error is None and str(value) == "2026-05-08"

    def check_date_invalid(self):
        _, error = validators.validate_date("2026-02-31", "Date")
        return error is not None

    def check_choice_valid(self):
        return validators.validate_choice("Debit", ["Debit", "Credit"], "Opening Balance Type") is None

    def check_invalid_choice(self):
        return validators.validate_choice("Sideways", ["Debit", "Credit"], "Opening Balance Type") is not None

    def check_max_length(self):
        _, error = validators.clean_text("abcdef", max_length=5, field_name="Code")
        return error == "Code cannot be longer than 5 characters."

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
