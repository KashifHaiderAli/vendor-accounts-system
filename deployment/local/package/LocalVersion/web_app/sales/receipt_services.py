from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import AccountingError, post_customer_receipt_entry, reverse_journal_entry
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from settings_module.services import get_numbering_settings, log_user_activity, now_text


PER_PAGE = 20
PAYMENT_MODES = ["Cash", "Bank", "Cheque", "Online Transfer"]


def today_iso():
    return date.today().isoformat()


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def format_money(value):
    return str(money(value))


def paginate(total_count, page, per_page=PER_PAGE):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    return {"page": page, "per_page": per_page, "total_count": total_count, "total_pages": total_pages, "offset": (page - 1) * per_page, "pages": list(range(1, total_pages + 1))}


def generate_receipt_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("receipt_prefix") or "RCV"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT receipt_no
            FROM customer_receipts
            WHERE company_id = %s AND branch_id = %s AND receipt_no LIKE %s
            ORDER BY receipt_no DESC
            LIMIT 1
            """,
            [company_id, branch_id, f"{doc_prefix}%"],
        )
        row = cursor.fetchone()
    next_number = 1
    if row:
        try:
            next_number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            next_number = 1
    return f"{doc_prefix}{next_number:0{padding}d}"


def list_receipts(company_id, branch_id, search="", payment_mode="", date_from="", date_to="", page=1):
    clauses = ["cr.company_id = %s", "cr.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(cr.receipt_no LIKE %s OR c.company_name LIKE %s OR cr.cheque_reference_no LIKE %s OR si.invoice_no LIKE %s)")
        params.extend([like, like, like, like])
    if payment_mode:
        clauses.append("cr.payment_mode = %s")
        params.append(payment_mode)
    if date_from:
        clauses.append("cr.receipt_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("cr.receipt_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM customer_receipts cr
            LEFT JOIN customers c ON c.id = cr.customer_id
            LEFT JOIN sales_invoices si ON si.id = cr.adjusted_invoice_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT cr.*, c.company_name AS customer_name, cb.account_name AS cash_bank_name,
                   si.invoice_no, je.id AS reversal_id
            FROM customer_receipts cr
            LEFT JOIN customers c ON c.id = cr.customer_id
            LEFT JOIN cash_bank_accounts cb ON cb.id = cr.cash_bank_account_id
            LEFT JOIN sales_invoices si ON si.id = cr.adjusted_invoice_id
            LEFT JOIN journal_entries je ON je.reference_type = 'customer_receipt_cancel' AND je.reference_id = cr.id
            WHERE {where_sql}
            ORDER BY cr.receipt_date DESC, cr.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, customer_code, company_name, account_id
            FROM customers
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY company_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_customer(company_id, branch_id, customer_id):
    if not customer_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM customers WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [customer_id, company_id, branch_id])
        return dictfetchone(cursor)


def get_cash_bank_accounts(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, account_name, account_type, account_id
            FROM cash_bank_accounts
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY account_type, account_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_cash_bank_account(company_id, branch_id, record_id):
    if not record_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM cash_bank_accounts WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [record_id, company_id, branch_id])
        return dictfetchone(cursor)


def get_open_invoices(company_id, branch_id, customer_id=None):
    clauses = ["company_id = %s", "branch_id = %s", "status <> 'Cancelled'", "balance_amount > 0"]
    params = [company_id, branch_id]
    if customer_id:
        clauses.append("customer_id = %s")
        params.append(customer_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, invoice_no, invoice_date, grand_total, received_amount, balance_amount, status, customer_id
            FROM sales_invoices
            WHERE {" AND ".join(clauses)}
            ORDER BY invoice_date DESC, id DESC
            """,
            params,
        )
        return dictfetchall(cursor)


