from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection

from accounts_module.accounting_utils import ensure_default_chart_of_accounts
from authentication.auth_utils import dictfetchall
from settings_module.services import now_text


CONTROL_ACCOUNT_NAMES = {
    "Assets",
    "Liabilities",
    "Equity",
    "Income",
    "Expenses",
    "Accounts Receivable",
    "Accounts Payable",
    "Office Expenses",
}

POSTING_ACCOUNT_NAMES = {
    "Cash",
    "Bank",
    "Input Tax Receivable",
    "Output Tax Payable",
    "Capital / Opening Balance",
    "Sales",
    "Service Income",
    "Purchases / Cost of Goods",
    "Sales Returns",
    "Purchase Returns",
}

LINKED_TABLES = [
    ("customers", "account_id"),
    ("suppliers", "account_id"),
    ("cash_bank_accounts", "account_id"),
    ("expense_heads", "account_id"),
]


class Command(BaseCommand):
    help = "Correct Chart of Accounts control/system flags without changing schema."

    def handle(self, *args, **options):
        try:
            self.fix_flags()
        except DatabaseError as exc:
            self.stdout.write(self.style.ERROR(f"FAIL: unable to update account flags: {exc}"))

    def fix_flags(self):
        summary = {
            "control_accounts_fixed": 0,
            "posting_accounts_fixed": 0,
            "linked_accounts_fixed": 0,
        }
        companies = self.rows("SELECT id FROM companies ORDER BY id")
        if not companies:
            self.stdout.write(self.style.ERROR("FAIL: no companies found."))
            return

        for company in companies:
            branches = self.rows("SELECT id FROM branches WHERE company_id=%s ORDER BY id", [company["id"]])
            for branch in branches:
                ensure_default_chart_of_accounts(company["id"], branch["id"])
                summary["control_accounts_fixed"] += self.fix_named_accounts(
                    company["id"],
                    branch["id"],
                    CONTROL_ACCOUNT_NAMES,
                    is_control=1,
                    is_system=1,
                )
                summary["posting_accounts_fixed"] += self.fix_named_accounts(
                    company["id"],
                    branch["id"],
                    POSTING_ACCOUNT_NAMES,
                    is_control=0,
                    is_system=1,
                )
                summary["linked_accounts_fixed"] += self.fix_linked_accounts(company["id"], branch["id"])

        self.stdout.write(f"control accounts fixed: {summary['control_accounts_fixed']}")
        self.stdout.write(f"posting accounts fixed: {summary['posting_accounts_fixed']}")
        self.stdout.write(f"linked accounts fixed: {summary['linked_accounts_fixed']}")
        self.stdout.write(self.style.SUCCESS("PASS: account flags corrected."))

    def fix_named_accounts(self, company_id, branch_id, names, is_control, is_system):
        fixed = 0
        timestamp = now_text()
        with connection.cursor() as cursor:
            for name in names:
                cursor.execute(
                    """
                    SELECT id, is_control_account, is_system_account
                    FROM accounts
                    WHERE company_id=%s
                      AND (branch_id=%s OR branch_id IS NULL)
                      AND lower(account_name)=lower(%s)
                    """,
                    [company_id, branch_id, name],
                )
                for account_id, current_control, current_system in cursor.fetchall():
                    if int(current_control or 0) == is_control and int(current_system or 0) == is_system:
                        continue
                    cursor.execute(
                        """
                        UPDATE accounts
                        SET is_control_account=%s,
                            is_system_account=%s,
                            updated_at=%s
                        WHERE id=%s
                        """,
                        [is_control, is_system, timestamp, account_id],
                    )
                    fixed += 1
        return fixed

    def fix_linked_accounts(self, company_id, branch_id):
        fixed = 0
        timestamp = now_text()
        with connection.cursor() as cursor:
            for table_name, account_field in LINKED_TABLES:
                if not self.table_exists(table_name):
                    continue
                cursor.execute(
                    f"""
                    SELECT DISTINCT {account_field}
                    FROM {table_name}
                    WHERE company_id=%s
                      AND branch_id=%s
                      AND {account_field} IS NOT NULL
                    """,
                    [company_id, branch_id],
                )
                account_ids = [row[0] for row in cursor.fetchall() if row[0]]
                for account_id in account_ids:
                    cursor.execute(
                        """
                        SELECT is_control_account, is_system_account
                        FROM accounts
                        WHERE id=%s AND company_id=%s AND (branch_id=%s OR branch_id IS NULL)
                        LIMIT 1
                        """,
                        [account_id, company_id, branch_id],
                    )
                    row = cursor.fetchone()
                    if not row:
                        continue
                    if int(row[0] or 0) == 0 and int(row[1] or 0) == 1:
                        continue
                    cursor.execute(
                        """
                        UPDATE accounts
                        SET is_control_account=0,
                            is_system_account=1,
                            updated_at=%s
                        WHERE id=%s
                        """,
                        [timestamp, account_id],
                    )
                    fixed += 1
        return fixed

    def table_exists(self, table_name):
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [table_name])
            return cursor.fetchone() is not None

    def rows(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchall(cursor)
