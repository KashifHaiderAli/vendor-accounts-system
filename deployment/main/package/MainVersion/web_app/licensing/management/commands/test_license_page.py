from __future__ import annotations

from datetime import date

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory
from django.urls import reverse

from licensing.hardware_fingerprint import get_hardware_fingerprint
from licensing.license_utils import expiry_for_license, generate_license_key
from licensing.views import index
from settings_module.services import now_text


class Command(BaseCommand):
    help = "Tests the /license/ status and activation page without persisting test license records."

    def handle(self, *args, **options):
        self.factory = RequestFactory()
        self.fingerprint = get_hardware_fingerprint()
        self.results = []
        self.initial_count = self.scalar("SELECT COUNT(*) FROM license_records")
        try:
            with transaction.atomic():
                self.run_checks()
                transaction.set_rollback(True)
        except DatabaseError as exc:
            self.stdout.write(self.style.ERROR(f"FAIL: license page test could not run: {exc}"))
            return

        passed = sum(1 for row in self.results if row[1])
        failed = len(self.results) - passed
        for name, ok, actual in self.results:
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"{'PASS' if ok else 'FAIL'}: {name} - {actual}"))
        if self.scalar("SELECT COUNT(*) FROM license_records") != self.initial_count:
            failed += 1
            self.stdout.write(self.style.ERROR("FAIL: original license state was not preserved"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS: original license state preserved"))
        self.stdout.write(f"Summary: PASS={passed} FAIL={failed}")
        self.stdout.write(self.style.SUCCESS("PASS") if failed == 0 else self.style.ERROR("FAIL"))

    def run_checks(self):
        company_id = self.create_company()
        self.check_route()
        self.check_get_page(company_id)
        self.check_invalid_key_rejected(company_id)
        self.check_valid_activation_deactivates_previous(company_id)
        self.check_license_expired_route()

    def add(self, name, ok, actual):
        self.results.append((name, bool(ok), actual))

    def scalar(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            row = cursor.fetchone()
            return row[0] if row else None

    def create_company(self):
        now = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO companies (company_name, legal_name, is_active, created_at, updated_at) VALUES (%s, %s, 1, %s, %s)",
                ["AUTO-TEST License Page", "AUTO-TEST License Page", now, now],
            )
            cursor.execute("SELECT last_insert_rowid()")
            return cursor.fetchone()[0]

    def request(self, company_id, method="get", data=None):
        request = self.factory.post("/license/", data=data or {}) if method == "post" else self.factory.get("/license/")
        request.session = {
            "user_id": 1,
            "username": "AUTO-TEST",
            "company_id": company_id,
            "company_name": "AUTO-TEST License Page",
            "current_branch_id": None,
            "role_name": "Master Admin",
            "is_master_user": 1,
        }
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def check_route(self):
        self.add("/license/ route exists", reverse("licensing:index") == "/license/", reverse("licensing:index"))

    def check_get_page(self, company_id):
        response = index(self.request(company_id))
        content = response.content.decode("utf-8")
        placeholders = ["Business screens will be added in later phases", "New Entry", "Filter", "This route is styled"]
        ok = response.status_code == 200 and self.fingerprint in content and "Activate License" in content and "License History" in content and not any(text in content for text in placeholders)
        self.add("/license/ renders real page", ok, f"status={response.status_code}, fingerprint={'yes' if self.fingerprint in content else 'no'}")

    def check_invalid_key_rejected(self, company_id):
        before = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s", [company_id])
        data = {
            "action": "activate",
            "license_type": "Trial",
            "start_date": date.today().isoformat(),
            "expiry_date": expiry_for_license("Trial", date.today().isoformat())[0],
            "license_key": "INVALID-LICENSE-KEY",
        }
        response = index(self.request(company_id, "post", data))
        after = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s", [company_id])
        self.add("Invalid key rejected", response.status_code == 302 and before == after, f"before={before}, after={after}, status={response.status_code}")

    def check_valid_activation_deactivates_previous(self, company_id):
        start = date.today().isoformat()
        expiry = expiry_for_license("Trial", start)[0]
        old_key = generate_license_key("Trial", self.fingerprint, start)
        now = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO license_records (
                    company_id, branch_id, license_type, hardware_fingerprint, license_key,
                    issue_date, start_date, expiry_date, is_lifetime, is_active, remarks,
                    created_at, updated_at
                ) VALUES (%s, NULL, 'Trial', %s, %s, %s, %s, %s, 0, 1, 'old active', %s, %s)
                """,
                [company_id, self.fingerprint, old_key, start, start, expiry, now, now],
            )
        annual_expiry = expiry_for_license("Annual", start)[0]
        data = {
            "action": "activate",
            "license_type": "Annual",
            "start_date": start,
            "expiry_date": annual_expiry,
            "license_key": generate_license_key("Annual", self.fingerprint, start),
            "remarks": "AUTO-TEST activation",
        }
        response = index(self.request(company_id, "post", data))
        active_count = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s AND is_active=1", [company_id])
        annual_active = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s AND license_type='Annual' AND is_active=1", [company_id])
        content = index(self.request(company_id)).content.decode("utf-8")
        ok = response.status_code == 302 and active_count == 1 and annual_active == 1 and "AUTO-TEST activation" in content
        self.add("Valid activation deactivates previous active license", ok, f"active_count={active_count}, annual_active={annual_active}")

    def check_license_expired_route(self):
        self.add("/license-expired/ route works", reverse("license_expired") == "/license-expired/", reverse("license_expired"))
