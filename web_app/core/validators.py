from __future__ import annotations

from decimal import Decimal, InvalidOperation


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


def validate_email(value, required=False):
    cleaned = str(value or "").strip()
    if not cleaned:
        return "Email is required." if required else None
    if "@" not in cleaned:
        return "Enter a valid email address."
    domain = cleaned.rsplit("@", 1)[-1]
    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return "Enter a valid email address."
    return None


def validate_decimal(value, field_name, min_value=None, max_value=None, allow_zero=True):
    try:
        amount = Decimal(str(value or "0"))
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


def validate_integer(value, field_name, min_value=None, max_value=None):
    try:
        number = int(str(value or "0"))
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


def validate_choice(value, allowed_values, field_name):
    cleaned = str(value or "").strip()
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
