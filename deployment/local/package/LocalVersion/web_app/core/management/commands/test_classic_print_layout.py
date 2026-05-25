from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import get_template, render_to_string
from django.urls import reverse


class Command(BaseCommand):
    help = "Verify classic quotation and invoice print templates/routes."

    def handle(self, *args, **options):
        failures = []
        template_paths = [
            "sales/quotation_print_classic.html",
            "sales/invoice_print_classic.html",
            "sales/quotation_print.html",
            "sales/invoice_print_preprinted.html",
            "sales/invoice_print_digital.html",
        ]
        for template_name in template_paths:
            disk_path = Path(settings.BASE_DIR) / "templates" / template_name
            if not disk_path.exists():
                failures.append(f"Missing template file: {template_name}")
                continue
            try:
                get_template(template_name)
            except Exception as exc:
                failures.append(f"Template load failed for {template_name}: {exc}")

        css_path = Path(settings.BASE_DIR) / "static" / "css" / "print_classic.css"
        if not css_path.exists():
            failures.append("Missing CSS file: static/css/print_classic.css")

        for route_name, arg in [
            ("sales:quotation_print", 1),
            ("sales:quotation_classic_print", 1),
            ("sales:quotation_classic_pdf", 1),
            ("sales:invoice_print", 1),
            ("sales:invoice_digital_print", 1),
            ("sales:invoice_classic_print", 1),
            ("sales:invoice_classic_pdf", 1),
        ]:
            try:
                reverse(route_name, args=[arg])
            except Exception as exc:
                failures.append(f"Route reverse failed for {route_name}: {exc}")

        company = {
            "company_name": "Classic Demo Company",
            "address": "Karachi",
            "phone": "021-000000",
            "mobile": "03000000000",
            "website": "example.com",
            "ntn": "123456",
        }
        quotation = {
            "quotation_no": "Q-001",
            "quotation_date": "2026-05-23",
            "valid_till": "2026-06-23",
            "display_customer_code": "C-001",
            "display_customer_name": "Classic Customer",
            "display_contact_person": "Contact Person",
            "display_customer_phone": "03001234567",
            "display_customer_mobile": "",
            "subject": "Classic quotation",
            "payment_terms_name": "15 Days",
            "subtotal": Decimal("1000.00"),
            "discount_total": Decimal("50.00"),
            "tax_total": Decimal("0.00"),
            "grand_total": Decimal("950.00"),
        }
        invoice = {
            "invoice_no": "INV-001",
            "invoice_date": "2026-05-23",
            "invoice_type": "cash_memo",
            "customer_code": "C-001",
            "company_name": "Classic Customer",
            "contact_person": "Contact Person",
            "customer_phone": "03001234567",
            "dc_no": "DC-001",
            "po_number": "PO-001",
            "payment_terms_days": 15,
            "subtotal": Decimal("1000.00"),
            "discount_total": Decimal("50.00"),
            "tax_total": Decimal("0.00"),
            "grand_total": Decimal("950.00"),
        }
        items = [{"description": "Classic Item", "quantity": Decimal("1.00"), "rate": Decimal("1000.00"), "line_total": Decimal("950.00")}]

        quotation_html = render_to_string(
            "sales/quotation_print_classic.html",
            {"company": company, "quotation": quotation, "items": items, "tax_enabled": False, "show_logo": False, "logo_url": ""},
        )
        invoice_html = render_to_string(
            "sales/invoice_print_classic.html",
            {"company": company, "invoice": invoice, "items": items, "tax_enabled": False, "show_logo": False, "logo_url": ""},
        )

        quotation_needles = ["QUOTATION", "S. NO.", "QTY.", "DESCRIPTION", "UNIT PRICE", "AMOUNT", "Sub Total", "Less Disc.", "Grand Total", "Rupees in words"]
        invoice_needles = ["BILL / CASH MEMO", "S. NO.", "QTY.", "DESCRIPTION", "UNIT PRICE", "AMOUNT", "Sub Total", "Less Disc.", "Total Due", "Rupees in words"]
        for needle in quotation_needles:
            if needle not in quotation_html:
                failures.append(f"Classic quotation output missing: {needle}")
        for needle in invoice_needles:
            if needle not in invoice_html:
                failures.append(f"Classic invoice output missing: {needle}")
        for forbidden in ["Tax", "NTN", "STRN"]:
            if forbidden in quotation_html:
                failures.append(f"Classic quotation tax-off output contains: {forbidden}")
            if forbidden in invoice_html:
                failures.append(f"Classic invoice tax-off output contains: {forbidden}")

        if "Nine Hundred Fifty Rupees Only" not in quotation_html or "Nine Hundred Fifty Rupees Only" not in invoice_html:
            failures.append("Amount in words did not render as expected.")

        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"FAIL: {failure}"))
            raise CommandError("Classic print layout checks failed.")
        self.stdout.write(self.style.SUCCESS("PASS: classic print templates ready."))
