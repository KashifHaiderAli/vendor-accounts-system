from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import AccountingError, post_supplier_purchase_entry, reverse_journal_entry
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from core.edition_utils import is_tax_enabled
from core.inventory_utils import post_supplier_purchase_stock, reverse_stock_movements
from settings_module.services import get_numbering_settings, log_user_activity, now_text


PER_PAGE = 20
PURCHASE_STATUSES = ["Unpaid", "Partially Paid", "Paid", "Cancelled"]


def today_iso():
    return date.today().isoformat()


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def format_money(value):
    return str(money(value))


def get_scope(request):
    return request.session.get("company_id"), request.session.get("current_branch_id")


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
    }


def generate_purchase_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("purchase_prefix") or "PUR"
    padding = int(settings.get("number_padding") or 4)
    use_year = int(settings.get("use_year_in_number") or 0) == 1
    doc_prefix = f"{prefix}-{date.today().year}-" if use_year else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT purchase_no
            FROM supplier_purchases
            WHERE company_id = %s AND branch_id = %s AND purchase_no LIKE %s
            ORDER BY purchase_no DESC
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


def list_purchases(company_id, branch_id, search="", status="", date_from="", date_to="", page=1):
    clauses = ["sp.company_id = %s", "sp.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(sp.purchase_no LIKE %s OR s.supplier_name LIKE %s OR sp.supplier_bill_no LIKE %s OR cc.confirmation_no LIKE %s)")
        params.extend([like, like, like, like])
    if status:
        clauses.append("sp.status = %s")
        params.append(status)
    if date_from:
        clauses.append("sp.purchase_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("sp.purchase_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id = sp.supplier_id
            LEFT JOIN customer_confirmations cc ON cc.id = sp.confirmation_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT sp.*, s.supplier_name, cc.confirmation_no
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id = sp.supplier_id
            LEFT JOIN customer_confirmations cc ON cc.id = sp.confirmation_id
            WHERE {where_sql}
            ORDER BY sp.purchase_date DESC, sp.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_suppliers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, supplier_code, supplier_name, account_id, contact_person, phone, mobile, email, address
            FROM suppliers
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY supplier_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_supplier(company_id, branch_id, supplier_id):
    if not supplier_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM suppliers WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [supplier_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def supplier_exists(company_id, branch_id, supplier_id):
    return get_supplier(company_id, branch_id, supplier_id) is not None


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, default_purchase_rate, default_tax_rate, warranty_or_service_description
            FROM item_services
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY item_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def item_exists(company_id, branch_id, item_id):
    if not item_id:
        return True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM item_services WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [item_id, company_id, branch_id],
        )
        return cursor.fetchone() is not None


def get_confirmations(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.id, cc.confirmation_no, cc.confirmation_date, cc.confirmation_type,
                   cc.po_number, cc.total_amount, cc.status,
                   COALESCE(q.customer_name, c.company_name) AS party_name
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.company_id = %s AND cc.branch_id = %s AND cc.status <> 'Cancelled'
            ORDER BY cc.confirmation_date DESC, cc.id DESC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_confirmation(company_id, branch_id, confirmation_id):
    if not confirmation_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.*, COALESCE(q.customer_name, c.company_name) AS party_name
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.id = %s AND cc.company_id = %s AND cc.branch_id = %s AND cc.status <> 'Cancelled'
            LIMIT 1
            """,
            [confirmation_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def purchase_no_exists(company_id, branch_id, purchase_no, exclude_id=None):
    params = [company_id, branch_id, purchase_no]
    clause = "company_id = %s AND branch_id = %s AND lower(purchase_no) = lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM supplier_purchases WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def default_form_data(company_id, branch_id):
    return {
        "purchase_no": generate_purchase_no(company_id, branch_id),
        "purchase_date": today_iso(),
        "supplier_id": "",
        "supplier_bill_no": "",
        "supplier_bill_date": "",
        "confirmation_id": "",
        "remarks": "",
        "status": "Unpaid",
        "subtotal": "0.00",
        "tax_total": "0.00",
        "grand_total": "0.00",
        "paid_amount": "0.00",
        "balance_amount": "0.00",
        "items": [empty_item_row()],
    }


def empty_item_row():
    return {
        "item_service_id": "",
        "description": "",
        "quantity": "1.00",
        "purchase_rate": "0.00",
        "tax_percent": "0.00",
        "tax_amount": "0.00",
        "line_total": "0.00",
        "errors": {},
    }


def parse_purchase_post(post):
    data = {
        "purchase_no": post.get("purchase_no", ""),
        "purchase_date": post.get("purchase_date", ""),
        "supplier_id": post.get("supplier_id", ""),
        "supplier_bill_no": post.get("supplier_bill_no", ""),
        "supplier_bill_date": post.get("supplier_bill_date", ""),
        "confirmation_id": post.get("confirmation_id", ""),
        "remarks": post.get("remarks", ""),
        "status": post.get("status", "Unpaid"),
        "paid_amount": post.get("paid_amount", "0"),
    }
    rows = []
    item_ids = post.getlist("item_service_id[]")
    descriptions = post.getlist("description[]")
    quantities = post.getlist("quantity[]")
    rates = post.getlist("purchase_rate[]")
    tax_percents = post.getlist("tax_percent[]")
    for index, description in enumerate(descriptions):
        rows.append(
            {
                "item_service_id": item_ids[index] if index < len(item_ids) else "",
                "description": description,
                "quantity": quantities[index] if index < len(quantities) else "",
                "purchase_rate": rates[index] if index < len(rates) else "",
                "tax_percent": tax_percents[index] if index < len(tax_percents) else "",
            }
        )
    data["items"] = rows
    return data


def validate_and_calculate(data, company_id, branch_id, purchase_id=None):
    errors = {}
    cleaned = {}

    cleaned["purchase_no"], errors["purchase_no"] = validators.clean_text(data.get("purchase_no"), max_length=50, required=True, field_name="Purchase No")
    if not errors["purchase_no"] and purchase_no_exists(company_id, branch_id, cleaned["purchase_no"], purchase_id):
        errors["purchase_no"] = "Purchase No already exists for the current branch."
    purchase_date, errors["purchase_date"] = validators.validate_date(data.get("purchase_date"), "Purchase Date", required=True)
    cleaned["purchase_date"] = purchase_date.isoformat() if purchase_date else ""

    supplier = get_supplier(company_id, branch_id, data.get("supplier_id"))
    if not supplier:
        errors["supplier_id"] = "Supplier is required."
    elif not supplier.get("account_id"):
        errors["supplier_id"] = "Selected supplier has no linked payable account. Please fix Supplier Master first."
    cleaned["supplier_id"] = data.get("supplier_id") or ""
    cleaned["supplier_account_id"] = supplier.get("account_id") if supplier else None

    cleaned["supplier_bill_no"], errors["supplier_bill_no"] = validators.clean_text(data.get("supplier_bill_no"), max_length=100, field_name="Supplier Bill No")
    bill_date, errors["supplier_bill_date"] = validators.validate_date(data.get("supplier_bill_date"), "Supplier Bill Date", required=False)
    cleaned["supplier_bill_date"] = bill_date.isoformat() if bill_date else None

    confirmation_id = data.get("confirmation_id") or ""
    if confirmation_id and not get_confirmation(company_id, branch_id, confirmation_id):
        errors["confirmation_id"] = "Selected confirmation was not found."
    cleaned["confirmation_id"] = confirmation_id
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")

    calculated_items, item_error = calculate_items(data.get("items") or [], company_id, branch_id)
    cleaned["items"] = calculated_items
    if item_error:
        errors["items"] = item_error

    totals = {
        "subtotal": sum(money(row["quantity"]) * money(row["purchase_rate"]) for row in calculated_items),
        "tax_total": sum(money(row["tax_amount"]) for row in calculated_items),
        "grand_total": sum(money(row["line_total"]) for row in calculated_items),
    }
    paid_amount, errors["paid_amount"] = validators.validate_money(data.get("paid_amount") or 0, "Paid Amount", allow_negative=False)
    paid_amount = paid_amount or Decimal("0.00")
    balance_amount = totals["grand_total"] - paid_amount
    if balance_amount < 0:
        errors["paid_amount"] = "Paid Amount cannot exceed Grand Total."
        balance_amount = Decimal("0.00")
    if totals["grand_total"] <= 0:
        errors["grand_total"] = "Grand Total must be greater than zero."

    status = derive_status(paid_amount, totals["grand_total"], data.get("status"))
    errors["status"] = validators.validate_choice(status, PURCHASE_STATUSES, "Status")
    cleaned.update(
        {
            "subtotal": format_money(totals["subtotal"]),
            "tax_total": format_money(totals["tax_total"]),
            "grand_total": format_money(totals["grand_total"]),
            "paid_amount": format_money(paid_amount),
            "balance_amount": format_money(balance_amount),
            "status": status,
        }
    )
    errors = {key: value for key, value in errors.items() if value}
    return errors, {**data, **cleaned}


def calculate_items(items, company_id, branch_id):
    tax_enabled = is_tax_enabled(company_id=company_id)
    rows = []
    has_error = False
    for raw in items:
        if not any(str(raw.get(key) or "").strip() for key in ["item_service_id", "description", "quantity", "purchase_rate", "tax_percent"]):
            continue
        errors = {}
        item_id = raw.get("item_service_id") or ""
        if item_id and not item_exists(company_id, branch_id, item_id):
            errors["item_service_id"] = "Selected item/service was not found."
        description, errors["description"] = validators.clean_text(raw.get("description"), required=True, field_name="Description")
        quantity, errors["quantity"] = validators.validate_decimal(raw.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        rate, errors["purchase_rate"] = validators.validate_money(raw.get("purchase_rate"), "Purchase Rate", allow_negative=False)
        tax_input = 0 if not tax_enabled else (raw.get("tax_percent") or 0)
        tax_percent, errors["tax_percent"] = validators.validate_percentage(tax_input, "Tax Percent")
        quantity = quantity or Decimal("0")
        rate = rate or Decimal("0")
        tax_percent = Decimal("0") if not tax_enabled else (tax_percent or Decimal("0"))
        base = (quantity * rate).quantize(Decimal("0.01"))
        tax_amount = (base * tax_percent / Decimal("100")).quantize(Decimal("0.01"))
        line_total = base + tax_amount
        errors = {key: value for key, value in errors.items() if value}
        if errors:
            has_error = True
        rows.append(
            {
                "item_service_id": item_id,
                "description": description,
                "quantity": str(quantity.quantize(Decimal("0.01"))),
                "purchase_rate": format_money(rate),
                "tax_percent": str(tax_percent.quantize(Decimal("0.01"))),
                "tax_amount": format_money(tax_amount),
                "line_total": format_money(line_total),
                "errors": errors,
            }
        )
    if not rows:
        return [empty_item_row()], "At least one purchase item is required."
    return rows, "Please correct item row errors." if has_error else None


def derive_status(paid_amount, grand_total, posted_status=None):
    if posted_status == "Cancelled":
        return "Cancelled"
    if grand_total <= 0 or paid_amount <= 0:
        return "Unpaid"
    if paid_amount < grand_total:
        return "Partially Paid"
    return "Paid"


def get_purchase(company_id, branch_id, purchase_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sp.*, s.supplier_name, s.contact_person AS supplier_contact_person,
                   s.phone AS supplier_phone, s.mobile AS supplier_mobile, s.email AS supplier_email,
                   s.address AS supplier_address, cc.confirmation_no, cc.confirmation_type,
                   cc.po_number, cc.total_amount AS confirmation_total,
                   je.entry_no AS journal_entry_no,
                   cb.full_name AS created_by_name, ub.full_name AS updated_by_name
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id = sp.supplier_id
            LEFT JOIN customer_confirmations cc ON cc.id = sp.confirmation_id
            LEFT JOIN journal_entries je ON je.id = sp.journal_entry_id
            LEFT JOIN users cb ON cb.id = sp.created_by_id
            LEFT JOIN users ub ON ub.id = sp.updated_by_id
            WHERE sp.id = %s AND sp.company_id = %s AND sp.branch_id = %s
            LIMIT 1
            """,
            [purchase_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_purchase_items(purchase_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT spi.*, i.item_code, i.item_name
            FROM supplier_purchase_items spi
            LEFT JOIN item_services i ON i.id = spi.item_service_id
            WHERE spi.supplier_purchase_id = %s
            ORDER BY spi.id
            """,
            [purchase_id],
        )
        return dictfetchall(cursor)


def save_purchase(company_id, branch_id, user_id, data, purchase_id=None):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if purchase_id:
                cursor.execute(
                    """
                    UPDATE supplier_purchases
                    SET supplier_bill_no = %s, supplier_bill_date = %s, remarks = %s,
                        updated_by_id = %s, updated_at = %s
                    WHERE id = %s AND company_id = %s AND branch_id = %s
                    """,
                    [data.get("supplier_bill_no"), data.get("supplier_bill_date"), data.get("remarks"), user_id, timestamp, purchase_id, company_id, branch_id],
                )
                return purchase_id

            cursor.execute(
                """
                INSERT INTO supplier_purchases (
                    company_id, branch_id, purchase_no, purchase_date, supplier_id,
                    supplier_bill_no, supplier_bill_date, confirmation_id, subtotal,
                    tax_total, grand_total, paid_amount, balance_amount, status,
                    journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
                """,
                [
                    company_id, branch_id, data["purchase_no"], data["purchase_date"], data["supplier_id"],
                    data.get("supplier_bill_no"), data.get("supplier_bill_date"), data.get("confirmation_id") or None,
                    data["subtotal"], data["tax_total"], data["grand_total"], data["paid_amount"], data["balance_amount"],
                    data["status"], data.get("remarks"), user_id, user_id, timestamp, timestamp,
                ],
            )
            saved_id = cursor.lastrowid
            insert_items(cursor, saved_id, data["items"], timestamp)
            journal_id = post_supplier_purchase_entry(
                company_id,
                branch_id,
                data["supplier_account_id"],
                data["purchase_date"],
                saved_id,
                data["subtotal"],
                data["tax_total"],
                data["grand_total"],
                user_id,
            )
            cursor.execute("UPDATE supplier_purchases SET journal_entry_id = %s WHERE id = %s", [journal_id, saved_id])
            post_supplier_purchase_stock(company_id, branch_id, saved_id, user_id)
    return saved_id


def insert_items(cursor, purchase_id, items, timestamp):
    for row in items:
        cursor.execute(
            """
            INSERT INTO supplier_purchase_items (
                supplier_purchase_id, item_service_id, description, quantity,
                purchase_rate, tax_percent, tax_amount, line_total, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                purchase_id, row.get("item_service_id") or None, row["description"], row["quantity"],
                row["purchase_rate"], row["tax_percent"], row["tax_amount"], row["line_total"], timestamp, timestamp,
            ],
        )


def purchase_has_future_references(_purchase_id):
    return False


def cancel_purchase(request, purchase):
    if purchase.get("status") == "Cancelled":
        raise ValueError("This purchase is already cancelled.")
    if purchase_has_future_references(purchase["id"]):
        raise ValueError("This purchase is already used by a later document and cannot be cancelled.")
    timestamp = now_text()
    company_id, branch_id = get_scope(request)
    with transaction.atomic():
        reversal_id = None
        if purchase.get("journal_entry_id"):
            reversal_id = reverse_journal_entry(
                purchase["journal_entry_id"],
                today_iso(),
                f"Cancel supplier purchase {purchase['purchase_no']}",
                request.session.get("user_id"),
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE journal_entries SET reference_type = 'supplier_purchase_cancel', reference_id = %s WHERE id = %s",
                    [purchase["id"], reversal_id],
                )
        reverse_stock_movements("supplier_purchase", purchase["id"], f"Cancel supplier purchase {purchase['purchase_no']}", request.session.get("user_id"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE supplier_purchases
                SET status = 'Cancelled', updated_by_id = %s, updated_at = %s
                WHERE id = %s AND company_id = %s AND branch_id = %s
                """,
                [request.session.get("user_id"), timestamp, purchase["id"], company_id, branch_id],
            )
    log_user_activity(request, "CANCEL", "Supplier Purchases", "supplier_purchases", purchase["id"], f"Cancelled supplier purchase {purchase['purchase_no']}.")
    return reversal_id


def get_print_context(company_id, branch_id, purchase_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id = %s LIMIT 1", [company_id])
        company = dictfetchone(cursor) or {}
        cursor.execute("SELECT * FROM branches WHERE id = %s AND company_id = %s LIMIT 1", [branch_id, company_id])
        branch = dictfetchone(cursor) or {}
    return {
        "company": company,
        "branch": branch,
        "purchase": get_purchase(company_id, branch_id, purchase_id),
        "items": get_purchase_items(purchase_id),
        "print_date": today_iso(),
    }
