from __future__ import annotations

from reports.management.commands.test_reports_routes import Command as RoutesCommand


class Command(RoutesCommand):
    help = "Verify the reports index and group submenu pages render the expected visible labels."

    FORBIDDEN_FILTERS = {
        "reports:customer_statement": ["Supplier", "Item / Service", "Expense Head", "Account", "Cash / Bank", "User", "Reference Type", "Action", "Module"],
        "reports:customer_ledger": ["Supplier", "Item / Service", "Expense Head", "Account", "Cash / Bank", "User", "Reference Type", "Action", "Module"],
        "reports:supplier_statement": ["Customer", "Item / Service", "Expense Head", "Account", "Cash / Bank", "User", "Reference Type", "Action", "Module"],
        "reports:supplier_ledger": ["Customer", "Item / Service", "Expense Head", "Account", "Cash / Bank", "User", "Reference Type", "Action", "Module"],
        "reports:item_history": ["Customer", "Supplier", "Expense Head", "Account", "Cash / Bank", "User", "Action", "Module"],
        "reports:account_ledger": ["Customer", "Supplier", "Item / Service", "Expense Head", "Cash / Bank", "User", "Action", "Module"],
    }

    def handle(self, *args, **options):
        context = self.get_login_context()
        if not context:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required."))
            return
        failures = 0
        for name in self.CONTENT_CHECKS:
            response = self.call_url(self.reverse_name(name), context)
            if response.status_code >= 400:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {name}: status {response.status_code}"))
                continue
            self.stdout.write(f"PASS {name}: status {response.status_code}")
            failures += self.check_content(name, response)
            failures += self.check_forbidden_filters(name, response)
        failures += self.check_filter_links_preserve_query(context)
        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} report UI check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: report UI submenus ready."))

    def reverse_name(self, name):
        from django.urls import reverse

        return reverse(name)

    def check_forbidden_filters(self, route_name, response):
        forbidden = self.FORBIDDEN_FILTERS.get(route_name)
        if not forbidden:
            return 0
        content = response.content.decode("utf-8", errors="ignore")
        leaked = [label for label in forbidden if f">{label}<" in content or f">{label}</label>" in content]
        if leaked:
            self.stdout.write(self.style.ERROR(f"FAIL {route_name}: irrelevant filters visible: {', '.join(leaked)}"))
            return 1
        self.stdout.write(f"PASS {route_name}: irrelevant filters hidden")
        return 0

    def check_filter_links_preserve_query(self, context):
        from django.urls import reverse

        response = self.call_url(reverse("reports:customer_statement") + "?customer_id=5&date_from=2026-05-01&date_to=2026-05-31", context)
        content = response.content.decode("utf-8", errors="ignore")
        required = [
            "customer_id=5",
            "date_from=2026-05-01",
            "date_to=2026-05-31",
            "export=csv",
            "print=1&logo=0",
            "print=1&logo=1",
        ]
        missing = [value for value in required if value not in content]
        if missing:
            self.stdout.write(self.style.ERROR(f"FAIL reports:customer_statement: filter action links lost query values: {', '.join(missing)}"))
            return 1
        self.stdout.write("PASS reports:customer_statement: CSV/print links preserve filters")
        return 0
