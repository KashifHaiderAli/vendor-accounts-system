from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import post_purchase_return_entry, reverse_journal_entry
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from core.edition_utils import is_tax_enabled
from core.inventory_utils import post_purchase_return_stock, reverse_stock_movements, validate_available_stock
from settings_module.services import get_numbering_settings, log_user_activity, now_text


PER_PAGE = 20
RETURN_STATUSES = ["Posted", "Cancelled"]


def today_iso():
    return date.today().isoformat()


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def paginate(total_count, page, per_page=PER_PAGE):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    return {"page": page, "per_page": per_page, "total_count": total_count, "total_pages": total_pages, "offset": (page - 1) * per_page, "pages": list(range(1, total_pages + 1))}


def generate_return_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("purchase_return_prefix") or "PR"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute("SELECT purchase_return_no FROM purchase_returns WHERE company_id=%s AND branch_id=%s AND purchase_return_no LIKE %s ORDER BY purchase_return_no DESC LIMIT 1", [company_id, branch_id, f"{doc_prefix}%"])
        row = cursor.fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            number = 1
    return f"{doc_prefix}{number:0{padding}d}"


def list_returns(company_id, branch_id, search="", status="", date_from="", date_to="", page=1):
    clauses = ["pr.company_id=%s", "pr.branch_id=%s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(pr.purchase_return_no LIKE %s OR s.supplier_name LIKE %s OR sp.purchase_no LIKE %s OR pr.supplier_bill_no LIKE %s OR pr.return_reason LIKE %s)")
        params.extend([like, like, like, like, like])
    if status:
        clauses.append("pr.status=%s")
        params.append(status)
    if date_from:
        clauses.append("pr.return_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("pr.return_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM purchase_returns pr LEFT JOIN suppliers s ON s.id=pr.supplier_id LEFT JOIN supplier_purchases sp ON sp.id=pr.supplier_purchase_id WHERE {where_sql}", params)
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT pr.*, s.supplier_name, sp.purchase_no, rev.id AS reversal_id
            FROM purchase_returns pr
            LEFT JOIN suppliers s ON s.id=pr.supplier_id
            LEFT JOIN supplier_purchases sp ON sp.id=pr.supplier_purchase_id
            LEFT JOIN journal_entries rev ON rev.reference_type='purchase_return_cancel' AND rev.reference_id=pr.id
            WHERE {where_sql}
            ORDER BY pr.return_date DESC, pr.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_suppliers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, supplier_code, supplier_name, account_id FROM suppliers WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY supplier_name", [company_id, branch_id])
        return dictfetchall(cursor)


def get_supplier(company_id, branch_id, supplier_id):
    if not supplier_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM suppliers WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [supplier_id, company_id, branch_id])
        return dictfetchone(cursor)


def get_purchases(company_id, branch_id, supplier_id=None):
    clauses = ["sp.company_id=%s", "sp.branch_id=%s", "sp.status <> 'Cancelled'", "sp.journal_entry_id IS NOT NULL"]
    params = [company_id, branch_id]
    if supplier_id:
        clauses.append("sp.supplier_id=%s")
        params.append(supplier_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sp.id, sp.purchase_no, sp.purchase_date, sp.supplier_id, sp.supplier_bill_no, sp.grand_total, sp.balance_amount, s.supplier_name
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id=sp.supplier_id
            WHERE {" AND ".join(clauses)}
            ORDER BY sp.purchase_date DESC, sp.id DESC
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
            SELECT sp.*, s.supplier_name, s.account_id AS supplier_account_id
            FROM supplier_purchases sp
            LEFT JOIN suppliers s ON s.id=sp.supplier_id
            WHERE {" AND ".join(clauses)}
            LIMIT 1
            """,
            params,
        )
        return dictfetchone(cursor)


def get_purchase_items(purchase_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM supplier_purchase_items WHERE supplier_purchase_id=%s ORDER BY id", [purchase_id])
        return dictfetchall(cursor)


def returned_quantity(purchase_item_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(SUM(pri.quantity), 0)
            FROM purchase_return_items pri
            JOIN purchase_returns pr ON pr.id=pri.purchase_return_id
            WHERE pri.supplier_purchase_item_id=%s AND pr.status <> 'Cancelled'
            """,
            [purchase_item_id],
        )
        return money(cursor.fetchone()[0])


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, item_code, item_name FROM item_services WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY item_name", [company_id, branch_id])
        return dictfetchall(cursor)


