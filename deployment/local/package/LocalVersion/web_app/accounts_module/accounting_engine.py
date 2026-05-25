from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import connection, transaction

from .accounting_utils import (
    account_belongs_to_scope,
    ensure_default_chart_of_accounts,
    get_account_by_id,
    get_system_account,
    log_accounting_activity,
    now_iso,
)


class AccountingError(Exception):
    pass


def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise AccountingError("Invalid money value.")


def generate_journal_entry_no(company_id, branch_id):
    year = now_iso()[:4]
    prefix = f"JE-{year}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT entry_no
            FROM journal_entries
            WHERE company_id = %s
              AND branch_id = %s
              AND entry_no LIKE %s
            ORDER BY entry_no DESC
            LIMIT 1
            """,
            [company_id, branch_id, f"{prefix}%"],
        )
        row = cursor.fetchone()
    next_no = 1
    if row:
        try:
            next_no = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            next_no = 1
    return f"{prefix}{next_no:06d}"


def validate_journal_lines(company_id, branch_id, entry_date, lines):
    if not entry_date:
        raise AccountingError("Entry date is required.")
    if not lines or len(lines) < 2:
        raise AccountingError("At least two journal lines are required.")

    clean_lines = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for line in lines:
        account_id = line.get("account_id")
        if not account_id:
            raise AccountingError("Each journal line must have an account.")
        account = get_account_by_id(account_id)
        if not account:
            raise AccountingError("Journal line account was not found.")
        if not account_belongs_to_scope(account, company_id, branch_id):
            raise AccountingError("Journal line account does not belong to the current company/branch.")
        if int(account.get("is_control_account") or 0) == 1:
            raise AccountingError("Cannot post journal entry to a control account. Please select a posting account.")
        debit = money(line.get("debit"))
        credit = money(line.get("credit"))
        if debit < 0 or credit < 0:
            raise AccountingError("Debit and credit cannot be negative.")
        if debit > 0 and credit > 0:
            raise AccountingError("A journal line cannot have both debit and credit.")
        if debit == 0 and credit == 0:
            raise AccountingError("A journal line must have either debit or credit.")
        total_debit += debit
        total_credit += credit
        clean_lines.append(
            {
                "account_id": account_id,
                "debit": debit,
                "credit": credit,
                "description": line.get("description", ""),
            }
        )

    if total_debit <= 0:
        raise AccountingError("Journal entry total must be greater than zero.")
    if total_debit != total_credit:
        raise AccountingError("Journal entry is not balanced.")
    return clean_lines, total_debit, total_credit


def create_journal_entry(
    company_id,
    branch_id,
    entry_date,
    reference_type,
    reference_id,
    description,
    lines,
    created_by_id=None,
):
    clean_lines, total_debit, total_credit = validate_journal_lines(
        company_id,
        branch_id,
        entry_date,
        lines,
    )
    timestamp = now_iso()
    with transaction.atomic():
        entry_no = generate_journal_entry_no(company_id, branch_id)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO journal_entries (
                    company_id, branch_id, entry_no, entry_date, reference_type,
                    reference_id, description, created_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    branch_id,
                    entry_no,
                    entry_date,
                    reference_type,
                    reference_id,
                    description,
                    created_by_id,
                    timestamp,
                    timestamp,
                ],
            )
            journal_entry_id = cursor.lastrowid
            for line in clean_lines:
                cursor.execute(
                    """
                    INSERT INTO journal_entry_lines (
                        journal_entry_id, account_id, debit, credit, description,
                        created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        journal_entry_id,
                        line["account_id"],
                        str(line["debit"]),
                        str(line["credit"]),
                        line["description"],
                        timestamp,
                        timestamp,
                    ],
                )
        if created_by_id:
            log_accounting_activity(
                company_id,
                branch_id,
                created_by_id,
                "CREATE",
                journal_entry_id,
                f"Created journal entry {entry_no}.",
            )
    return journal_entry_id


def reverse_journal_entry(journal_entry_id, reversal_date, description, created_by_id=None):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM journal_entries WHERE id = %s LIMIT 1", [journal_entry_id])
        entry = cursor.fetchone()
        if not entry:
            raise AccountingError("Original journal entry was not found.")
        columns = [column[0] for column in cursor.description]
        original = dict(zip(columns, entry))
        cursor.execute(
            "SELECT account_id, debit, credit, description FROM journal_entry_lines WHERE journal_entry_id = %s",
            [journal_entry_id],
        )
        lines = [
            {
                "account_id": row[0],
                "debit": money(row[2]),
                "credit": money(row[1]),
                "description": f"Reversal: {row[3] or ''}".strip(),
            }
            for row in cursor.fetchall()
        ]
    return create_journal_entry(
        original["company_id"],
        original["branch_id"],
        reversal_date,
        "journal_reversal",
        journal_entry_id,
        description,
        lines,
        created_by_id,
    )


def account_id(company_id, branch_id, account_name):
    account = get_system_account(company_id, branch_id, account_name)
    if not account:
        raise AccountingError(f"Required account '{account_name}' was not found.")
    return account["id"]


