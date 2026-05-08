from __future__ import annotations

from decimal import Decimal

from django.db import connection

from authentication.auth_utils import dictfetchall


def get_trial_balance(company_id, branch_id, date_to=None):
    params = [company_id, branch_id]
    date_clause = ""
    if date_to:
        date_clause = "AND je.entry_date <= %s"
        params.append(date_to)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                a.id AS account_id,
                a.account_code,
                a.account_name,
                a.account_type,
                COALESCE(SUM(jel.debit), 0) AS debit_total,
                COALESCE(SUM(jel.credit), 0) AS credit_total
            FROM accounts a
            LEFT JOIN journal_entry_lines jel ON jel.account_id = a.id
            LEFT JOIN journal_entries je ON je.id = jel.journal_entry_id
                AND je.company_id = %s
                AND je.branch_id = %s
                {date_clause}
            WHERE a.company_id = %s
              AND (a.branch_id = %s OR a.branch_id IS NULL)
            GROUP BY a.id, a.account_code, a.account_name, a.account_type
            ORDER BY a.account_type, a.account_code
            """,
            params + [company_id, branch_id],
        )
        rows = dictfetchall(cursor)
    for row in rows:
        debit = Decimal(str(row["debit_total"] or 0))
        credit = Decimal(str(row["credit_total"] or 0))
        balance = debit - credit
        row["balance_debit"] = balance if balance > 0 else Decimal("0.00")
        row["balance_credit"] = abs(balance) if balance < 0 else Decimal("0.00")
    return rows


def get_account_ledger(company_id, branch_id, account_id, date_from=None, date_to=None):
    params = [company_id, branch_id, account_id]
    clauses = ["je.company_id = %s", "je.branch_id = %s", "jel.account_id = %s"]
    if date_from:
        clauses.append("je.entry_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("je.entry_date <= %s")
        params.append(date_to)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                je.entry_date AS date,
                je.entry_no,
                je.reference_type,
                je.reference_id,
                COALESCE(jel.description, je.description) AS description,
                jel.debit,
                jel.credit
            FROM journal_entry_lines jel
            JOIN journal_entries je ON je.id = jel.journal_entry_id
            WHERE {' AND '.join(clauses)}
            ORDER BY je.entry_date, je.entry_no, jel.id
            """,
            params,
        )
        rows = dictfetchall(cursor)
    running = Decimal("0.00")
    for row in rows:
        running += Decimal(str(row["debit"] or 0)) - Decimal(str(row["credit"] or 0))
        row["running_balance"] = running
    return rows
