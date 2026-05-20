from __future__ import annotations

from decimal import Decimal, InvalidOperation


def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def calculate_line_total(quantity, rate, discount_percent=0, discount_amount=0, tax_percent=0, tax_option="tax_exclusive"):
    qty = money(quantity)
    unit_rate = money(rate)
    disc_pct = money(discount_percent)
    posted_discount = money(discount_amount)
    tax_pct = money(tax_percent)
    mode = tax_option or "tax_exclusive"

    line_base = (qty * unit_rate).quantize(Decimal("0.01"))
    discount = (line_base * disc_pct / Decimal("100")).quantize(Decimal("0.01")) if disc_pct > 0 else posted_discount
    if discount > line_base:
        discount = line_base

    discounted_amount = line_base - discount
    if mode == "no_tax" or tax_pct <= 0:
        taxable_amount = discounted_amount
        tax_amount = Decimal("0.00")
        line_total = discounted_amount
    elif mode == "tax_inclusive":
        divisor = Decimal("100") + tax_pct
        tax_amount = (discounted_amount * tax_pct / divisor).quantize(Decimal("0.01"))
        taxable_amount = discounted_amount - tax_amount
        line_total = discounted_amount
    else:
        taxable_amount = discounted_amount
        tax_amount = (taxable_amount * tax_pct / Decimal("100")).quantize(Decimal("0.01"))
        line_total = taxable_amount + tax_amount

    return {
        "line_base": line_base,
        "discount_amount": discount,
        "taxable_amount": taxable_amount,
        "tax_amount": tax_amount,
        "line_total": line_total,
    }


def calculate_document_totals(items, tax_option="tax_exclusive"):
    totals = {"subtotal": Decimal("0.00"), "discount_total": Decimal("0.00"), "tax_total": Decimal("0.00"), "grand_total": Decimal("0.00")}
    calculated = []
    for item in items:
        line = calculate_line_total(
            item.get("quantity"),
            item.get("rate") or item.get("purchase_rate"),
            item.get("discount_percent", 0),
            item.get("discount_amount", 0),
            item.get("tax_percent", 0),
            tax_option,
        )
        totals["subtotal"] += line["taxable_amount"] if tax_option == "tax_inclusive" else line["line_base"]
        totals["discount_total"] += line["discount_amount"]
        totals["tax_total"] += line["tax_amount"]
        totals["grand_total"] += line["line_total"]
        calculated.append({**item, **line})
    return calculated, totals