def default_form_data(company_id, branch_id, purchase=None):
    data = {"purchase_return_no": generate_return_no(company_id, branch_id), "return_date": today_iso(), "supplier_id": purchase.get("supplier_id") if purchase else "", "supplier_purchase_id": purchase.get("id") if purchase else "", "supplier_bill_no": purchase.get("supplier_bill_no") if purchase else "", "return_reason": "", "remarks": "", "status": "Posted", "subtotal": "0.00", "tax_total": "0.00", "grand_total": "0.00", "refund_amount": "0.00", "items": []}
    if purchase:
        for item in get_purchase_items(purchase["id"]):
            available = money(item.get("quantity")) - returned_quantity(item["id"])
            if available > 0:
                data["items"].append({"item_service_id": item.get("item_service_id") or "", "supplier_purchase_item_id": item.get("id"), "description": item.get("description") or "", "quantity": str(available), "purchase_rate": item.get("purchase_rate") or "0", "tax_percent": item.get("tax_percent") or "0", "tax_amount": "0.00", "line_total": "0.00", "max_quantity": str(available), "errors": {}})
    if purchase and not data["items"]:
        data["items"] = [empty_item_row()]
    return data


def empty_item_row():
    return {"item_service_id": "", "supplier_purchase_item_id": "", "description": "", "quantity": "1", "purchase_rate": "0.00", "tax_percent": "0", "tax_amount": "0.00", "line_total": "0.00", "max_quantity": "", "errors": {}}


def parse_post(post):
    items = []
    for index, description in enumerate(post.getlist("description")):
        items.append({"item_service_id": post.getlist("item_service_id")[index] if index < len(post.getlist("item_service_id")) else "", "supplier_purchase_item_id": post.getlist("supplier_purchase_item_id")[index] if index < len(post.getlist("supplier_purchase_item_id")) else "", "description": description, "quantity": post.getlist("quantity")[index] if index < len(post.getlist("quantity")) else "", "purchase_rate": post.getlist("purchase_rate")[index] if index < len(post.getlist("purchase_rate")) else "", "tax_percent": post.getlist("tax_percent")[index] if index < len(post.getlist("tax_percent")) else ""})
    return {"purchase_return_no": post.get("purchase_return_no", ""), "return_date": post.get("return_date", ""), "supplier_id": post.get("supplier_id", ""), "supplier_purchase_id": post.get("supplier_purchase_id", ""), "supplier_bill_no": post.get("supplier_bill_no", ""), "return_reason": post.get("return_reason", ""), "remarks": post.get("remarks", ""), "status": "Posted", "items": items}


