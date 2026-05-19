from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import get_template


DOCUMENT_PRINT_TEMPLATES = [
    "sales/quotation_print.html",
    "sales/delivery_challan_print.html",
    "sales/invoice_print_preprinted.html",
    "sales/invoice_print_digital.html",
    "sales/receipt_print.html",
    "sales/sales_return_print.html",
    "sales/confirmation_print.html",
    "purchases/supplier_purchase_print.html",
    "purchases/supplier_payment_print.html",
    "purchases/purchase_return_print.html",
    "accounts_module/expense_voucher_print.html",
    "services/contract_print.html",
    "reports/print_report.html",
]

ITEM_TABLE_PRINT_TEMPLATES = [
    "sales/quotation_print.html",
    "sales/invoice_print_preprinted.html",
    "sales/delivery_challan_print.html",
    "sales/sales_return_print.html",
    "purchases/supplier_purchase_print.html",
    "purchases/purchase_return_print.html",
]


class Command(BaseCommand):
    help = "Check business print templates and compact A4 print stylesheet."

    def handle(self, *args, **options):
        failures = []
        base_dir = Path(settings.BASE_DIR)
        print_css = base_dir / "static" / "css" / "print.css"

        if not print_css.exists():
            failures.append("static/css/print.css is missing.")
        else:
            css = print_css.read_text(encoding="utf-8")
            required_css = ["@page", "size: A4", "margin: 8mm", ".print-footer", ".print-table"]
            for marker in required_css:
                if marker not in css:
                    failures.append(f"print.css is missing `{marker}`.")

        for template_name in DOCUMENT_PRINT_TEMPLATES:
            try:
                get_template(template_name)
            except Exception as exc:
                failures.append(f"{template_name} template error: {exc}")
                continue

            path = base_dir / "templates" / template_name
            if not path.exists():
                failures.append(f"{template_name} file is missing.")
                continue
            content = path.read_text(encoding="utf-8")
            if "css/print.css" not in content and template_name != "sales/invoice_print_digital.html":
                failures.append(f"{template_name} does not reference css/print.css.")
            if template_name != "reports/print_report.html" and "print_footer.html" not in content and template_name != "sales/invoice_print_digital.html":
                failures.append(f"{template_name} does not include the shared print footer.")

        for template_name in ITEM_TABLE_PRINT_TEMPLATES:
            path = base_dir / "templates" / template_name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            if "<th" in content and ("Tax</th>" in content or "Tax %" in content or "tax_amount" in content):
                failures.append(f"{template_name} appears to show item-row tax columns.")

        partials = [
            base_dir / "templates" / "partials" / "print_header.html",
            base_dir / "templates" / "partials" / "print_footer.html",
            base_dir / "templates" / "partials" / "document_totals.html",
        ]
        for partial in partials:
            if not partial.exists():
                failures.append(f"{partial.relative_to(base_dir)} is missing.")

        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"FAIL: {failure}"))
            self.stdout.write(self.style.ERROR(f"FAIL: {len(failures)} print template check(s) failed."))
            return

        self.stdout.write(self.style.SUCCESS("PASS: print templates ready."))
