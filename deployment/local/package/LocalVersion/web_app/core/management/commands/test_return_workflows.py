from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import reverse


class Command(BaseCommand):
    help = "Verify sales/purchase return auto-fetch, refund, and inventory wiring."

    def handle(self, *args, **options):
        failures = 0

        checks = [
            (
                "Sales return invoice item endpoint resolves",
                lambda: reverse("sales:return_invoice_items_detail", args=[1]) == "/sales/returns/invoice/1/items/",
            ),
            (
                "Sales return customer invoice filter endpoint resolves",
                lambda: reverse("sales:return_customer_invoices", args=[1]) == "/sales/returns/customer/1/invoices/",
            ),
            (
                "Purchase return purchase item endpoint resolves",
                lambda: reverse("purchases:return_purchase_items_detail", args=[1]) == "/purchases/returns/purchase/1/items/",
            ),
            (
                "Purchase return supplier purchase filter endpoint resolves",
                lambda: reverse("purchases:return_supplier_purchases", args=[1]) == "/purchases/returns/supplier/1/purchases/",
            ),
        ]

        for label, check in checks:
            try:
                ok = check()
            except Exception as exc:
                ok = False
                self.stdout.write(self.style.ERROR(f"FAIL {label}: {exc}"))
            if ok:
                self.stdout.write(f"PASS {label}")
            else:
                failures += 1
                if label not in ("Sales return invoice item endpoint resolves", "Purchase return purchase item endpoint resolves"):
                    self.stdout.write(self.style.ERROR(f"FAIL {label}"))

        file_checks = [
            (
                "Sales return form fetches invoice items",
                "templates/sales/sales_return_form.html",
                ["data-items-url-template", "data-invoices-url-template", "sales:return_invoice_items_detail", "sales:return_customer_invoices", "Invoiced", "Returned", "Max", "sr-remove-row"],
                ["Cash refund handling is not implemented", "addReturnRow"],
            ),
            (
                "Purchase return form fetches purchase items",
                "templates/purchases/purchase_return_form.html",
                ["data-items-url-template", "data-purchases-url-template", "purchases:return_purchase_items_detail", "purchases:return_supplier_purchases", "Purchased", "Returned", "Max", "pr-remove-row"],
                ["Supplier refund receipt handling is not implemented", "addPurchaseReturnRow"],
            ),
            (
                "Sales return JavaScript loads rows from selected invoice",
                "static/js/sales_return.js",
                ["fetch(", "sales_invoice_id", "customer_id", "loadInvoiceItems", "loadCustomerInvoices", "max_returnable_qty", "already_returned_qty", "sr-remove-row", "sales-return-total", "replace(/&/g"],
                ["replaceAll", "addReturnRow"],
            ),
            (
                "Purchase return JavaScript loads rows from selected purchase",
                "static/js/purchase_return.js",
                ["fetch(", "supplier_purchase_id", "supplier_id", "loadPurchaseItems", "loadSupplierPurchases", "max_returnable_qty", "already_returned_qty", "pr-remove-row", "purchase-return-total", "replace(/&/g"],
                ["replaceAll", "addPurchaseReturnRow"],
            ),
            (
                "Sales return service calculates refund amount",
                "sales/return_services.py",
                ['"refund_amount": grand_total', 'data.get("refund_amount") or data["grand_total"]', "post_sales_return_stock", '"invoiced_qty"', '"already_returned_qty"'],
                ['"refund_amount": Decimal("0.00")', 'str(Decimal("0.00"))'],
            ),
            (
                "Purchase return service calculates refund amount and checks stock",
                "purchases/return_services.py",
                ['"refund_amount": grand_total', 'data.get("refund_amount") or data["grand_total"]', "validate_available_stock", "post_purchase_return_stock", '"purchased_qty"', '"already_returned_qty"'],
                ['"refund_amount": Decimal("0.00")', 'str(Decimal("0.00"))'],
            ),
            (
                "Sales return JSON contract includes returnable quantity fields",
                "sales/views.py",
                ['"invoice_item_id"', '"item_id"', '"item_name"', '"invoiced_qty"', '"already_returned_qty"', '"max_returnable_qty"', "sales_return_customer_invoices"],
                [],
            ),
            (
                "Purchase return JSON contract includes returnable quantity fields",
                "purchases/views.py",
                ['"purchase_item_id"', '"item_id"', '"item_name"', '"purchased_qty"', '"already_returned_qty"', '"max_returnable_qty"', "purchase_return_supplier_purchases"],
                [],
            ),
        ]

        for label, relative_path, required, forbidden in file_checks:
            path = Path(relative_path)
            try:
                text = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {label}: missing {relative_path}"))
                continue

            missing = [fragment for fragment in required if fragment not in text]
            present = [fragment for fragment in forbidden if fragment in text]
            if missing or present:
                failures += 1
                detail = []
                if missing:
                    detail.append(f"missing {', '.join(missing)}")
                if present:
                    detail.append(f"forbidden {', '.join(present)}")
                self.stdout.write(self.style.ERROR(f"FAIL {label}: {'; '.join(detail)}"))
            else:
                self.stdout.write(f"PASS {label}")

        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} return workflow check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: return workflows ready."))
