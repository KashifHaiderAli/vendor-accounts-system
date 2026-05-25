from __future__ import annotations

from django.db import connection, transaction
from django.utils import timezone

from authentication.auth_utils import dictfetchall, dictfetchone


COMPANY_FIELDS = [
    "company_name",
    "legal_name",
    "address",
    "phone",
    "mobile",
    "email",
    "website",
    "ntn",
    "strn",
    "logo_path",
    "is_active",
]

COMPANY_SETTINGS_FIELDS = [
    "quotation_footer",
    "invoice_footer",
    "bank_details",
    "authorized_person_name",
]

NUMBERING_FIELDS = [
    "customer_prefix",
    "supplier_prefix",
    "item_prefix",
    "quotation_prefix",
    "confirmation_prefix",
    "delivery_challan_prefix",
    "invoice_prefix",
    "sales_return_prefix",
    "cash_memo_prefix",
    "receipt_prefix",
    "purchase_prefix",
    "purchase_return_prefix",
    "supplier_payment_prefix",
    "service_contract_prefix",
    "expense_voucher_prefix",
    "use_year_in_number",
    "number_padding",
]

NUMBERING_DEFAULTS = {
    "customer_prefix": "CUS",
    "supplier_prefix": "SUP",
    "item_prefix": "ITM",
    "quotation_prefix": "QTN",
    "confirmation_prefix": "CONF",
    "delivery_challan_prefix": "DC",
    "invoice_prefix": "INV",
    "sales_return_prefix": "SR",
    "cash_memo_prefix": "CM",
    "receipt_prefix": "RCV",
    "purchase_prefix": "PUR",
    "purchase_return_prefix": "PR",
    "supplier_payment_prefix": "SPV",
    "service_contract_prefix": "SC",
    "expense_voucher_prefix": "EXP",
    "use_year_in_number": 1,
    "number_padding": 4,
}

TAX_DEFAULTS = {
    "default_sales_tax_percent": 0,
    "default_input_tax_percent": 0,
    "default_tax_applicable": 0,
    "tax_invoice_label": "Tax Invoice",
    "show_ntn_on_invoice": 1,
    "show_strn_on_invoice": 1,
}


def now_text():
    return timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")