def return_no_exists(company_id, branch_id, return_no, exclude_id=None):
    params = [company_id, branch_id, return_no]
    clause = "company_id=%s AND branch_id=%s AND lower(purchase_return_no)=lower(%s)"
    if exclude_id:
        clause += " AND id<>%s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM purchase_returns WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_and_calculate(data, company_id, branch_id, return_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["purchase_return_no"], errors["purchase_return_no"] = validators.clean_text(data.get("purchase_return_no"), max_length=50, required=True, field_name="Return No")
    if not errors["purchase_return_no"] and return_no_exists(company_id, branch_id, cleaned["purchase_return_no"], return_id):
        errors["purchase_return_no"] = "Return No already exists for the current branch."
    return_date, errors["return_date"] = validators.validate_date(data.get("return_date"), "Return Date", required=True)
    cleaned["return_date"] = return_date.isoformat() if return_date else ""
    cleaned["supplier_bill_no"], errors["supplier_bill_no"] = validators.clean_text(data.get("supplier_bill_no"), max_length=100, field_name="Supplier Bill No")
    cleaned["return_reason"], errors["return_reason"] = validators.clean_text(data.get("return_reason"), field_name="Return Reason")
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
    supplier = get_supplier(company_id, branch_id, data.get("supplier_id"))
    if not supplier:
        errors["supplier_id"] = "Select a valid active supplier."
    elif not supplier.get("account_id"):
        errors["supplier_id"] = "Selected supplier does not have a linked payable account."
    purchase = get_purchase(company_id, branch_id, data.get("supplier_purchase_id"), supplier["id"] if supplier else None)
    if not purchase:
        errors["supplier_purchase_id"] = "Select a valid posted supplier purchase."
    elif not purchase.get("journal_entry_id"):
        errors["supplier_purchase_id"] = "Selected purchase is not posted to accounting."
    cleaned["supplier_id"] = supplier["id"] if supplier else ""
    cleaned["supplier_account_id"] = supplier.get("account_id") if supplier else None
    cleaned["supplier_purchase_id"] = purchase["id"] if purchase else ""

    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    tax_enabled = is_tax_enabled(company_id=company_id)
    rows = []
    for row in data.get("items") or []:
        row_errors = {}
        description, row_errors["description"] = validators.clean_text(row.get("description"), required=True, field_name="Description")
        quantity, row_errors["quantity"] = validators.validate_decimal(row.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        rate, row_errors["purchase_rate"] = validators.validate_money(row.get("purchase_rate"), "Purchase Rate", required=True)
        tax_input = 0 if not tax_enabled else row.get("tax_percent")
        tax_percent, row_errors["tax_percent"] = validators.validate_percentage(tax_input, "Tax Percent")
        purchase_item = get_purchase_item(purchase["id"], row.get("supplier_purchase_item_id")) if purchase and row.get("supplier_purchase_item_id") else None
        if row.get("supplier_purchase_item_id") and not purchase_item:
            row_errors["supplier_purchase_item_id"] = "Selected purchase item is invalid."
        if purchase_item and quantity:
            available = money(purchase_item.get("quantity")) - returned_quantity(purchase_item["id"])
            if quantity > available:
                row_errors["quantity"] = f"Returned quantity cannot exceed available quantity {available}."
        if row.get("item_service_id") and quantity and not row_errors:
            try:
                validate_available_stock(company_id, branch_id, row.get("item_service_id"), quantity, "Purchase Return")
            except ValueError as exc:
                row_errors["quantity"] = str(exc)
        base = money(quantity or 0) * money(rate or 0)
        tax_percent = Decimal("0") if not tax_enabled else (tax_percent or Decimal("0"))
        tax_amount = (base * money(tax_percent or 0) / Decimal("100")).quantize(Decimal("0.01"))
        line_total = base + tax_amount
        row.update({"description": description, "quantity": quantity or Decimal("0"), "purchase_rate": rate or Decimal("0"), "tax_percent": tax_percent or Decimal("0"), "tax_amount": tax_amount, "line_total": line_total, "errors": {k: v for k, v in row_errors.items() if v}})
        if row["errors"]:
            errors["items"] = "Please correct item row errors."
        else:
            subtotal += base
            tax_total += tax_amount
            rows.append(row)
    if not rows:
        errors["items"] = "At least one return item is required."
    grand_total = subtotal + tax_total
    if grand_total <= 0:
        errors["grand_total"] = "Return total must be greater than zero."
    cleaned.update({"items": data.get("items") or [], "subtotal": subtotal, "tax_total": tax_total, "grand_total": grand_total, "refund_amount": grand_total, "status": "Posted"})
    return {k: v for k, v in errors.items() if v}, cleaned


def get_purchase_item(purchase_id, item_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM supplier_purchase_items WHERE id=%s AND supplier_purchase_id=%s LIMIT 1", [item_id, purchase_id])
        return dictfetchone(cursor)


def save_return(company_id, branch_id, user_id, data, return_id=None):
    timestamp = now_text()
    if return_id:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE purchase_returns SET return_reason=%s, remarks=%s, updated_by_id=%s, updated_at=%s WHERE id=%s AND company_id=%s AND branch_id=%s", [data.get("return_reason"), data.get("remarks"), user_id, timestamp, return_id, company_id, branch_id])
        return return_id
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO purchase_returns (
                    company_id, branch_id, purchase_return_no, return_date, supplier_id, supplier_purchase_id,
                    supplier_bill_no, return_reason, subtotal, tax_total, grand_total, refund_amount, status,
                    journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, data["purchase_return_no"], data["return_date"], data["supplier_id"], data["supplier_purchase_id"], data.get("supplier_bill_no"), data.get("return_reason"), str(data["subtotal"]), str(data["tax_total"]), str(data["grand_total"]), str(data.get("refund_amount") or data["grand_total"]), "Posted", data.get("remarks"), user_id, user_id, timestamp, timestamp],
            )
            saved_id = cursor.lastrowid
            for item in data["items"]:
                if item.get("errors"):
                    continue
                cursor.execute(
                    """
                    INSERT INTO purchase_return_items (
                        purchase_return_id, item_service_id, supplier_purchase_item_id, description,
                        quantity, purchase_rate, tax_percent, tax_amount, line_total, created_at, updated_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [saved_id, item.get("item_service_id") or None, item.get("supplier_purchase_item_id") or None, item["description"], str(item["quantity"]), str(item["purchase_rate"]), str(item["tax_percent"]), str(item["tax_amount"]), str(item["line_total"]), timestamp, timestamp],
                )
            journal_id = post_purchase_return_entry(company_id, branch_id, data["supplier_account_id"], data["return_date"], saved_id, data["subtotal"], data["tax_total"], data["grand_total"], user_id)
            cursor.execute("UPDATE purchase_returns SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
            post_purchase_return_stock(company_id, branch_id, saved_id, user_id)
            update_purchase_balance(cursor, data["supplier_purchase_id"], data["grand_total"], user_id, timestamp, subtract=True)
    return saved_id


def update_purchase_balance(cursor, purchase_id, amount, user_id, timestamp, subtract=True):
    cursor.execute("SELECT grand_total, paid_amount, balance_amount FROM supplier_purchases WHERE id=%s LIMIT 1", [purchase_id])
    row = cursor.fetchone()
    if not row:
        return
    paid = money(row[1])
    balance = money(row[2]) - money(amount) if subtract else money(row[2]) + money(amount)
    if balance < 0:
        balance = Decimal("0.00")
    status = "Paid" if balance <= 0 else ("Partially Paid" if paid > 0 else "Unpaid")
    cursor.execute("UPDATE supplier_purchases SET balance_amount=%s, status=%s, updated_by_id=%s, updated_at=%s WHERE id=%s", [str(balance), status, user_id, timestamp, purchase_id])


def get_return(company_id, branch_id, return_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pr.*, s.supplier_name, s.address AS supplier_address, s.phone AS supplier_phone,
                   sp.purchase_no, sp.purchase_date, je.entry_no AS journal_entry_no, rev.id AS reversal_id
            FROM purchase_returns pr
            LEFT JOIN suppliers s ON s.id=pr.supplier_id
            LEFT JOIN supplier_purchases sp ON sp.id=pr.supplier_purchase_id
            LEFT JOIN journal_entries je ON je.id=pr.journal_entry_id
            LEFT JOIN journal_entries rev ON rev.reference_type='purchase_return_cancel' AND rev.reference_id=pr.id
            WHERE pr.id=%s AND pr.company_id=%s AND pr.branch_id=%s
            LIMIT 1
            """,
            [return_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_return_items(return_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_return_items WHERE purchase_return_id=%s ORDER BY id", [return_id])
        return dictfetchall(cursor)


def cancel_return(request, purchase_return):
    if purchase_return.get("reversal_id"):
        raise ValueError("This purchase return already has a cancellation reversal journal.")
    user_id = request.session.get("user_id")
    timestamp = now_text()
    with transaction.atomic():
        reversal_id = reverse_journal_entry(purchase_return["journal_entry_id"], today_iso(), f"Cancel purchase return {purchase_return['purchase_return_no']}", user_id)
        with connection.cursor() as cursor:
            reverse_stock_movements("purchase_return", purchase_return["id"], f"Cancel purchase return {purchase_return['purchase_return_no']}", user_id)
            cursor.execute("UPDATE journal_entries SET reference_type='purchase_return_cancel', reference_id=%s, description=%s, updated_at=%s WHERE id=%s", [purchase_return["id"], f"Cancellation reversal for purchase return {purchase_return['purchase_return_no']}", timestamp, reversal_id])
            cursor.execute("UPDATE purchase_returns SET status='Cancelled', updated_by_id=%s, updated_at=%s WHERE id=%s", [user_id, timestamp, purchase_return["id"]])
            update_purchase_balance(cursor, purchase_return["supplier_purchase_id"], purchase_return["grand_total"], user_id, timestamp, subtract=False)
    log_user_activity(request, "CANCEL", "Purchase Returns", "purchase_returns", purchase_return["id"], f"Cancelled purchase return {purchase_return['purchase_return_no']}.")


def mark_printed(request, purchase_return):
    log_user_activity(request, "PRINT", "Purchase Returns", "purchase_returns", purchase_return["id"], f"Printed purchase return {purchase_return['purchase_return_no']}.")


def get_print_context(company_id, branch_id, return_id):
    purchase_return = get_return(company_id, branch_id, return_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return {"purchase_return": purchase_return, "items": get_return_items(return_id), "company": company, "branch": branch, "print_date": today_iso()}
