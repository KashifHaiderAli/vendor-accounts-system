from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import AccountingError, post_supplier_payment_entry, reverse_journal_entry
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


def generate_payment_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("supplier_payment_prefix") or "SPV"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT payment_no
            FROM supplier_payments
            WHERE company_id = %s AND branch_id = %s AND payment_no LIKE %s
            ORDER BY payment_no DESC
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


def list_payments(company_id, branch_id, search="", payment_mode="", date_from="", date_to="", page=1):
    clauses = ["spay.company_id = %s", "spay.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(spay.payment_no LIKE %s OR s.supplier_name LIKE %s OR spay.cheque_reference_no LIKE %s OR sp.purchase_no LIKE %s)")
        params.extend([like, like, like, like])
    if payment_mode:
        clauses.append("spay.payment_mode = %s")
        params.append(payment_mode)
    if date_from:
        clauses.append("spay.payment_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("spay.payment_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM supplier_payments spay
            LEFT JOIN suppliers s ON s.id = spay.supplier_id
            LEFT JOIN supplier_purchases sp ON sp.id = spay.adjusted_purchase_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT spay.*, s.supplier_name, cb.account_name AS cash_bank_name,
                   sp.purchase_no, je.id AS reversal_id
            FROM supplier_payments spay
            LEFT JOIN suppliers s ON s.id = spay.supplier_id
            LEFT JOIN cash_bank_accounts cb ON cb.id = spay.cash_bank_account_id
            LEFT JOIN supplier_purchases sp ON sp.id = spay.adjusted_purchase_id
            LEFT JOIN journal_entries je ON je.reference_type = 'supplier_payment_cancel' AND je.reference_id = spay.id
            WHERE {where_sql}
            ORDER BY spay.payment_date DESC, spay.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_suppliers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, supplier_code, supplier_name, account_id
            FROM suppliers
            WHERE company_id=%s AND branch_id=%s AND is_active=1
            ORDER BY supplier_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_supplier(company_id, branch_id, supplier_id):
    if not supplier_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM suppliers WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [supplier_id, company_id, branch_id])
        return dictfetchone(cursor)


