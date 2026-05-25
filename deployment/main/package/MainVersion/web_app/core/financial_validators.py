from __future__ import annotations

from decimal import Decimal


def ensure_not_negative(value, field_name):
    if Decimal(str(value or "0")) < 0:
        return f"{field_name} cannot be negative."
    return None


def ensure_positive(value, field_name):
    if Decimal(str(value or "0")) <= 0:
        return f"{field_name} must be greater than zero."
    return None


def ensure_not_over_amount(value, maximum, field_name, maximum_label):
    if Decimal(str(value or "0")) > Decimal(str(maximum or "0")):
        return f"{field_name} cannot be greater than {maximum_label}."
    return None
