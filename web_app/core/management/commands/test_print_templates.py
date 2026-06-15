from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from core.format_utils import format_amount, format_quantity


DOCUMENT_PRINT_TEMPLATES = [
    "sales/quotation_print.html",
    "sales/quotation_print_classic.html",
    "sales/quotation_print_letterhead.html",
    "sales/delivery_challan_print.html",
    "sales/invoice_print_preprinted.html",
    "sales/invoice_print_digital.html",
    "sales/invoice_print_classic.html",
    "sales/invoice_print_letterhead.html",
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
        digital_signature_dir = base_dir / "DigitalSignature"

        if not print_css.exists():
            failures.append("static/css/print.css is missing.")
        else:
            css = print_css.read_text(encoding="utf-8")
            required_css = [
                "@page",
                "size: A4",
                "margin: 8mm",
                ".print-footer",
                ".print-table",
                ".print-detail-grid",
                ".print-label",
                ".print-value",
                ".digital-signature-img",
                ".signature-line.has-digital-signature",
            ]
            for marker in required_css:
                if marker not in css:
                    failures.append(f"print.css is missing `{marker}`.")
        if not digital_signature_dir.exists():
            failures.append("DigitalSignature folder is missing.")

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
            if template_name.endswith("_classic.html") or template_name.endswith("_letterhead.html"):
                if "css/print_classic.css" not in content:
                    failures.append(f"{template_name} does not reference css/print_classic.css.")
                continue
            if "css/print.css" not in content and template_name != "sales/invoice_print_digital.html":
                failures.append(f"{template_name} does not reference css/print.css.")
            if template_name != "reports/print_report.html" and "print_footer.html" not in content and template_name != "sales/invoice_print_digital.html":
                failures.append(f"{template_name} does not include the shared print footer.")
            if template_name != "sales/invoice_print_digital.html" and "print_detail_grid.html" not in content:
                failures.append(f"{template_name} does not include the compact detail grid partial.")
            if "print-party-grid" in content or "print-meta-grid" in content:
                failures.append(f"{template_name} still uses an old vertical/grid detail block.")

        for template_name in ITEM_TABLE_PRINT_TEMPLATES:
            path = base_dir / "templates" / template_name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            if "<th" in content and ("Tax</th>" in content or "Tax %" in content or "tax_amount" in content):
                failures.append(f"{template_name} appears to show item-row tax columns.")

        quotation_print = base_dir / "templates" / "sales" / "quotation_print.html"
        if quotation_print.exists():
            content = quotation_print.read_text(encoding="utf-8")
            if "document_totals.html" not in content or "tax_total=quotation.tax_total" not in content:
                failures.append("sales/quotation_print.html does not pass quotation.tax_total to document totals.")
            if "format_quantity" not in content:
                failures.append("sales/quotation_print.html does not use format_quantity for item quantity.")
        if format_quantity("1.00") != "1" or format_quantity("2.50") != "2.5":
            failures.append("format_quantity helper is not formatting whole/decimal quantities correctly.")
        if format_amount("1250000.50") != "1,250,000.50":
            failures.append("format_amount helper is not adding comma separators correctly.")
        try:
            from core.calculation_utils import calculate_line_total

            line = calculate_line_total("1", "130000", "5", "0", "4.5", "tax_exclusive")
            if str(line["tax_amount"]) != "5557.50" or str(line["line_total"]) != "129057.50":
                failures.append("quotation tax calculation helper is not calculating tax after discount.")
        except Exception as exc:
            failures.append(f"quotation tax calculation helper check failed: {exc}")

        partials = [
            base_dir / "templates" / "partials" / "print_header.html",
            base_dir / "templates" / "partials" / "print_footer.html",
            base_dir / "templates" / "partials" / "print_detail_grid.html",
            base_dir / "templates" / "partials" / "document_totals.html",
        ]
        for partial in partials:
            if not partial.exists():
                failures.append(f"{partial.relative_to(base_dir)} is missing.")

        base_template = base_dir / "templates" / "base.html"
        if base_template.exists():
            base_content = base_template.read_text(encoding="utf-8")
            if "{% static 'favicon.ico' %}" not in base_content:
                failures.append("base.html does not include favicon.ico links.")
        else:
            failures.append("templates/base.html is missing.")

        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"FAIL: {failure}"))
            self.stdout.write(self.style.ERROR(f"FAIL: {len(failures)} print template check(s) failed."))
            return

        self.stdout.write(self.style.SUCCESS("PASS: print templates ready."))
