from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from authentication.auth_utils import dictfetchone
from reports import report_utils
from reports.views import REPORTS


class Command(BaseCommand):
    help = "Run smoke checks for report query helpers without altering data."

    def handle(self, *args, **options):
        company = self.first_row("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
        branch = self.first_row("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id LIMIT 1", [company["id"]]) if company else None
        if not company or not branch:
            self.stdout.write(self.style.ERROR("FAIL: active company and branch are required."))
            return

        filters = {
            "date_from": "",
            "date_to": "",
            "q": "",
            "status": "",
            "customer_id": self.first_id("customers", company["id"], branch["id"]),
            "supplier_id": self.first_id("suppliers", company["id"], branch["id"]),
            "account_id": self.first_id("accounts", company["id"], branch["id"], allow_null_branch=True),
            "cash_bank_account_id": self.first_id("cash_bank_accounts", company["id"], branch["id"]),
            "item_service_id": self.first_id("item_services", company["id"], branch["id"]),
            "expense_head_id": self.first_id("expense_heads", company["id"], branch["id"]),
            "payment_mode": "",
            "invoice_type": "",
            "user_id": self.first_id("users", company["id"], branch["id"], branch_field=None),
            "action": "",
            "module": "",
        }

        failures = 0
        for key, definition in REPORTS.items():
            try:
                rows, summary = definition["function"](company["id"], branch["id"], filters)
                self.stdout.write(f"{key}: rows={len(rows)} summary={summary}")
            except Exception as exc:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {key}: {exc}"))

        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} report query check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: report queries ready."))

    def first_row(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchone(cursor)

    def first_id(self, table, company_id, branch_id, allow_null_branch=False, branch_field="branch_id"):
        if not report_utils.table_exists(table):
            return ""
        if branch_field is None:
            branch_clause = "1=1"
            params = [company_id]
        else:
            branch_clause = f"({branch_field}=%s OR {branch_field} IS NULL)" if allow_null_branch else f"{branch_field}=%s"
            params = [company_id, branch_id]
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM {table} WHERE company_id=%s AND {branch_clause} ORDER BY id LIMIT 1",
                params,
            )
            found = cursor.fetchone()
        return str(found[0]) if found else ""
