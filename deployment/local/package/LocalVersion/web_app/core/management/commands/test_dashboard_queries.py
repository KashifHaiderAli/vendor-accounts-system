from django.core.management.base import BaseCommand
from django.test import RequestFactory

from core.dashboard_utils import dashboard_data


class Command(BaseCommand):
    help = "Run dashboard aggregate queries and print KPI values."

    def handle(self, *args, **options):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = cursor.fetchone()
            cursor.execute("SELECT id FROM branches WHERE is_active=1 ORDER BY id LIMIT 1")
            branch = cursor.fetchone()
            cursor.execute("SELECT id, full_name, role_id FROM users WHERE is_active=1 ORDER BY id LIMIT 1")
            user = cursor.fetchone()
        if not company or not branch or not user:
            self.stdout.write(self.style.ERROR("FAIL: company, branch, and user are required."))
            return
        request = RequestFactory().get("/")
        request.session = {"company_id": company[0], "current_branch_id": branch[0], "user_id": user[0], "full_name": user[1], "role_id": user[2], "is_master_user": 1}
        data = dashboard_data(request)
        for card in data["dashboard_cards"]:
            self.stdout.write(f"{card['label']}: {card['value']}")
        self.stdout.write(self.style.SUCCESS("PASS: dashboard queries completed"))
