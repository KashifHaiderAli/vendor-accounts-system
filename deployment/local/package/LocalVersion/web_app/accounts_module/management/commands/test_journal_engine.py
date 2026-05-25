from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection

from accounts_module.accounting_engine import AccountingError, create_journal_entry
from accounts_module.accounting_utils import (
    ensure_default_chart_of_accounts,
    get_system_account,
    log_accounting_activity,
    today_iso,
)
from authentication.auth_utils import dictfetchone


class Command(BaseCommand):
    help = "Developer-only smoke test for the hidden journal engine."

    def handle(self, *args, **options):
        try:
            context = self.get_context()
            if not context:
                self.stdout.write(self.style.ERROR("FAIL: Missing company, branch, or master admin user."))
                return
            company_id = context["company_id"]
            branch_id = context["branch_id"]
            user_id = context["user_id"]

            existing = self.get_existing_test_entry(company_id, branch_id)
            if existing:
                self.stdout.write(f"Existing test journal entry id: {existing['id']}")
                self.stdout.write(self.style.SUCCESS("PASS"))
                return

            created_accounts = ensure_default_chart_of_accounts(company_id, branch_id)
            if created_accounts:
                log_accounting_activity(
                    company_id,
                    branch_id,
                    user_id,
                    "ENSURE_CHART",
                    None,
                    "Ensured default chart of accounts from test_journal_engine.",
                )

            cash = get_system_account(company_id, branch_id, "Cash")
            capital = get_system_account(company_id, branch_id, "Capital / Opening Balance")
            if not cash or not capital:
                raise AccountingError("Required Cash or Capital account is missing.")

            journal_id = create_journal_entry(
                company_id,
                branch_id,
                today_iso(),
                "test_journal_engine",
                None,
                "Developer journal engine smoke test",
                [
                    {
                        "account_id": cash["id"],
                        "debit": Decimal("100.00"),
                        "credit": Decimal("0.00"),
                        "description": "Test debit",
                    },
                    {
                        "account_id": capital["id"],
                        "debit": Decimal("0.00"),
                        "credit": Decimal("100.00"),
                        "description": "Test credit",
                    },
                ],
                created_by_id=user_id,
            )
            self.stdout.write(f"Created journal entry id: {journal_id}")
            self.stdout.write(self.style.SUCCESS("PASS"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"FAIL: {exc}"))

    def get_context(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id AS company_id FROM companies ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            cursor.execute("SELECT id AS branch_id FROM branches WHERE is_active = 1 ORDER BY is_head_office DESC, id LIMIT 1")
            branch = dictfetchone(cursor)
            cursor.execute("SELECT id AS user_id FROM users WHERE is_master_user = 1 AND is_active = 1 ORDER BY id LIMIT 1")
            user = dictfetchone(cursor)
        if not company or not branch or not user:
            return None
        return {**company, **branch, **user}

    def get_existing_test_entry(self, company_id, branch_id):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM journal_entries
                WHERE company_id = %s
                  AND branch_id = %s
                  AND reference_type = 'test_journal_engine'
                ORDER BY id DESC
                LIMIT 1
                """,
                [company_id, branch_id],
            )
            return dictfetchone(cursor)
