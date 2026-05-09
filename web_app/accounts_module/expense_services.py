from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import create_journal_entry, reverse_journal_entry
from accounts_module.accounting_utils import ensure_default_chart_of_accounts, get_system_account
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from masters.master_utils import paginate
from settings_module.services import get_numbering_settings, log_user_activity, now_text


PAYMENT_MODES = ["Cash", "Bank", "Cheque", "Online Transfer"]
STATUSES = ["Posted", "Cancelled"]


def table_exists():
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expense_vouchers'")
        return cursor.fetchone() is not None


def today_iso():
    return date.today().isoformat()


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def generate_voucher_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("expense_voucher_prefix") or "EXP"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute("SELECT voucher_no FROM expense_vouchers WHERE company_id=%s AND branch_id=%s AND voucher_no LIKE %s ORDER BY voucher_no DESC LIMIT 1", [company_id, branch_id, f"{doc_prefix}%"])
        row = cursor.fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            number = 1
    return f"{doc_prefix}{number:0{padding}d}"


def list_vouchers(company_id, branch_id, filters, page):
    if not table_exists():
        return [], 0
    clauses = ["ev.company_id=%s", "ev.branch_id=%s"]
    params = [company_id, branch_id]
    if filters.get("q"):
        like = f"%{filters['q']}%"
        clauses.append("(ev.voucher_no LIKE %s OR eh.expense_name LIKE %s OR ev.cheque_reference_no LIKE %s OR ev.remarks LIKE %s)")
        params.extend([like, like, like, like])
    for key, col in [("expense_head", "ev.expense_head_id"), ("payment_mode", "ev.payment_mode"), ("status", "ev.status")]:
        if filters.get(key):
            clauses.append(f"{col}=%s")
            params.append(filters[key])
    if filters.get("date_from"):
        clauses.append("ev.voucher_date >= %s")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("ev.voucher_date <= %s")
        params.append(filters["date_to"])
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM expense_vouchers ev LEFT JOIN expense_heads eh ON eh.id=ev.expense_head_id WHERE {where_sql}", params)
        total = int(cursor.fetchone()[0] or 0)
        page_data = paginate(total, page)
        cursor.execute(
            f"""
            SELECT ev.*, eh.expense_name, cb.account_name AS cash_bank_name, rev.id AS reversal_id
            FROM expense_vouchers ev
            LEFT JOIN expense_heads eh ON eh.id=ev.expense_head_id
            LEFT JOIN cash_bank_accounts cb ON cb.id=ev.cash_bank_account_id
            LEFT JOIN journal_entries rev ON rev.reference_type='expense_voucher_cancel' AND rev.reference_id=ev.id
            WHERE {where_sql}
            ORDER BY ev.voucher_date DESC, ev.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_data["per_page"], page_data["offset"]],
        )
        return dictfetchall(cursor), total


def get_expense_heads(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, expense_code, expense_name, account_id FROM expense_heads WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY expense_name", [company_id, branch_id])
        return dictfetchall(cursor)


def get_cash_bank_accounts(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, account_name, account_type, account_id FROM cash_bank_accounts WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY account_name", [company_id, branch_id])
        return dictfetchall(cursor)


def default_form_data(company_id, branch_id):
    return {"voucher_no": generate_voucher_no(company_id, branch_id), "voucher_date": today_iso(), "expense_head_id": "", "cash_bank_account_id": "", "payment_mode": "Cash", "cheque_reference_no": "", "amount": "0.00", "tax_percent": "0", "tax_amount": "0.00", "total_amount": "0.00", "remarks": "", "status": "Posted"}


def parse_post(post):
    return {key: post.get(key, "") for key in ["voucher_no", "voucher_date", "expense_head_id", "cash_bank_account_id", "payment_mode", "cheque_reference_no", "amount", "tax_percent", "remarks"]}


def get_expense_head(company_id, branch_id, record_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM expense_heads WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [record_id, company_id, branch_id])
        return dictfetchone(cursor)


def get_cash_bank(company_id, branch_id, record_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM cash_bank_accounts WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [record_id, company_id, branch_id])
        return dictfetchone(cursor)


def voucher_no_exists(company_id, branch_id, voucher_no, exclude_id=None):
    params = [company_id, branch_id, voucher_no]
    clause = "company_id=%s AND branch_id=%s AND lower(voucher_no)=lower(%s)"
    if exclude_id:
        clause += " AND id<>%s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM expense_vouchers WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_and_calculate(data, company_id, branch_id, voucher_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["voucher_no"], errors["voucher_no"] = validators.clean_text(data.get("voucher_no"), max_length=50, required=True, field_name="Voucher No")
    if not errors["voucher_no"] and voucher_no_exists(company_id, branch_id, cleaned["voucher_no"], voucher_id):
        errors["voucher_no"] = "Voucher No already exists for the current branch."
    voucher_date, errors["voucher_date"] = validators.validate_date(data.get("voucher_date"), "Voucher Date", required=True)
    cleaned["voucher_date"] = voucher_date.isoformat() if voucher_date else ""
    errors["payment_mode"] = validators.validate_choice(data.get("payment_mode"), PAYMENT_MODES, "Payment Mode")
    cleaned["payment_mode"] = data.get("payment_mode")
    cleaned["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
    if cleaned["payment_mode"] == "Cheque" and not cleaned["cheque_reference_no"]:
        errors["cheque_reference_no"] = "Reference No is required for cheque payments."
    amount, errors["amount"] = validators.validate_money(data.get("amount"), "Amount", allow_zero=False, required=True)
    tax_percent, errors["tax_percent"] = validators.validate_percentage(data.get("tax_percent"), "Tax Percent")
    cleaned["amount"] = amount or Decimal("0.00")
    cleaned["tax_percent"] = tax_percent or Decimal("0.00")
    cleaned["tax_amount"] = (cleaned["amount"] * cleaned["tax_percent"] / Decimal("100")).quantize(Decimal("0.01"))
    cleaned["total_amount"] = cleaned["amount"] + cleaned["tax_amount"]
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
    expense_head = get_expense_head(company_id, branch_id, data.get("expense_head_id"))
    if not expense_head:
        errors["expense_head_id"] = "Select a valid active expense head."
    elif not expense_head.get("account_id"):
        errors["expense_head_id"] = "Selected expense head does not have a linked account."
    cash_bank = get_cash_bank(company_id, branch_id, data.get("cash_bank_account_id"))
    if not cash_bank:
        errors["cash_bank_account_id"] = "Select a valid active cash/bank account."
    elif not cash_bank.get("account_id"):
        errors["cash_bank_account_id"] = "Selected cash/bank account does not have a linked account."
    cleaned["expense_head_id"] = expense_head["id"] if expense_head else ""
    cleaned["expense_account_id"] = expense_head.get("account_id") if expense_head else None
    cleaned["cash_bank_account_id"] = cash_bank["id"] if cash_bank else ""
    cleaned["cash_bank_linked_account_id"] = cash_bank.get("account_id") if cash_bank else None
    cleaned["status"] = "Posted"
    return {k: v for k, v in errors.items() if v}, cleaned


def save_voucher(company_id, branch_id, user_id, data, voucher_id=None):
    timestamp = now_text()
    if voucher_id:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE expense_vouchers SET cheque_reference_no=%s, remarks=%s, updated_by_id=%s, updated_at=%s WHERE id=%s AND company_id=%s AND branch_id=%s", [data.get("cheque_reference_no"), data.get("remarks"), user_id, timestamp, voucher_id, company_id, branch_id])
        return voucher_id
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO expense_vouchers (
                    company_id, branch_id, voucher_no, voucher_date, expense_head_id, cash_bank_account_id,
                    payment_mode, cheque_reference_no, amount, tax_percent, tax_amount, total_amount, status,
                    journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Posted',NULL,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, data["voucher_no"], data["voucher_date"], data["expense_head_id"], data["cash_bank_account_id"], data["payment_mode"], data.get("cheque_reference_no"), str(data["amount"]), str(data["tax_percent"]), str(data["tax_amount"]), str(data["total_amount"]), data.get("remarks"), user_id, user_id, timestamp, timestamp],
            )
            saved_id = cursor.lastrowid
            journal_id = post_expense_voucher(company_id, branch_id, data, saved_id, user_id)
            cursor.execute("UPDATE expense_vouchers SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
    return saved_id


def post_expense_voucher(company_id, branch_id, data, voucher_id, user_id):
    ensure_default_chart_of_accounts(company_id, branch_id)
    lines = [{"account_id": data["expense_account_id"], "debit": data["amount"], "credit": 0, "description": "Expense voucher"}]
    if data["tax_amount"] > 0:
        tax_account = get_system_account(company_id, branch_id, "Input Tax Receivable")
        if not tax_account:
            raise ValueError("Input Tax Receivable account was not found.")
        lines.append({"account_id": tax_account["id"], "debit": data["tax_amount"], "credit": 0, "description": "Input tax on expense"})
    lines.append({"account_id": data["cash_bank_linked_account_id"], "debit": 0, "credit": data["total_amount"], "description": "Expense payment"})
    return create_journal_entry(company_id, branch_id, data["voucher_date"], "expense_voucher", voucher_id, "Expense voucher posting", lines, user_id)


def get_voucher(company_id, branch_id, voucher_id):
    if not table_exists():
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ev.*, eh.expense_name, cb.account_name AS cash_bank_name, je.entry_no AS journal_entry_no,
                   rev.id AS reversal_id
            FROM expense_vouchers ev
            LEFT JOIN expense_heads eh ON eh.id=ev.expense_head_id
            LEFT JOIN cash_bank_accounts cb ON cb.id=ev.cash_bank_account_id
            LEFT JOIN journal_entries je ON je.id=ev.journal_entry_id
            LEFT JOIN journal_entries rev ON rev.reference_type='expense_voucher_cancel' AND rev.reference_id=ev.id
            WHERE ev.id=%s AND ev.company_id=%s AND ev.branch_id=%s
            LIMIT 1
            """,
            [voucher_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def cancel_voucher(request, voucher):
    if voucher.get("reversal_id"):
        raise ValueError("This expense voucher already has a cancellation reversal journal.")
    user_id = request.session.get("user_id")
    timestamp = now_text()
    with transaction.atomic():
        reversal_id = reverse_journal_entry(voucher["journal_entry_id"], today_iso(), f"Cancel expense voucher {voucher['voucher_no']}", user_id)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE journal_entries SET reference_type='expense_voucher_cancel', reference_id=%s, description=%s, updated_at=%s WHERE id=%s", [voucher["id"], f"Cancellation reversal for expense voucher {voucher['voucher_no']}", timestamp, reversal_id])
            cursor.execute("UPDATE expense_vouchers SET status='Cancelled', updated_by_id=%s, updated_at=%s WHERE id=%s", [user_id, timestamp, voucher["id"]])
    log_user_activity(request, "CANCEL", "Expense Vouchers", "expense_vouchers", voucher["id"], f"Cancelled expense voucher {voucher['voucher_no']}.")


def mark_printed(request, voucher):
    log_user_activity(request, "PRINT", "Expense Vouchers", "expense_vouchers", voucher["id"], f"Printed expense voucher {voucher['voucher_no']}.")
