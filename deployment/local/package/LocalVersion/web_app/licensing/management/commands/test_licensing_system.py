from __future__ import annotations

from datetime import date, timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from licensing.hardware_fingerprint import get_hardware_fingerprint
from licensing.license_utils import expiry_for_license, generate_license_key
from licensing.middleware import LicenseValidationMiddleware, has_valid_license
from licensing.views import index as license_index
from settings_module.services import now_text


class Command(BaseCommand):
    help = "Safely tests license validation, middleware behavior, and audit logging without persisting test licenses."

    def handle(self, *args, **options):
        self.factory = RequestFactory()
        self.fingerprint = get_hardware_fingerprint()
        self.results = []
        self.initial_license_count = self.scalar("SELECT COUNT(*) FROM license_records")

        try:
            with transaction.atomic():
                self.run_tests()
                transaction.set_rollback(True)
        except DatabaseError as exc:
            self.stdout.write(self.style.ERROR(f"FAIL: licensing test could not run: {exc}"))
            return

        passed = sum(1 for item in self.results if item["status"] == "PASS")
        failed = sum(1 for item in self.results if item["status"] == "FAIL")
        warnings = sum(1 for item in self.results if item["status"] == "WARNING")

        for item in self.results:
            style = self.style.SUCCESS if item["status"] == "PASS" else self.style.ERROR
            if item["status"] == "WARNING":
                style = self.style.WARNING
            self.stdout.write(style(f"{item['status']}: {item['name']} - {item['actual']}"))

        final_count = self.scalar("SELECT COUNT(*) FROM license_records")
        if final_count != self.initial_license_count:
            self.results.append(
                {
                    "name": "License state restored",
                    "status": "FAIL",
                    "actual": f"license_records count changed from {self.initial_license_count} to {final_count}",
                }
            )
            failed += 1
        else:
            self.stdout.write(self.style.SUCCESS("PASS: original license state preserved"))

        self.stdout.write("")
        self.stdout.write(f"Summary: PASS={passed} FAIL={failed} WARNING={warnings}")
        if failed:
            self.stdout.write(self.style.ERROR("FAIL"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS"))

    def run_tests(self):
        self.check_valid_license()
        self.check_missing_license()
        self.check_expired_license()
        self.check_inactive_license()
        self.check_wrong_hardware()
        self.check_invalid_key()
        self.check_trial_valid()
        self.check_trial_expired()
        self.check_annual_valid()
        self.check_annual_expired()
        self.check_lifetime_license()
        self.check_license_page()
        self.check_middleware_policy()
        self.check_audit_log()

    def add_result(self, name, passed, actual, warning=False):
        self.results.append(
            {
                "name": name,
                "status": "WARNING" if warning else ("PASS" if passed else "FAIL"),
                "actual": actual,
            }
        )

    def scalar(self, sql, params=None):
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            row = cursor.fetchone()
            return row[0] if row else None

    def create_company(self, name):
        now = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO companies (company_name, legal_name, is_active, created_at, updated_at)
                VALUES (%s, %s, 1, %s, %s)
                """,
                [name, name, now, now],
            )
            cursor.execute("SELECT last_insert_rowid()")
            return cursor.fetchone()[0]

    def insert_license(self, company_id, license_type, start, expiry=None, is_lifetime=0, is_active=1, fingerprint=None, key=None):
        fingerprint = fingerprint or self.fingerprint
        if key is None:
            key = generate_license_key(license_type, fingerprint, start)
        now = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO license_records (
                    company_id, branch_id, license_type, hardware_fingerprint, license_key,
                    issue_date, start_date, expiry_date, is_lifetime, is_active, remarks,
                    created_at, updated_at
                ) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    license_type,
                    fingerprint,
                    key,
                    start,
                    start,
                    expiry,
                    is_lifetime,
                    is_active,
                    "AUTO-TEST license record, rolled back by test_licensing_system.",
                    now,
                    now,
                ],
            )

    def company_with_license(self, name, license_type, start, expiry=None, is_lifetime=0, is_active=1, fingerprint=None, key=None):
        company_id = self.create_company(name)
        self.insert_license(company_id, license_type, start, expiry, is_lifetime, is_active, fingerprint, key)
        return company_id

    def check_valid_license(self):
        today = date.today()
        expiry, is_lifetime = expiry_for_license("Annual", today.isoformat())
        company_id = self.company_with_license("AUTO-TEST Valid License", "Annual", today.isoformat(), expiry, is_lifetime)
        allowed = has_valid_license(company_id)
        response = self.middleware_response("/sales/quotations/", company_id)
        self.add_result("Valid license exists", allowed and response.status_code == 200, f"valid={allowed}, protected_status={response.status_code}")

    def check_missing_license(self):
        company_id = self.create_company("AUTO-TEST Missing License")
        allowed = has_valid_license(company_id)
        response = self.middleware_response("/sales/quotations/new/", company_id, method="post")
        self.add_result("Missing license simulation", (not allowed) and response.status_code == 302, f"valid={allowed}, protected_status={response.status_code}, location={response.get('Location', '')}")

    def check_expired_license(self):
        start = (date.today() - timedelta(days=60)).isoformat()
        expiry = (date.today() - timedelta(days=30)).isoformat()
        company_id = self.company_with_license("AUTO-TEST Expired License", "Trial", start, expiry)
        allowed = has_valid_license(company_id)
        self.add_result("Expired license simulation", not allowed, f"valid={allowed}")

    def check_inactive_license(self):
        today = date.today()
        expiry, is_lifetime = expiry_for_license("Annual", today.isoformat())
        company_id = self.company_with_license("AUTO-TEST Inactive License", "Annual", today.isoformat(), expiry, is_lifetime, is_active=0)
        allowed = has_valid_license(company_id)
        self.add_result("Inactive/locked license simulation", not allowed, f"valid={allowed}")

    def check_wrong_hardware(self):
        today = date.today()
        wrong_fingerprint = "WRONG-" + self.fingerprint
        expiry, is_lifetime = expiry_for_license("Annual", today.isoformat())
        company_id = self.company_with_license("AUTO-TEST Wrong Hardware", "Annual", today.isoformat(), expiry, is_lifetime, fingerprint=wrong_fingerprint)
        allowed = has_valid_license(company_id)
        self.add_result("Wrong hardware fingerprint simulation", not allowed, f"valid={allowed}")

    def check_invalid_key(self):
        today = date.today()
        expiry, is_lifetime = expiry_for_license("Annual", today.isoformat())
        company_id = self.company_with_license("AUTO-TEST Invalid Key", "Annual", today.isoformat(), expiry, is_lifetime, key="INVALID-LICENSE-KEY")
        allowed = has_valid_license(company_id)
        self.add_result("Invalid license key simulation", not allowed, f"valid={allowed}")

    def check_trial_valid(self):
        today = date.today()
        expiry, is_lifetime = expiry_for_license("Trial", today.isoformat())
        company_id = self.company_with_license("AUTO-TEST Valid Trial", "Trial", today.isoformat(), expiry, is_lifetime)
        allowed = has_valid_license(company_id)
        self.add_result("Trial license valid", allowed, f"valid={allowed}, expiry={expiry}")

    def check_trial_expired(self):
        start = (date.today() - timedelta(days=45)).isoformat()
        expiry = (date.today() - timedelta(days=15)).isoformat()
        company_id = self.company_with_license("AUTO-TEST Expired Trial", "Trial", start, expiry)
        allowed = has_valid_license(company_id)
        self.add_result("Trial license expired", not allowed, f"valid={allowed}, expiry={expiry}")

    def check_annual_valid(self):
        start = date.today().isoformat()
        expiry, is_lifetime = expiry_for_license("Annual", start)
        company_id = self.company_with_license("AUTO-TEST Valid Annual", "Annual", start, expiry, is_lifetime)
        allowed = has_valid_license(company_id)
        self.add_result("Annual license valid", allowed, f"valid={allowed}, expiry={expiry}")

    def check_annual_expired(self):
        start = (date.today() - timedelta(days=400)).isoformat()
        expiry = (date.today() - timedelta(days=35)).isoformat()
        company_id = self.company_with_license("AUTO-TEST Expired Annual", "Annual", start, expiry)
        allowed = has_valid_license(company_id)
        self.add_result("Annual license expired", not allowed, f"valid={allowed}, expiry={expiry}")

    def check_lifetime_license(self):
        start = (date.today() - timedelta(days=2000)).isoformat()
        company_id = self.company_with_license("AUTO-TEST Lifetime", "Lifetime", start, None, 1)
        allowed = has_valid_license(company_id)
        self.add_result("Lifetime license", allowed, f"valid={allowed}")

    def check_middleware_policy(self):
        company_id = self.create_company("AUTO-TEST Middleware Missing")
        protected = self.middleware_response("/reports/", company_id)
        license_page = self.middleware_response("/license/", company_id)
        expired_page = self.middleware_response("/license-expired/", company_id)
        login_page = self.middleware_response("/login/", company_id)
        static_file = self.middleware_response("/static/css/app.css", company_id)
        passed = protected.status_code == 302 and license_page.status_code == 200 and expired_page.status_code == 200 and login_page.status_code == 200 and static_file.status_code == 200
        actual = f"protected={protected.status_code}, license={license_page.status_code}, expired={expired_page.status_code}, login={login_page.status_code}, static={static_file.status_code}"
        self.add_result("License middleware policy", passed, actual)

    def check_license_page(self):
        company_id = self.create_company("AUTO-TEST License Page")
        get_response = license_index(self.view_request(company_id))
        content = get_response.content.decode("utf-8")
        page_ok = (
            reverse("licensing:index") == "/license/"
            and get_response.status_code == 200
            and self.fingerprint in content
            and "Activate License" in content
            and "License History" in content
            and "Business screens will be added in later phases" not in content
        )

        invalid_before = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s", [company_id])
        invalid_data = {
            "action": "activate",
            "license_type": "Trial",
            "start_date": date.today().isoformat(),
            "expiry_date": expiry_for_license("Trial", date.today().isoformat())[0],
            "license_key": "INVALID-LICENSE-KEY",
        }
        invalid_response = license_index(self.view_request(company_id, "post", invalid_data))
        invalid_after = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s", [company_id])

        start = date.today().isoformat()
        valid_data = {
            "action": "activate",
            "license_type": "Trial",
            "start_date": start,
            "expiry_date": expiry_for_license("Trial", start)[0],
            "license_key": generate_license_key("Trial", self.fingerprint, start),
            "remarks": "AUTO-TEST license page activation",
        }
        valid_response = license_index(self.view_request(company_id, "post", valid_data))
        active_count = self.scalar("SELECT COUNT(*) FROM license_records WHERE company_id=%s AND is_active=1", [company_id])

        passed = page_ok and invalid_response.status_code == 302 and invalid_before == invalid_after and valid_response.status_code == 302 and active_count == 1
        actual = f"page_ok={page_ok}, invalid_before={invalid_before}, invalid_after={invalid_after}, active_count={active_count}"
        self.add_result("/license/ page and activation", passed, actual)

    def check_audit_log(self):
        company_id = self.create_company("AUTO-TEST Audit License Failure")
        before = self.scalar("SELECT COUNT(*) FROM user_activity_log WHERE action_type='LICENSE_FAILURE'")
        self.middleware_response("/settings/company/", company_id)
        after = self.scalar("SELECT COUNT(*) FROM user_activity_log WHERE action_type='LICENSE_FAILURE'")
        self.add_result("Audit log records license failure", after > before, f"before={before}, after={after}")

    def middleware_response(self, path, company_id, method="get"):
        request = self.factory.post(path) if method.lower() == "post" else self.factory.get(path)
        request.session = {"company_id": company_id, "current_branch_id": None, "user_id": None, "username": "AUTO-TEST"}
        setattr(request, "_messages", FallbackStorage(request))
        middleware = LicenseValidationMiddleware(lambda req: HttpResponse("OK"))
        return middleware(request)

    def view_request(self, company_id, method="get", data=None):
        request = self.factory.post("/license/", data=data or {}) if method.lower() == "post" else self.factory.get("/license/")
        request.session = {
            "company_id": company_id,
            "company_name": "AUTO-TEST",
            "current_branch_id": None,
            "user_id": 1,
            "username": "AUTO-TEST",
            "role_name": "Master Admin",
            "is_master_user": 1,
        }
        setattr(request, "_messages", FallbackStorage(request))
        return request
