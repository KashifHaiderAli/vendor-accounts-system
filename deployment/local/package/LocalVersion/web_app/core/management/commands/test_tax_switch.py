from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory
from unittest.mock import patch

from core.edition_utils import can_change_tax_enabled, is_tax_enabled
from sales.services import calculate_items as calculate_quotation_items
from sales.invoice_services import calculate_items as calculate_invoice_items


class Command(BaseCommand):
    help = "Verify edition tax switch behavior without changing schema."

    def handle(self, *args, **options):
        checks = []
        factory = RequestFactory()
        admin_request = factory.get("/")
        admin_request.session = {"username": "admin"}
        other_request = factory.get("/")
        other_request.session = {"username": "admin2"}
        checks.append(("admin user can change switch", can_change_tax_enabled(admin_request)))
        checks.append(("other user cannot change switch", not can_change_tax_enabled(other_request)))

        with patch.dict("os.environ", {"ENABLE_TAX": "False"}):
            checks.append(("ENABLE_TAX=False forces tax off", not is_tax_enabled()))
            quotation_rows, quotation_totals = calculate_quotation_items(
                [{"description": "Test", "quantity": "1", "rate": "1000", "discount_percent": "0", "discount_amount": "0", "tax_percent": "18"}],
                "tax_exclusive",
                None,
                None,
            )
            invoice_rows, _, invoice_totals = calculate_invoice_items(
                [{"description": "Test", "quantity": "1", "rate": "1000", "discount_percent": "0", "discount_amount": "0", "tax_percent": "18"}],
                None,
                None,
            )
            checks.append(("quotation tax forced zero", str(quotation_totals["tax_total"]) in {"0.00", "0"} and quotation_rows[0]["tax_percent"] == "0.00"))
            checks.append(("invoice tax forced zero", str(invoice_totals["tax_total"]) in {"0.00", "0"} and invoice_rows[0]["tax_percent"] == "0.00"))

        failed = [label for label, ok in checks if not ok]
        for label, ok in checks:
            self.stdout.write(f"{'PASS' if ok else 'FAIL'} - {label}")
        if failed:
            raise CommandError("Tax switch checks failed: " + ", ".join(failed))
        self.stdout.write(self.style.SUCCESS("PASS tax switch checks"))