def get_cash_bank_accounts(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, account_name, account_type, account_id
            FROM cash_bank_accounts
            WHERE company_id=%s AND branch_id=%s AND is_active=1
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


def get_open_purchases(company_id, branch_id, supplier_id=None):
    clauses = ["company_id=%s", "branch_id=%s", "status <> 'Cancelled'", "balance_amount > 0"]
    params = [company_id, branch_id]
    if supplier_id:
        clauses.append("supplier_id=%s")
        params.append(supplier_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, purchase_no, purchase_date, grand_total, paid_amount, balance_amount, status, supplier_id
            FROM supplier_purchases
            WHERE {" AND ".join(clauses)}
            ORDER BY purchase_date DESC, id DESC
            """,
            params,
        )
        return dictfetchall(cursor)


def get_purchase(company_id, branch_id, purchase_id, supplier_id=None):
    if not purchase_id:
        return None
    clauses = ["sp.id=%s", "sp.company_id=%s", "sp.branch_id=%s", "sp.status <> 'Cancelled'"]
    params = [purchase_id, company_id, branch_id]
    if supplier_id:
        clauses.append("sp.supplier_id=%s")
        params.append(supplier_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sp.*, s.supplier_name
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id = sp.supplier_id
            WHERE {" AND ".join(clauses)}
            LIMIT 1
            """,
            params,
        )
        return dictfetchone(cursor)


def payment_no_exists(company_id, branch_id, payment_no, exclude_id=None):
    params = [company_id, branch_id, payment_no]
    clause = "company_id=%s AND branch_id=%s AND lower(payment_no)=lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM supplier_payments WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def default_form_data(company_id, branch_id, purchase=None):
    return {
        "payment_no": generate_payment_no(company_id, branch_id),
        "payment_date": today_iso(),
        "supplier_id": purchase.get("supplier_id") if purchase else "",
        "payment_mode": "Cash",
        "cash_bank_account_id": "",
        "cheque_reference_no": "",
        "amount": format_money(purchase.get("balance_amount")) if purchase else "0.00",
        "adjusted_purchase_id": purchase.get("id") if purchase else "",
        "remarks": "",
    }


def parse_post(post):
    return {
        "payment_no": post.get("payment_no", ""),
        "payment_date": post.get("payment_date", ""),
        "supplier_id": post.get("supplier_id", ""),
        "payment_mode": post.get("payment_mode", ""),
        "cash_bank_account_id": post.get("cash_bank_account_id", ""),
        "cheque_reference_no": post.get("cheque_reference_no", ""),
        "amount": post.get("amount", ""),
        "adjusted_purchase_id": post.get("adjusted_purchase_id", ""),
        "remarks": post.get("remarks", ""),
    }


def validate_and_clean(data, company_id, branch_id, payment_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["payment_no"], errors["payment_no"] = validators.clean_text(data.get("payment_no"), max_length=50, required=True, field_name="Payment No")
    if not errors["payment_no"] and payment_no_exists(company_id, branch_id, cleaned["payment_no"], payment_id):
        errors["payment_no"] = "Payment No already exists for the current branch."
    payment_date, errors["payment_date"] = validators.validate_date(data.get("payment_date"), "Payment Date", required=True)
    cleaned["payment_date"] = payment_date.isoformat() if payment_date else ""
    errors["payment_mode"] = validators.validate_choice(data.get("payment_mode"), PAYMENT_MODES, "Payment Mode")
    cleaned["payment_mode"] = str(data.get("payment_mode") or "").strip()
    cleaned["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
    if cleaned["payment_mode"] == "Cheque" and not cleaned["cheque_reference_no"]:
        errors["cheque_reference_no"] = "Reference No is required for cheque payments."
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")

    supplier = get_supplier(company_id, branch_id, data.get("supplier_id"))
    if not supplier:
        errors["supplier_id"] = "Select a valid active supplier."
    elif not supplier.get("account_id"):
        errors["supplier_id"] = "Selected supplier does not have a linked payable account."
    cleaned["supplier_id"] = supplier["id"] if supplier else ""
    cleaned["supplier_account_id"] = supplier.get("account_id") if supplier else None

    cash_bank = get_cash_bank_account(company_id, branch_id, data.get("cash_bank_account_id"))
    if not cash_bank:
        errors["cash_bank_account_id"] = "Select a valid active cash/bank account."
    elif not cash_bank.get("account_id"):
        errors["cash_bank_account_id"] = "Selected cash/bank account does not have a linked account."
    cleaned["cash_bank_account_id"] = cash_bank["id"] if cash_bank else ""
    cleaned["cash_bank_linked_account_id"] = cash_bank.get("account_id") if cash_bank else None

    amount, errors["amount"] = validators.validate_money(data.get("amount"), "Amount", allow_zero=False, required=True)
    cleaned["amount"] = amount or Decimal("0.00")

    purchase = get_purchase(company_id, branch_id, data.get("adjusted_purchase_id"), supplier["id"] if supplier else None) if data.get("adjusted_purchase_id") else None
    if data.get("adjusted_purchase_id") and not purchase:
        errors["adjusted_purchase_id"] = "Select a valid unpaid purchase for this supplier."
    elif purchase and amount and amount > money(purchase.get("balance_amount")):
        errors["amount"] = "Payment amount cannot be greater than the selected purchase balance."
    cleaned["adjusted_purchase_id"] = purchase["id"] if purchase else None

    return {key: value for key, value in errors.items() if value}, cleaned


def save_payment(company_id, branch_id, user_id, data, payment_id=None):
    timestamp = now_text()
    if payment_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE supplier_payments
                SET cheque_reference_no=%s, remarks=%s, updated_by_id=%s, updated_at=%s
                WHERE id=%s AND company_id=%s AND branch_id=%s
                """,
                [data.get("cheque_reference_no"), data.get("remarks"), user_id, timestamp, payment_id, company_id, branch_id],
            )
        return payment_id

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO supplier_payments (
                    company_id, branch_id, payment_no, payment_date, supplier_id, payment_mode,
                    cash_bank_account_id, cheque_reference_no, amount, adjusted_purchase_id,
                    journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    branch_id,
                    data["payment_no"],
                    data["payment_date"],
                    data["supplier_id"],
                    data["payment_mode"],
                    data["cash_bank_account_id"],
                    data.get("cheque_reference_no"),
                    str(data["amount"]),
                    data.get("adjusted_purchase_id"),
                    data.get("remarks"),
                    user_id,
                    user_id,
                    timestamp,
                    timestamp,
                ],
            )
            saved_id = cursor.lastrowid
            journal_id = post_supplier_payment_entry(
                company_id,
                branch_id,
                data["supplier_account_id"],
                data["cash_bank_linked_account_id"],
                data["payment_date"],
                saved_id,
                data["amount"],
                user_id,
            )
            cursor.execute("UPDATE supplier_payments SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
            if data.get("adjusted_purchase_id"):
                update_purchase_balance(cursor, data["adjusted_purchase_id"], data["amount"], user_id, timestamp, subtract=False)
    return saved_id


def update_purchase_balance(cursor, purchase_id, amount, user_id, timestamp, subtract=False):
    cursor.execute("SELECT id, grand_total, paid_amount FROM supplier_purchases WHERE id=%s LIMIT 1", [purchase_id])
    row = cursor.fetchone()
    if not row:
        return
    grand_total = money(row[1])
    paid = money(row[2]) - money(amount) if subtract else money(row[2]) + money(amount)
    if paid < 0:
        paid = Decimal("0.00")
    balance = grand_total - paid
    if balance < 0:
        balance = Decimal("0.00")
    status = "Paid" if balance <= 0 else ("Partially Paid" if paid > 0 else "Unpaid")
    cursor.execute(
        """
        UPDATE supplier_purchases
        SET paid_amount=%s, balance_amount=%s, status=%s, updated_by_id=%s, updated_at=%s
        WHERE id=%s
        """,
        [str(paid), str(balance), status, user_id, timestamp, purchase_id],
    )


def get_payment(company_id, branch_id, payment_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT spay.*, s.supplier_name, s.contact_person AS supplier_contact_person,
                   s.phone AS supplier_phone, s.mobile AS supplier_mobile, s.email AS supplier_email,
                   s.address AS supplier_address, cb.account_name AS cash_bank_name, cb.account_type AS cash_bank_type,
                   sp.purchase_no, sp.balance_amount AS purchase_balance, je.entry_no AS journal_entry_no,
                   rev.id AS reversal_id
            FROM supplier_payments spay
            LEFT JOIN suppliers s ON s.id = spay.supplier_id
            LEFT JOIN cash_bank_accounts cb ON cb.id = spay.cash_bank_account_id
            LEFT JOIN supplier_purchases sp ON sp.id = spay.adjusted_purchase_id
            LEFT JOIN journal_entries je ON je.id = spay.journal_entry_id
            LEFT JOIN journal_entries rev ON rev.reference_type = 'supplier_payment_cancel' AND rev.reference_id = spay.id
            WHERE spay.id=%s AND spay.company_id=%s AND spay.branch_id=%s
            LIMIT 1
            """,
            [payment_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def payment_has_reversal(payment_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM journal_entries WHERE reference_type='supplier_payment_cancel' AND reference_id=%s LIMIT 1", [payment_id])
        return cursor.fetchone() is not None


def cancel_payment(request, payment):
    if payment_has_reversal(payment["id"]):
        raise ValueError("This payment already has a cancellation reversal journal.")
    if not payment.get("journal_entry_id"):
        raise AccountingError("Payment journal entry was not found.")
    user_id = request.session.get("user_id")
    timestamp = now_text()
    with transaction.atomic():
        reversal_id = reverse_journal_entry(payment["journal_entry_id"], today_iso(), f"Cancel supplier payment {payment['payment_no']}", user_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE journal_entries SET reference_type='supplier_payment_cancel', reference_id=%s, description=%s, updated_at=%s WHERE id=%s",
                [payment["id"], f"Cancellation reversal for supplier payment {payment['payment_no']}", timestamp, reversal_id],
            )
            if payment.get("adjusted_purchase_id"):
                update_purchase_balance(cursor, payment["adjusted_purchase_id"], payment["amount"], user_id, timestamp, subtract=True)
    log_user_activity(request, "CANCEL", "Supplier Payments", "supplier_payments", payment["id"], f"Cancelled/reversed supplier payment {payment['payment_no']}.")
    return reversal_id


def mark_printed(request, payment):
    log_user_activity(request, "PRINT", "Supplier Payments", "supplier_payments", payment["id"], f"Printed supplier payment {payment['payment_no']}.")


def get_print_context(company_id, branch_id, payment_id):
    payment = get_payment(company_id, branch_id, payment_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return {"payment": payment, "company": company, "branch": branch, "print_date": today_iso()}