def post_sales_invoice_entry(company_id, branch_id, customer_account_id, invoice_date, invoice_id, subtotal, discount_total, tax_total, grand_total, created_by_id=None):
    ensure_default_chart_of_accounts(company_id, branch_id)
    net_sales = money(subtotal) - money(discount_total)
    lines = [{"account_id": customer_account_id, "debit": grand_total, "credit": 0, "description": "Sales invoice receivable"}, {"account_id": account_id(company_id, branch_id, "Sales"), "debit": 0, "credit": net_sales, "description": "Sales revenue"}]
    if money(tax_total) > 0:
        lines.append({"account_id": account_id(company_id, branch_id, "Output Tax Payable"), "debit": 0, "credit": tax_total, "description": "Output tax"})
    return create_journal_entry(company_id, branch_id, invoice_date, "sales_invoice", invoice_id, "Sales invoice posting", lines, created_by_id)


def post_customer_receipt_entry(company_id, branch_id, cash_bank_account_id, customer_account_id, receipt_date, receipt_id, amount, created_by_id=None):
    lines = [{"account_id": cash_bank_account_id, "debit": amount, "credit": 0, "description": "Customer receipt"}, {"account_id": customer_account_id, "debit": 0, "credit": amount, "description": "Customer receivable settled"}]
    return create_journal_entry(company_id, branch_id, receipt_date, "customer_receipt", receipt_id, "Customer receipt posting", lines, created_by_id)


def post_supplier_purchase_entry(company_id, branch_id, supplier_account_id, purchase_date, purchase_id, subtotal, tax_total, grand_total, created_by_id=None):
    ensure_default_chart_of_accounts(company_id, branch_id)
    lines = [{"account_id": account_id(company_id, branch_id, "Purchases / Cost of Goods"), "debit": subtotal, "credit": 0, "description": "Purchase cost"}]
    if money(tax_total) > 0:
        lines.append({"account_id": account_id(company_id, branch_id, "Input Tax Receivable"), "debit": tax_total, "credit": 0, "description": "Input tax"})
    lines.append({"account_id": supplier_account_id, "debit": 0, "credit": grand_total, "description": "Supplier payable"})
    return create_journal_entry(company_id, branch_id, purchase_date, "supplier_purchase", purchase_id, "Supplier purchase posting", lines, created_by_id)


def post_supplier_payment_entry(company_id, branch_id, supplier_account_id, cash_bank_account_id, payment_date, payment_id, amount, created_by_id=None):
    lines = [{"account_id": supplier_account_id, "debit": amount, "credit": 0, "description": "Supplier payable settled"}, {"account_id": cash_bank_account_id, "debit": 0, "credit": amount, "description": "Supplier payment"}]
    return create_journal_entry(company_id, branch_id, payment_date, "supplier_payment", payment_id, "Supplier payment posting", lines, created_by_id)


def post_sales_return_entry(company_id, branch_id, customer_account_id, return_date, sales_return_id, subtotal, discount_total, tax_total, grand_total, created_by_id=None):
    ensure_default_chart_of_accounts(company_id, branch_id)
    net_return = money(subtotal) - money(discount_total)
    lines = [{"account_id": account_id(company_id, branch_id, "Sales Returns"), "debit": net_return, "credit": 0, "description": "Sales return"}]
    if money(tax_total) > 0:
        lines.append({"account_id": account_id(company_id, branch_id, "Output Tax Payable"), "debit": tax_total, "credit": 0, "description": "Output tax reversal"})
    lines.append({"account_id": customer_account_id, "debit": 0, "credit": grand_total, "description": "Customer receivable reduced"})
    return create_journal_entry(company_id, branch_id, return_date, "sales_return", sales_return_id, "Sales return posting", lines, created_by_id)


def post_purchase_return_entry(company_id, branch_id, supplier_account_id, return_date, purchase_return_id, subtotal, tax_total, grand_total, created_by_id=None):
    ensure_default_chart_of_accounts(company_id, branch_id)
    lines = [{"account_id": supplier_account_id, "debit": grand_total, "credit": 0, "description": "Supplier payable reduced"}, {"account_id": account_id(company_id, branch_id, "Purchase Returns"), "debit": 0, "credit": subtotal, "description": "Purchase return"}]
    if money(tax_total) > 0:
        lines.append({"account_id": account_id(company_id, branch_id, "Input Tax Receivable"), "debit": 0, "credit": tax_total, "description": "Input tax reversal"})
    return create_journal_entry(company_id, branch_id, return_date, "purchase_return", purchase_return_id, "Purchase return posting", lines, created_by_id)


def post_expense_entry(company_id, branch_id, expense_account_id, cash_bank_account_id, expense_date, expense_id, amount, created_by_id=None):
    lines = [{"account_id": expense_account_id, "debit": amount, "credit": 0, "description": "Expense"}, {"account_id": cash_bank_account_id, "debit": 0, "credit": amount, "description": "Expense payment"}]
    return create_journal_entry(company_id, branch_id, expense_date, "expense_voucher", expense_id, "Expense voucher posting", lines, created_by_id)
