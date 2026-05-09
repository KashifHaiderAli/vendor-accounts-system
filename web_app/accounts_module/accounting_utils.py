from __future__ import annotations

from datetime import date

from django.db import connection

from authentication.auth_utils import dictfetchall, dictfetchone
from settings_module.services import now_text


DEFAULT_ACCOUNTS = [
    ("ASSET", "Assets", "Assets", None, 1),
    ("CASH", "Cash", "Assets", "Assets", 0),
    ("BANK", "Bank", "Assets", "Assets", 0),
    ("AR", "Accounts Receivable", "Assets", "Assets", 1),
    ("INPUT-TAX", "Input Tax Receivable", "Assets", "Assets", 0),
    ("LIABILITY", "Liabilities", "Liabilities", None, 1),
    ("AP", "Accounts Payable", "Liabilities", "Liabilities", 1),
    ("OUTPUT-TAX", "Output Tax Payable", "Liabilities", "Liabilities", 0),
    ("EQUITY", "Equity", "Equity", None, 1),
    ("CAPITAL", "Capital / Opening Balance", "Equity", "Equity", 0),
    ("INCOME", "Income", "Income", None, 1),
    ("SALES", "Sales", "Income", "Income", 0),
    ("SERVICE-INCOME", "Service Income", "Income", "Income", 0),
    ("EXPENSE", "Expenses", "Expenses", None, 1),
    ("PURCHASES", "Purchases / Cost of Goods", "Expenses", "Expenses", 0),
    ("OFFICE-EXP", "Office Expenses", "Expenses", "Expenses", 1),
    ("SALES-RETURN", "Sales Returns", "Expenses", "Expenses", 0),
    ("PURCHASE-RETURN", "Purchase Returns", "Expenses", "Expenses", 0),
]


def get_current_company_id(request):
    return request.session.get("company_id")


def get_current_branch_id(request):
    return request.session.get("current_branch_id")


def get_current_user_id(request):
    return request.session.get("user_id")


def now_iso():
    return now_text()


def today_iso():
    return date.today().isoformat()


def get_account_by_id(account_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM accounts WHERE id = %s LIMIT 1", [account_id])
        return dictfetchone(cursor)


def get_account_by_code(company_id, branch_id, account_code):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM accounts
            WHERE company_id = %s
              AND (branch_id = %s OR branch_id IS NULL)
              AND lower(account_code) = lower(%s)
            ORDER BY CASE WHEN branch_id = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            [company_id, branch_id, account_code, branch_id],
        )
        return dictfetchone(cursor)


def get_account_by_name(company_id, branch_id, account_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM accounts
            WHERE company_id = %s
              AND (branch_id = %s OR branch_id IS NULL)
              AND lower(account_name) = lower(%s)
            ORDER BY CASE WHEN branch_id = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            [company_id, branch_id, account_name, branch_id],
        )
        return dictfetchone(cursor)


def get_system_account(company_id, branch_id, account_name):
    account = get_account_by_name(company_id, branch_id, account_name)
    if account:
        return account
    return get_account_by_code(company_id, branch_id, account_name)


def find_or_create_system_account(
    company_id,
    branch_id,
    account_code,
    account_name,
    account_type,
    parent_id=None,
    is_control_account=0,
):
    existing = get_account_by_name(company_id, branch_id, account_name)
    if existing:
        update_account_flags(existing["id"], is_control_account, 1)
        return existing
    existing = get_account_by_code(company_id, branch_id, account_code)
    if existing:
        update_account_flags(existing["id"], is_control_account, 1)
        return existing

    timestamp = now_iso()
    final_code = unique_account_code(company_id, branch_id, account_code)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO accounts (
                company_id, branch_id, account_code, account_name, account_type,
                parent_id, is_control_account, is_system_account, is_active,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s)
            """,
            [
                company_id,
                branch_id,
                final_code,
                account_name,
                account_type,
                parent_id,
                is_control_account,
                timestamp,
                timestamp,
            ],
        )
        account_id = cursor.lastrowid
    return get_account_by_id(account_id)


def update_account_flags(account_id, is_control_account, is_system_account):
    timestamp = now_iso()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE accounts
            SET is_control_account = %s,
                is_system_account = %s,
                updated_at = %s
            WHERE id = %s
            """,
            [is_control_account, is_system_account, timestamp, account_id],
        )


def unique_account_code(company_id, branch_id, account_code):
    candidate = account_code
    counter = 2
    while get_account_by_code(company_id, branch_id, candidate):
        candidate = f"{account_code}-{counter}"
        counter += 1
    return candidate


def ensure_default_chart_of_accounts(company_id, branch_id):
    created = []
    by_name = {}
    for code, name, account_type, parent_name, is_control in DEFAULT_ACCOUNTS:
        parent_id = by_name.get(parent_name, {}).get("id") if parent_name else None
        if parent_name and not parent_id:
            parent = get_account_by_name(company_id, branch_id, parent_name)
            parent_id = parent["id"] if parent else None
        before = get_account_by_name(company_id, branch_id, name)
        account = find_or_create_system_account(
            company_id,
            branch_id,
            code,
            name,
            account_type,
            parent_id=parent_id,
            is_control_account=is_control,
        )
        by_name[name] = account
        if not before:
            created.append(account)
    return created


def account_belongs_to_scope(account, company_id, branch_id):
    if not account:
        return False
    return int(account["company_id"]) == int(company_id) and (
        account["branch_id"] is None or int(account["branch_id"]) == int(branch_id)
    )


def list_chart_accounts(company_id, branch_id, search="", account_type="", status="", limit=20, offset=0):
    params = [company_id, branch_id]
    clauses = ["a.company_id = %s", "(a.branch_id = %s OR a.branch_id IS NULL)"]
    if search:
        like = f"%{search}%"
        clauses.append("(a.account_code LIKE %s OR a.account_name LIKE %s)")
        params.extend([like, like])
    if account_type:
        clauses.append("a.account_type = %s")
        params.append(account_type)
    if status == "active":
        clauses.append("a.is_active = 1")
    elif status == "inactive":
        clauses.append("a.is_active = 0")
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM accounts a WHERE {where_sql}", params)
        total = int(cursor.fetchone()[0] or 0)
        cursor.execute(
            f"""
            SELECT a.*, p.account_name AS parent_account_name
            FROM accounts a
            LEFT JOIN accounts p ON p.id = a.parent_id
            WHERE {where_sql}
            ORDER BY a.account_type, a.account_code
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = dictfetchall(cursor)
    for row in rows:
        row["is_control_account"] = int(row.get("is_control_account") or 0)
        row["is_system_account"] = int(row.get("is_system_account") or 0)
    return rows, total


def account_types(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT account_type
            FROM accounts
            WHERE company_id = %s AND (branch_id = %s OR branch_id IS NULL)
            ORDER BY account_type
            """,
            [company_id, branch_id],
        )
        return [row[0] for row in cursor.fetchall()]


def log_accounting_activity(company_id, branch_id, user_id, action_type, record_id=None, description=None):
    timestamp = now_iso()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO user_activity_log (
                company_id, branch_id, user_id, action_type, module_name,
                table_name, record_id, description, activity_datetime, created_at
            )
            VALUES (%s, %s, %s, %s, 'Accounting', 'journal_entries', %s, %s, %s, %s)
            """,
            [company_id, branch_id, user_id, action_type, record_id, description, timestamp, timestamp],
        )
