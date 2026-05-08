from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


PHONE_ALLOWED_RE = re.compile(r"^[0-9+\-\s()]+$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
WEBSITE_RE = re.compile(
    r"^(https?://)?(www\.)?[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+(/[^\s]*)?$"
)
DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")
INTEGER_RE = re.compile(r"^-?\d+$")
MONEY_DIGITS_RE = re.compile(r"^-?(\d{1,15})(\.\d{1,2})?$")


def clean_text(value, max_length=None, required=False, field_name="Field"):
    cleaned = str(value or "").strip()
    if required and not cleaned:
        return cleaned, f"{field_name} is required."
    if max_length is not None and len(cleaned) > max_length:
        return cleaned, f"{field_name} cannot be longer than {max_length} characters."
    return cleaned, None


def validate_required(value, field_name):
    if str(value or "").strip() == "":
        return f"{field_name} is required."
    return None


def validate_phone(value, field_name="Phone", required=False):
    cleaned = str(value or "").strip()
    if not cleaned:
        return cleaned, f"{field_name} is required." if required else None
    if len(cleaned) > 30:
        return cleaned, f"{field_name} cannot be longer than 30 characters."
    if not PHONE_ALLOWED_RE.match(cleaned):
        return cleaned, f"{field_name} can contain only digits, +, -, spaces, and parentheses."
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7:
        return cleaned, f"{field_name} must contain at least 7 digits."
    return cleaned, None


def validate_mobile(value, field_name="Mobile", required=False):
    cleaned, error = validate_phone(value, field_name, required)
    if error or not cleaned:
        return cleaned, error
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 10:
        return cleaned, f"{field_name} must contain at least 10 digits."
    return cleaned, None


def validate_email(value, field_name="Email", required=False):
    cleaned = str(value or "").strip()
    if not cleaned:
        return cleaned, f"{field_name} is required." if required else None
    if len(cleaned) > 254:
        return cleaned, f"{field_name} cannot be longer than 254 characters."
    if any(char.isspace() for char in cleaned) or not EMAIL_RE.match(cleaned):
        return cleaned, "Enter a valid email address."
    return cleaned.lower(), None


def validate_website(value, field_name="Website", required=False):
    cleaned = str(value or "").strip()
    if not cleaned:
        return cleaned, f"{field_name} is required." if required else None
    if len(cleaned) > 200:
        return cleaned, f"{field_name} cannot be longer than 200 characters."
    if any(char.isspace() for char in cleaned) or not WEBSITE_RE.match(cleaned):
        return cleaned, f"Enter a valid {field_name.lower()}."
    return cleaned, None


def validate_decimal(value, field_name, min_value=None, max_value=None, allow_zero=True, required=False):
    raw = str(value or "").strip()
    if raw == "":
        if required:
            return None, f"{field_name} is required."
        raw = "0"
    if "," in raw:
        return None, f"{field_name} must not contain commas."
    if not DECIMAL_RE.match(raw):
        return None, f"{field_name} must be a valid number."
    try:
        amount = Decimal(raw)
    except (InvalidOperation, TypeError):
        return None, f"{field_name} must be a valid number."
    if min_value is not None and amount < Decimal(str(min_value)):
        if Decimal(str(min_value)) == Decimal("0"):
            return None, f"{field_name} cannot be negative."
        return None, f"{field_name} must be at least {min_value}."
    if not allow_zero and amount == 0:
        return None, f"{field_name} must be greater than zero."
    if max_value is not None and amount > Decimal(str(max_value)):
        if min_value is not None:
            return None, f"{field_name} must be between {min_value} and {max_value}."
        return None, f"{field_name} cannot be greater than {max_value}."
    return amount, None


def validate_money(value, field_name, allow_negative=False, allow_zero=True, required=False):
    raw = str(value or "").strip()
    if raw == "":
        if required:
            return None, f"{field_name} is required."
        raw = "0"
    if "," in raw:
        return None, f"{field_name} must not contain commas."
    if not MONEY_DIGITS_RE.match(raw):
        return None, f"{field_name} must be a valid amount with up to 2 decimal places."
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return None, f"{field_name} must be a valid amount."
    if not allow_negative and amount < 0:
        return None, f"{field_name} cannot be negative."
    if not allow_zero and amount == 0:
        return None, f"{field_name} must be greater than zero."
    return amount, None


def validate_percentage(value, field_name, required=False):
    amount, error = validate_decimal(value, field_name, min_value=0, max_value=100, required=required)
    if error:
        return None, error
    return amount, None


def validate_integer(value, field_name, min_value=None, max_value=None, required=False):
    raw = str(value or "").strip()
    if raw == "":
        if required:
            return None, f"{field_name} is required."
        raw = "0"
    if not INTEGER_RE.match(raw):
        return None, f"{field_name} must be a whole number."
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return None, f"{field_name} must be a whole number."
    if min_value is not None and number < int(min_value):
        if int(min_value) == 0:
            return None, f"{field_name} cannot be negative."
        return None, f"{field_name} must be at least {min_value}."
    if max_value is not None and number > int(max_value):
        if min_value is not None:
            return None, f"{field_name} must be between {min_value} and {max_value}."
        return None, f"{field_name} cannot be greater than {max_value}."
    return number, None


def validate_date(value, field_name, required=False):
    cleaned = str(value or "").strip()
    if not cleaned:
        return None, f"{field_name} is required." if required else None
    try:
        parsed = datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        return None, f"{field_name} must be a valid date in YYYY-MM-DD format."
    return parsed, None


def validate_choice(value, allowed_values, field_name, required=True):
    cleaned = str(value or "").strip()
    if not cleaned and not required:
        return None
    allowed_lookup = {str(item).lower(): str(item) for item in allowed_values}
    if cleaned.lower() not in allowed_lookup:
        choices = ", ".join(str(item) for item in allowed_values)
        return f"{field_name} must be one of: {choices}."
    return None


def validate_unique_code(connection, table_name, code_field, code_value, company_id, branch_id, current_id=None):
    if str(code_value or "").strip() == "":
        return None
    label = code_field.replace("_", " ").title()
    params = [company_id, code_value]
    branch_clause = "branch_id IS NULL" if branch_id is None else "branch_id = %s"
    if branch_id is not None:
        params.insert(1, branch_id)
    clause = f"company_id = %s AND {branch_clause} AND lower({code_field}) = lower(%s)"
    if current_id:
        clause += " AND id <> %s"
        params.append(current_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM {table_name} WHERE {clause} LIMIT 1", params)
        if cursor.fetchone():
            return f"{label} already exists for the current branch."
    return None


def collect_form_errors(errors):
    if not errors:
        return []
    collected = []
    for message in errors.values():
        if isinstance(message, (list, tuple)):
            collected.extend(str(item) for item in message if item)
        elif message:
            collected.append(str(message))
    return collected


def normalize_bool(value):
    return 1 if str(value).lower() in {"1", "true", "yes", "on"} or value is True else 0
