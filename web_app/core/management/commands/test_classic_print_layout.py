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
            css_text = ""
        else:
            css_text = css_path.read_text(encoding="utf-8")
            classic_value_block = css_text.split(".classic-value", 1)[1].split("}", 1)[0] if ".classic-value" in css_text else ""
            if "border-bottom: 1px" in classic_value_block:
                failures.append("Classic meta value fields still use underline border-bottom.")
            for selector in [
                ".classic-items-table tbody tr.classic-item-row",
                ".classic-items-table tbody tr.classic-filler-row td",
                ".classic-invoice-received-by",
            ]:
                if selector not in css_text:
                    failures.append(f"Classic CSS missing spacing selector: {selector}")

        for template_name in ["sales/quotation_print_classic.html", "sales/invoice_print_classic.html"]:
            source = (Path(settings.BASE_DIR) / "templates" / template_name).read_text(encoding="utf-8")
            if 'class="classic-item-row"' not in source:
                failures.append(f"{template_name} missing classic-item-row on real item rows.")
            if 'class="classic-filler-row"' not in source:
                failures.append(f"{template_name} missing classic-filler-row on filler rows.")
            if 'class="item-row"' in source or 'class="filler-row"' in source:
                failures.append(f"{template_name} still contains old item/filler row class names.")

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
            "company_name": "Dynamic Classic Company",
            "address": "Dynamic Address",
            "phone": "021-111111",
            "mobile": "03001111111",
            "email": "classic@example.com",
            "website": "dynamic.example.com",
            "ntn": "123456",
        }
        classic_context = {
            "classic_company_name": "Dynamic Classic Company",
            "classic_company_address": "Dynamic Address",
            "classic_company_phone": "03001111111",
            "classic_company_email": "classic@example.com",
            "classic_company_website": "dynamic.example.com",
            "classic_company_ntn": "123456",
            "classic_company_strn": "",
            "classic_contact_person": "Dynamic Contact",
            "classic_contact_phone": "03001111111",
            "classic_contact_email": "classic@example.com",
            "classic_terms_text": "",
            "classic_use_saved_terms": False,
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
            "subtotal": Decimal("1250000.50"),
            "discount_total": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "grand_total": Decimal("1250000.50"),
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
            "subtotal": Decimal("1250000.50"),
            "discount_total": Decimal("50.00"),
            "tax_total": Decimal("0.00"),
            "grand_total": Decimal("1250000.50"),
        }
        items = [{"description": "Classic Item", "quantity": Decimal("1.00"), "rate": Decimal("1250000.50"), "line_total": Decimal("1250000.50")}]

        quotation_html = render_to_string(
            "sales/quotation_print_classic.html",
            {"company": company, "quotation": quotation, "items": items, "tax_enabled": False, "show_logo": False, "logo_url": "", **classic_context},
        )
        invoice_html = render_to_string(
            "sales/invoice_print_classic.html",
            {"company": company, "invoice": invoice, "items": items, "tax_enabled": False, "show_logo": False, "logo_url": "", **classic_context},
        )
        tax_invoice = dict(invoice, tax_total=Decimal("225000.09"), grand_total=Decimal("1475000.59"))
        tax_invoice_html = render_to_string(
            "sales/invoice_print_classic.html",
            {"company": company, "invoice": tax_invoice, "items": items, "tax_enabled": True, "show_logo": False, "logo_url": "", **classic_context},
        )

        quotation_needles = ["QUOTATION", "S. NO.", "QTY.", "DESCRIPTION", "UNIT PRICE", "AMOUNT", "Sub Total", "Less Disc.", "Grand Total", "Rupees in words"]
        invoice_needles = ["INVOICE", "S. NO.", "QTY.", "DESCRIPTION", "UNIT PRICE", "AMOUNT", "Sub Total", "Less Disc.", "Total Due", "Rupees in words"]
        for needle in quotation_needles:
            if needle not in quotation_html:
                failures.append(f"Classic quotation output missing: {needle}")
        for needle in invoice_needles:
            if needle not in invoice_html:
                failures.append(f"Classic invoice output missing: {needle}")
        for needle in ["Availability", "Payment Terms", "Validity", "Thank You For Your Business!", "Dynamic Contact", "03001111111", "classic@example.com"]:
            if needle not in quotation_html:
                failures.append(f"Classic quotation output missing: {needle}")
        for needle in ["Dynamic Classic Company", "Dynamic Address", "classic@example.com", "dynamic.example.com"]:
            if needle not in quotation_html:
                failures.append(f"Classic quotation header/footer missing company setup value: {needle}")
            if needle not in invoice_html:
                failures.append(f"Classic invoice header missing company setup value: {needle}")
        for hardcoded in ["Mohsin Ansari", "0345-2138642", "mohsin@dominantsystems.pk", "Dominant Systems Pakistan"]:
            if hardcoded in quotation_html or hardcoded in invoice_html:
                failures.append(f"Classic output contains hard-coded value: {hardcoded}")
            for template_name in ["sales/quotation_print_classic.html", "sales/invoice_print_classic.html"]:
                source = (Path(settings.BASE_DIR) / "templates" / template_name).read_text(encoding="utf-8")
                if hardcoded in source:
                    failures.append(f"{template_name} contains hard-coded value: {hardcoded}")
        if "TAX INVOICE" in invoice_html:
            failures.append("Classic invoice output still contains TAX INVOICE.")
        if "SALES TAX INVOICE" not in tax_invoice_html:
            failures.append("Tax-enabled classic invoice does not show SALES TAX INVOICE.")
        if "SALES TAX INVOICE" in invoice_html:
            failures.append("Tax-disabled classic invoice should show INVOICE, not SALES TAX INVOICE.")
        if "1,250,000.50" not in quotation_html or "1,250,000.50" not in invoice_html:
            failures.append("Classic print amounts are not comma-formatted.")
        for forbidden in ["Tax", "TAX", "NTN", "STRN"]:
            if forbidden in quotation_html:
                failures.append(f"Classic quotation tax-off output contains: {forbidden}")
            if forbidden in invoice_html:
                failures.append(f"Classic invoice tax-off output contains: {forbidden}")

        if "One Million Two Hundred Fifty Thousand Rupees and Fifty Paisa Only" not in quotation_html or "One Million Two Hundred Fifty Thousand Rupees and Fifty Paisa Only" not in invoice_html:
            failures.append("Amount in words did not render as expected.")

        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"FAIL: {failure}"))
            raise CommandError("Classic print layout checks failed.")
        self.stdout.write(self.style.SUCCESS("PASS: classic print templates ready."))
