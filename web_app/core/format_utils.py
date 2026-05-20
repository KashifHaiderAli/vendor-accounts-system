from __future__ import annotations

from decimal import Decimal, InvalidOperation


def format_quantity(qty, blank_for_none=True):
    if qty is None or qty == "":
        return "" if blank_for_none else "0"
    try:
        value = Decimal(str(qty))
    except (InvalidOperation, TypeError, ValueError):
        return str(qty)
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f").rstrip("0").rstrip(".")
