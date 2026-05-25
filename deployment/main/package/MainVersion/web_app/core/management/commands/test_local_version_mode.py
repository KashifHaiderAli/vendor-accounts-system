from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string

from core.edition_utils import database_file_name, env_tax_enabled, get_edition_name, is_tax_enabled
from sales.services import calculate_items as calculate_quotation_items


class Command(BaseCommand):
    help = "Verify LocalVersion non-tax mode behavior."

    def handle(self, *args, **options):
        checks = []
        checks.append(("ENABLE_TAX=False", not env_tax_enabled()))
        checks.append(("tax helper returns false", not is_tax_enabled()))
        checks.append(("edition is LocalVersion", get_edition_name() == "LocalVersion"))

        rows, totals = calculate_quotation_items(
            [{"description": "Local item", "quantity": "1", "rate": "1000", "discount_percent": "0", "discount_amount": "0", "tax_percent": "18"}],
            "tax_exclusive",
            None,
            None,
        )
        checks.append(("calculation tax_total zero", str(totals["tax_total"]) in {"0", "0.00"} and rows[0]["tax_amount"] == "0.00"))

        rendered_totals = render_to_string("partials/document_totals.html", {"subtotal": 1000, "discount_total": 50, "tax_total": 180, "grand_total": 950, "tax_enabled": False})
        checks.append(("print totals omit tax label", "Tax" not in rendered_totals and "Grand Total" in rendered_totals))

        checks.append(("local database file recognized", database_file_name() in {"vendor_accounts_local.db", "vendor_accounts.db", "vendor_accounts_main.db"}))

        try:
            call_command("check", verbosity=0)
            checks.append(("Django check", True))
        except Exception:
            checks.append(("Django check", False))

        failed = [label for label, ok in checks if not ok]
        for label, ok in checks:
            self.stdout.write(f"{'PASS' if ok else 'FAIL'} - {label}")
        if failed:
            raise CommandError("LocalVersion checks failed: " + ", ".join(failed))
        self.stdout.write(self.style.SUCCESS("PASS local version mode checks"))
