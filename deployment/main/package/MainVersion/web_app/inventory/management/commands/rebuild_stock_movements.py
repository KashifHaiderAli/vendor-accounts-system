from django.core.management.base import BaseCommand

from core.inventory_utils import rebuild_stock_movements_from_transactions
from authentication.auth_utils import dictfetchone
from django.db import connection


class Command(BaseCommand):
    help = "Rebuild quantity-only stock movements from existing business transactions."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Clear existing stock movements before rebuilding.")

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            cursor.execute("SELECT * FROM users WHERE is_master_user=1 AND is_active=1 ORDER BY id LIMIT 1")
            user = dictfetchone(cursor)
        if not company:
            self.stdout.write(self.style.ERROR("FAIL: active company is required."))
            return
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY id", [company["id"]])
            branches = cursor.fetchall()
        if not branches:
            self.stdout.write(self.style.ERROR("FAIL: active branch is required."))
            return
        totals = {}
        for branch in branches:
            summary = rebuild_stock_movements_from_transactions(company["id"], branch[0], user["id"] if user else None, reset=options["reset"])
            for key, value in summary.items():
                totals[key] = totals.get(key, 0) + value
        for key in sorted(totals):
            self.stdout.write(f"{key}: {totals[key]}")
        self.stdout.write(self.style.SUCCESS("PASS: stock movements rebuilt"))
