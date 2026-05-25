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


ONES = (
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _under_thousand_to_words(number):
    words = []
    hundreds, remainder = divmod(number, 100)
    if hundreds:
        words.extend([ONES[hundreds], "Hundred"])
    if remainder:
        if remainder < 20:
            words.append(ONES[remainder])
        else:
            tens, ones = divmod(remainder, 10)
            words.append(TENS[tens])
            if ones:
                words.append(ONES[ones])
    return " ".join(words)


def amount_in_words(value):
    try:
        amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0.00")
    rupees = int(amount)
    paisa = int((amount - Decimal(rupees)) * 100)
    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        for scale_value, scale_name in ((10**9, "Billion"), (10**6, "Million"), (1000, "Thousand"), (1, "")):
            chunk, rupees = divmod(rupees, scale_value)
            if chunk:
                parts.append(f"{_under_thousand_to_words(chunk)} {scale_name}".strip())
        words = " ".join(parts)
    if paisa:
        words = f"{words} Rupees and {_under_thousand_to_words(paisa)} Paisa"
    else:
        words = f"{words} Rupees"
    return words + " Only"
