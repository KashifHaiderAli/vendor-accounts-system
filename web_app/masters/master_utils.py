from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import connection

from authentication.auth_utils import dictfetchall, dictfetchone
from settings_module.services import log_user_activity, now_text


PER_PAGE = 20


def get_current_company_id(request):
    return request.session.get("company_id")


def get_current_branch_id(request):
    return request.session.get("current_branch_id")


def validate_decimal(value, field_label, minimum=None, maximum=None):
    try:
        amount = Decimal(str(value or "0"))
    except (InvalidOperation, TypeError):
        return None, f"{field_label} must be a valid number."
    if minimum is not None and amount < Decimal(str(minimum)):
        return None, f"{field_label} cannot be negative."
    if maximum is not None and amount > Decimal(str(maximum)):
        return None, f"{field_label} must be between {minimum} and {maximum}."
    return amount, None


def validate_email(value):
    if value and ("@" not in value or "." not in value.split("@")[-1]):
        return "Enter a valid email address."
    return None


def paginate(total_count, page, per_page=PER_PAGE):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    return {
        "page": page,
        "per_page": per_page,
        "total_count": total_count,
        "total_pages": total_pages,
        "offset": (page - 1) * per_page,
        "pages": list(range(1, total_pages + 1)),
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1,
        "next_page": page + 1,
    }


def list_records(config, company_id, branch_id, search="", status="", page=1):
    table = config["table"]
    params = [company_id, branch_id]
    clauses = [f"{table}.company_id = %s", f"{table}.branch_id = %s"]
    if search:
        like = f"%{search}%"
        search_clause = " OR ".join([f"{table}.{field} LIKE %s" for field in config["search_fields"]])
        clauses.append(f"({search_clause})")
        params.extend([like] * len(config["search_fields"]))
    if status == "active":
        clauses.append(f"{table}.is_active = 1")
    elif status == "inactive":
        clauses.append(f"{table}.is_active = 0")

    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} {config.get('joins', '')} WHERE {where_sql}",
            params,
        )
        total_count = int(cursor.fetchone()[0] or 0)
        pagination = paginate(total_count, page)
        cursor.execute(
            f"""
            SELECT {config['select_sql']}
            FROM {table} {config.get('joins', '')}
            WHERE {where_sql}
            ORDER BY {table}.is_active DESC, {config['order_by']}
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        rows = dictfetchall(cursor)
    return rows, pagination


def get_record(config, company_id, branch_id, record_id):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT *
            FROM {config['table']}
            WHERE id = %s AND company_id = %s AND branch_id = %s
            LIMIT 1
            """,
            [record_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def unique_value_exists(config, company_id, branch_id, field_name, value, exclude_id=None):
    params = [company_id, branch_id, value]
    clause = f"company_id = %s AND branch_id = %s AND lower({field_name}) = lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id FROM {config['table']} WHERE {clause} LIMIT 1",
            params,
        )
        return cursor.fetchone() is not None


def get_active_payment_terms(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, name, days
            FROM payment_terms
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY name ASC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def payment_term_exists(company_id, branch_id, payment_terms_id):
    if not payment_terms_id:
        return True
    try:
        term_id = int(payment_terms_id)
    except (TypeError, ValueError):
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM payment_terms
            WHERE id = %s AND company_id = %s AND branch_id = %s
            LIMIT 1
            """,
            [term_id, company_id, branch_id],
        )
        return cursor.fetchone() is not None


def get_parent_account(company_id, branch_id, account_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM accounts
            WHERE company_id = %s
              AND branch_id = %s
              AND lower(account_name) = lower(%s)
              AND is_active = 1
            LIMIT 1
            """,
            [company_id, branch_id, account_name],
        )
        return dictfetchone(cursor)


def generate_account_code(company_id, branch_id, base_code):
    candidate = base_code.upper()
    suffix = 2
    with connection.cursor() as cursor:
        while True:
            cursor.execute(
                """
                SELECT id FROM accounts
                WHERE company_id = %s AND branch_id = %s AND lower(account_code) = lower(%s)
                LIMIT 1
                """,
                [company_id, branch_id, candidate],
            )
            if not cursor.fetchone():
                return candidate
            candidate = f"{base_code.upper()}-{suffix}"
            suffix += 1


def create_linked_account(company_id, branch_id, account_code, account_name, account_type, parent_name):
    parent = get_parent_account(company_id, branch_id, parent_name)
    if not parent:
        raise ValueError(
            f"Required parent account '{parent_name}' was not found. "
            "Please ensure the Chart of Accounts is initialized before saving this record."
        )

    timestamp = now_text()
    final_code = generate_account_code(company_id, branch_id, account_code)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO accounts (
                company_id, branch_id, account_code, account_name, account_type,
                parent_id, is_control_account, is_system_account, is_active,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 0, 0, 1, %s, %s)
            """,
            [
                company_id,
                branch_id,
                final_code,
                account_name,
                account_type,
                parent["id"],
                timestamp,
                timestamp,
            ],
        )
        account_id = cursor.lastrowid
    if not account_id:
        raise ValueError("Linked account could not be created. Please try again.")
    return account_id


def update_linked_account_name(account_id, company_id, branch_id, account_name):
    if not account_id:
        return
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE accounts
            SET account_name = %s, updated_at = %s
            WHERE id = %s AND company_id = %s AND branch_id = %s
            """,
            [account_name, timestamp, account_id, company_id, branch_id],
        )


def insert_record(config, company_id, branch_id, user_id, data):
    timestamp = now_text()
    fields = config["fields"]
    columns = ["company_id", "branch_id"] + fields + [
        "created_by_id",
        "updated_by_id",
        "created_at",
        "updated_at",
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    values = [company_id, branch_id] + [data.get(field) for field in fields] + [
        user_id,
        user_id,
        timestamp,
        timestamp,
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {config['table']} ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return cursor.lastrowid


def update_record(config, company_id, branch_id, user_id, record_id, data):
    timestamp = now_text()
    fields = config["fields"]
    assignments = ", ".join([f"{field} = %s" for field in fields])
    values = [data.get(field) for field in fields] + [user_id, timestamp, record_id, company_id, branch_id]
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {config['table']}
            SET {assignments}, updated_by_id = %s, updated_at = %s
            WHERE id = %s AND company_id = %s AND branch_id = %s
            """,
            values,
        )


def set_record_active(config, company_id, branch_id, user_id, record_id, is_active):
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE {config['table']}
            SET is_active = %s, updated_by_id = %s, updated_at = %s
            WHERE id = %s AND company_id = %s AND branch_id = %s
            """,
            [is_active, user_id, timestamp, record_id, company_id, branch_id],
        )


def linked_account_has_journal_entries(account_id):
    if not account_id:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM journal_entry_lines
            WHERE account_id = %s
            LIMIT 1
            """,
            [account_id],
        )
        return cursor.fetchone() is not None


def future_reference_exists(table_key, record_id):
    # Placeholder for Phase 7+ transaction-reference checks.
    return False


def clean_text(request, field_name):
    return request.POST.get(field_name, "").strip()


def clean_bool(request, field_name, default=False):
    if field_name not in request.POST and default:
        return 1
    return 1 if request.POST.get(field_name) == "on" else 0