def get_company(company_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id = %s LIMIT 1", [company_id])
        return dictfetchone(cursor)


def get_branch(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM branches WHERE company_id = %s AND id = %s LIMIT 1",
            [company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_company_settings(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM company_settings
            WHERE company_id = %s
              AND (branch_id = %s OR branch_id IS NULL)
            ORDER BY CASE WHEN branch_id = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            [company_id, branch_id, branch_id],
        )
        return dictfetchone(cursor)


def save_company_and_settings(company_id, branch_id, company_data, settings_data):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE companies
                SET company_name = %s,
                    legal_name = %s,
                    address = %s,
                    phone = %s,
                    mobile = %s,
                    email = %s,
                    website = %s,
                    ntn = %s,
                    strn = %s,
                    logo_path = %s,
                    is_active = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                [
                    company_data["company_name"],
                    company_data.get("legal_name"),
                    company_data.get("address"),
                    company_data.get("phone"),
                    company_data.get("mobile"),
                    company_data.get("email"),
                    company_data.get("website"),
                    company_data.get("ntn"),
                    company_data.get("strn"),
                    company_data.get("logo_path"),
                    company_data.get("is_active", 1),
                    timestamp,
                    company_id,
                ],
            )
            cursor.execute(
                """
                SELECT id
                FROM company_settings
                WHERE company_id = %s AND branch_id = %s
                LIMIT 1
                """,
                [company_id, branch_id],
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """
                    UPDATE company_settings
                    SET quotation_footer = %s,
                        invoice_footer = %s,
                        bank_details = %s,
                        authorized_person_name = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    [
                        settings_data.get("quotation_footer"),
                        settings_data.get("invoice_footer"),
                        settings_data.get("bank_details"),
                        settings_data.get("authorized_person_name"),
                        timestamp,
                        row[0],
                    ],
                )
                settings_id = row[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO company_settings (
                        company_id, branch_id, quotation_footer, invoice_footer,
                        bank_details, authorized_person_name, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        company_id,
                        branch_id,
                        settings_data.get("quotation_footer"),
                        settings_data.get("invoice_footer"),
                        settings_data.get("bank_details"),
                        settings_data.get("authorized_person_name"),
                        timestamp,
                        timestamp,
                    ],
                )
                settings_id = cursor.lastrowid
    return settings_id


def list_branches(company_id, search="", status=""):
    params = [company_id]
    clauses = ["company_id = %s"]
    if search:
        like = f"%{search}%"
        clauses.append(
            "(branch_code LIKE %s OR branch_name LIKE %s OR phone LIKE %s OR email LIKE %s)"
        )
        params.extend([like, like, like, like])
    if status == "active":
        clauses.append("is_active = 1")
    elif status == "inactive":
        clauses.append("is_active = 0")

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT *
            FROM branches
            WHERE {' AND '.join(clauses)}
            ORDER BY is_head_office DESC, is_active DESC, branch_name ASC
            """,
            params,
        )
        return dictfetchall(cursor)


def branch_code_exists(company_id, branch_code, exclude_branch_id=None):
    params = [company_id, branch_code]
    clause = "company_id = %s AND lower(branch_code) = lower(%s)"
    if exclude_branch_id:
        clause += " AND id <> %s"
        params.append(exclude_branch_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM branches WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def count_active_branches(company_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM branches WHERE company_id = %s AND is_active = 1",
            [company_id],
        )
        return int(cursor.fetchone()[0] or 0)


def save_branch(company_id, branch_data, branch_id=None, current_user_id=None, is_master_user=False):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if branch_data.get("is_head_office"):
                cursor.execute(
                    "UPDATE branches SET is_head_office = 0, updated_at = %s WHERE company_id = %s",
                    [timestamp, company_id],
                )

            if branch_id:
                cursor.execute(
                    """
                    UPDATE branches
                    SET branch_code = %s,
                        branch_name = %s,
                        address = %s,
                        phone = %s,
                        mobile = %s,
                        email = %s,
                        is_head_office = %s,
                        is_active = %s,
                        updated_at = %s
                    WHERE id = %s AND company_id = %s
                    """,
                    [
                        branch_data["branch_code"],
                        branch_data["branch_name"],
                        branch_data.get("address"),
                        branch_data.get("phone"),
                        branch_data.get("mobile"),
                        branch_data.get("email"),
                        branch_data.get("is_head_office", 0),
                        branch_data.get("is_active", 1),
                        timestamp,
                        branch_id,
                        company_id,
                    ],
                )
                saved_id = branch_id
            else:
                cursor.execute(
                    """
                    INSERT INTO branches (
                        company_id, branch_code, branch_name, address, phone, mobile,
                        email, is_head_office, is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        company_id,
                        branch_data["branch_code"],
                        branch_data["branch_name"],
                        branch_data.get("address"),
                        branch_data.get("phone"),
                        branch_data.get("mobile"),
                        branch_data.get("email"),
                        branch_data.get("is_head_office", 0),
                        branch_data.get("is_active", 1),
                        timestamp,
                        timestamp,
                    ],
                )
                saved_id = cursor.lastrowid
                if is_master_user and current_user_id:
                    ensure_user_branch_access(cursor, current_user_id, saved_id, timestamp)
    return saved_id


def ensure_user_branch_access(cursor, user_id, branch_id, timestamp):
    cursor.execute(
        "SELECT id FROM user_branches WHERE user_id = %s AND branch_id = %s LIMIT 1",
        [user_id, branch_id],
    )
    if cursor.fetchone():
        return
    cursor.execute(
        """
        INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at)
        VALUES (%s, %s, 0, %s, %s)
        """,
        [user_id, branch_id, timestamp, timestamp],
    )


def set_branch_active(company_id, branch_id, is_active):
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE branches
            SET is_active = %s, updated_at = %s
            WHERE company_id = %s AND id = %s
            """,
            [is_active, timestamp, company_id, branch_id],
        )


def make_head_office(company_id, branch_id):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE branches SET is_head_office = 0, updated_at = %s WHERE company_id = %s",
                [timestamp, company_id],
            )
            cursor.execute(
                """
                UPDATE branches
                SET is_head_office = 1, is_active = 1, updated_at = %s
                WHERE company_id = %s AND id = %s
                """,
                [timestamp, company_id, branch_id],
            )


def get_numbering_settings(company_id, branch_id):
    return get_or_create_settings_row(
        "numbering_settings",
        NUMBERING_FIELDS,
        NUMBERING_DEFAULTS,
        company_id,
        branch_id,
    )


def save_numbering_settings(company_id, branch_id, data):
    return upsert_settings_row(
        "numbering_settings",
        NUMBERING_FIELDS,
        company_id,
        branch_id,
        data,
    )


def get_tax_settings(company_id, branch_id):
    return get_or_create_settings_row(
        "tax_settings",
        list(TAX_DEFAULTS.keys()),
        TAX_DEFAULTS,
        company_id,
        branch_id,
    )


def save_tax_settings(company_id, branch_id, data):
    return upsert_settings_row(
        "tax_settings",
        list(TAX_DEFAULTS.keys()),
        company_id,
        branch_id,
        data,
    )


def get_or_create_settings_row(table_name, fields, defaults, company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE company_id = %s AND branch_id = %s
            LIMIT 1
            """,
            [company_id, branch_id],
        )
        row = dictfetchone(cursor)
        if row:
            return row

        cursor.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE company_id = %s AND (branch_id IS NULL OR branch_id <> %s)
            ORDER BY CASE WHEN branch_id IS NULL THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """,
            [company_id, branch_id],
        )
        base_row = dictfetchone(cursor) or defaults.copy()

    data = {field: base_row.get(field, defaults.get(field)) for field in fields}
    row_id = upsert_settings_row(table_name, fields, company_id, branch_id, data)
    data.update({"id": row_id, "company_id": company_id, "branch_id": branch_id})
    return data


def upsert_settings_row(table_name, fields, company_id, branch_id, data):
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id FROM {table_name} WHERE company_id = %s AND branch_id = %s LIMIT 1",
            [company_id, branch_id],
        )
        row = cursor.fetchone()
        values = [data.get(field) for field in fields]
        if row:
            assignments = ", ".join([f"{field} = %s" for field in fields])
            cursor.execute(
                f"UPDATE {table_name} SET {assignments}, updated_at = %s WHERE id = %s",
                values + [timestamp, row[0]],
            )
            return row[0]

        columns = ["company_id", "branch_id"] + fields + ["created_at", "updated_at"]
        placeholders = ", ".join(["%s"] * len(columns))
        cursor.execute(
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
            [company_id, branch_id] + values + [timestamp, timestamp],
        )
        return cursor.lastrowid


def log_user_activity(
    request,
    action_type,
    module_name,
    table_name=None,
    record_id=None,
    description=None,
):
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_activity_log (
                company_id, branch_id, user_id, action_type, module_name,
                table_name, record_id, description, activity_datetime, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                request.session.get("company_id"),
                request.session.get("current_branch_id"),
                request.session.get("user_id"),
                action_type,
                module_name,
                table_name,
                record_id,
                description,
                timestamp,
                timestamp,
            ],
        )