def get_invoice(company_id, branch_id, invoice_id, customer_id=None):
    if not invoice_id:
        return None
    clauses = ["si.id=%s", "si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'"]
    params = [invoice_id, company_id, branch_id]
    if customer_id:
        clauses.append("si.customer_id=%s")
        params.append(customer_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT si.*, c.company_name AS customer_name
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id = si.customer_id
            WHERE {" AND ".join(clauses)}
            LIMIT 1
            """,
            params,
        )
        return dictfetchone(cursor)


def receipt_no_exists(company_id, branch_id, receipt_no, exclude_id=None):
    params = [company_id, branch_id, receipt_no]
    clause = "company_id=%s AND branch_id=%s AND lower(receipt_no)=lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM customer_receipts WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def default_form_data(company_id, branch_id, invoice=None):
    return {
        "receipt_no": generate_receipt_no(company_id, branch_id),
        "receipt_date": today_iso(),
        "customer_id": invoice.get("customer_id") if invoice else "",
        "payment_mode": "Cash",
        "cash_bank_account_id": "",
        "cheque_reference_no": "",
        "amount": format_money(invoice.get("balance_amount")) if invoice else "0.00",
        "adjusted_invoice_id": invoice.get("id") if invoice else "",
        "remarks": "",
    }


def parse_post(post):
    return {
        "receipt_no": post.get("receipt_no", ""),
        "receipt_date": post.get("receipt_date", ""),
        "customer_id": post.get("customer_id", ""),
        "payment_mode": post.get("payment_mode", ""),
        "cash_bank_account_id": post.get("cash_bank_account_id", ""),
        "cheque_reference_no": post.get("cheque_reference_no", ""),
        "amount": post.get("amount", ""),
        "adjusted_invoice_id": post.get("adjusted_invoice_id", ""),
        "remarks": post.get("remarks", ""),
    }


def validate_and_clean(data, company_id, branch_id, receipt_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["receipt_no"], errors["receipt_no"] = validators.clean_text(data.get("receipt_no"), max_length=50, required=True, field_name="Receipt No")
    if not errors["receipt_no"] and receipt_no_exists(company_id, branch_id, cleaned["receipt_no"], receipt_id):
        errors["receipt_no"] = "Receipt No already exists for the current branch."
    receipt_date, errors["receipt_date"] = validators.validate_date(data.get("receipt_date"), "Receipt Date", required=True)
    cleaned["receipt_date"] = receipt_date.isoformat() if receipt_date else ""
    errors["payment_mode"] = validators.validate_choice(data.get("payment_mode"), PAYMENT_MODES, "Payment Mode")
    cleaned["payment_mode"] = str(data.get("payment_mode") or "").strip()
    cleaned["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
    if cleaned["payment_mode"] == "Cheque" and not cleaned["cheque_reference_no"]:
        errors["cheque_reference_no"] = "Reference No is required for cheque receipts."
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")

    customer = get_customer(company_id, branch_id, data.get("customer_id"))
    if not customer:
        errors["customer_id"] = "Select a valid active customer."
    elif not customer.get("account_id"):
        errors["customer_id"] = "Selected customer does not have a linked receivable account."
    cleaned["customer_id"] = customer["id"] if customer else ""
    cleaned["customer_account_id"] = customer.get("account_id") if customer else None

    cash_bank = get_cash_bank_account(company_id, branch_id, data.get("cash_bank_account_id"))
    if not cash_bank:
        errors["cash_bank_account_id"] = "Select a valid active cash/bank account."
    elif not cash_bank.get("account_id"):
        errors["cash_bank_account_id"] = "Selected cash/bank account does not have a linked account."
    cleaned["cash_bank_account_id"] = cash_bank["id"] if cash_bank else ""
    cleaned["cash_bank_linked_account_id"] = cash_bank.get("account_id") if cash_bank else None

    amount, errors["amount"] = validators.validate_money(data.get("amount"), "Amount", allow_zero=False, required=True)
    cleaned["amount"] = amount or Decimal("0.00")

    invoice = get_invoice(company_id, branch_id, data.get("adjusted_invoice_id"), customer["id"] if customer else None) if data.get("adjusted_invoice_id") else None
    if data.get("adjusted_invoice_id") and not invoice:
        errors["adjusted_invoice_id"] = "Select a valid unpaid invoice for this customer."
    elif invoice and amount and amount > money(invoice.get("balance_amount")):
        errors["amount"] = "Receipt amount cannot be greater than the selected invoice balance."
    cleaned["adjusted_invoice_id"] = invoice["id"] if invoice else None

    return {key: value for key, value in errors.items() if value}, cleaned


def save_receipt(company_id, branch_id, user_id, data, receipt_id=None):
    timestamp = now_text()
    if receipt_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE customer_receipts
                SET cheque_reference_no=%s, remarks=%s, updated_by_id=%s, updated_at=%s
                WHERE id=%s AND company_id=%s AND branch_id=%s
                """,
                [data.get("cheque_reference_no"), data.get("remarks"), user_id, timestamp, receipt_id, company_id, branch_id],
            )
        return receipt_id

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customer_receipts (
                    company_id, branch_id, receipt_no, receipt_date, customer_id, payment_mode,
                    cash_bank_account_id, cheque_reference_no, amount, adjusted_invoice_id,
                    journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    branch_id,
                    data["receipt_no"],
                    data["receipt_date"],
                    data["customer_id"],
                    data["payment_mode"],
                    data["cash_bank_account_id"],
                    data.get("cheque_reference_no"),
                    str(data["amount"]),
                    data.get("adjusted_invoice_id"),
                    data.get("remarks"),
                    user_id,
                    user_id,
                    timestamp,
                    timestamp,
                ],
            )
            saved_id = cursor.lastrowid
            journal_id = post_customer_receipt_entry(
                company_id,
                branch_id,
                data["cash_bank_linked_account_id"],
                data["customer_account_id"],
                data["receipt_date"],
                saved_id,
                data["amount"],
                user_id,
            )
            cursor.execute("UPDATE customer_receipts SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
            if data.get("adjusted_invoice_id"):
                update_invoice_balance(cursor, data["adjusted_invoice_id"], data["amount"], user_id, timestamp, subtract=False)
    return saved_id


def update_invoice_balance(cursor, invoice_id, amount, user_id, timestamp, subtract=False):
    cursor.execute("SELECT id, grand_total, received_amount, status FROM sales_invoices WHERE id=%s LIMIT 1", [invoice_id])
    row = cursor.fetchone()
    if not row:
        return
    grand_total = money(row[1])
    received = money(row[2]) - money(amount) if subtract else money(row[2]) + money(amount)
    if received < 0:
        received = Decimal("0.00")
    balance = grand_total - received
    if balance < 0:
        balance = Decimal("0.00")
    if balance <= 0:
        status = "Paid"
    elif received > 0:
        status = "Partially Paid"
    else:
        status = "Draft" if row[3] == "Draft" else "Printed"
    cursor.execute(
        """
        UPDATE sales_invoices
        SET received_amount=%s, balance_amount=%s, status=%s, updated_by_id=%s, updated_at=%s
        WHERE id=%s
        """,
        [str(received), str(balance), status, user_id, timestamp, invoice_id],
    )


def get_receipt(company_id, branch_id, receipt_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cr.*, c.company_name AS customer_name, c.contact_person AS customer_contact_person,
                   c.phone AS customer_phone, c.mobile AS customer_mobile, c.email AS customer_email,
                   c.address AS customer_address, cb.account_name AS cash_bank_name, cb.account_type AS cash_bank_type,
                   si.invoice_no, si.balance_amount AS invoice_balance, je.entry_no AS journal_entry_no,
                   rev.id AS reversal_id
            FROM customer_receipts cr
            LEFT JOIN customers c ON c.id = cr.customer_id
            LEFT JOIN cash_bank_accounts cb ON cb.id = cr.cash_bank_account_id
            LEFT JOIN sales_invoices si ON si.id = cr.adjusted_invoice_id
            LEFT JOIN journal_entries je ON je.id = cr.journal_entry_id
            LEFT JOIN journal_entries rev ON rev.reference_type = 'customer_receipt_cancel' AND rev.reference_id = cr.id
            WHERE cr.id=%s AND cr.company_id=%s AND cr.branch_id=%s
            LIMIT 1
            """,
            [receipt_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def receipt_has_reversal(receipt_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM journal_entries WHERE reference_type='customer_receipt_cancel' AND reference_id=%s LIMIT 1", [receipt_id])
        return cursor.fetchone() is not None


def cancel_receipt(request, receipt):
    if receipt_has_reversal(receipt["id"]):
        raise ValueError("This receipt already has a cancellation reversal journal.")
    if not receipt.get("journal_entry_id"):
        raise AccountingError("Receipt journal entry was not found.")
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    user_id = request.session.get("user_id")
    timestamp = now_text()
    with transaction.atomic():
        reversal_id = reverse_journal_entry(receipt["journal_entry_id"], today_iso(), f"Cancel customer receipt {receipt['receipt_no']}", user_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE journal_entries SET reference_type='customer_receipt_cancel', reference_id=%s, description=%s, updated_at=%s WHERE id=%s",
                [receipt["id"], f"Cancellation reversal for customer receipt {receipt['receipt_no']}", timestamp, reversal_id],
            )
            if receipt.get("adjusted_invoice_id"):
                update_invoice_balance(cursor, receipt["adjusted_invoice_id"], receipt["amount"], user_id, timestamp, subtract=True)
    log_user_activity(request, "CANCEL", "Customer Receipts", "customer_receipts", receipt["id"], f"Cancelled/reversed receipt {receipt['receipt_no']}.")
    return reversal_id


def mark_printed(request, receipt):
    log_user_activity(request, "PRINT", "Customer Receipts", "customer_receipts", receipt["id"], f"Printed receipt {receipt['receipt_no']}.")


def get_print_context(company_id, branch_id, receipt_id):
    receipt = get_receipt(company_id, branch_id, receipt_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return {"receipt": receipt, "company": company, "branch": branch, "print_date": today_iso()}
