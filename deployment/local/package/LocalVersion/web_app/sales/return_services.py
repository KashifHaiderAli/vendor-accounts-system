from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import AccountingError, post_sales_return_entry, reverse_journal_entry
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from core.edition_utils import is_tax_enabled
from core.inventory_utils import column_exists, post_sales_return_stock, reverse_stock_movements
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
    prefix = settings.get("sales_return_prefix") or "SR"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute("SELECT sales_return_no FROM sales_returns WHERE company_id=%s AND branch_id=%s AND sales_return_no LIKE %s ORDER BY sales_return_no DESC LIMIT 1", [company_id, branch_id, f"{doc_prefix}%"])
        row = cursor.fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            number = 1
    return f"{doc_prefix}{number:0{padding}d}"


def list_returns(company_id, branch_id, search="", status="", date_from="", date_to="", page=1):
    clauses = ["sr.company_id=%s", "sr.branch_id=%s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(sr.sales_return_no LIKE %s OR c.company_name LIKE %s OR si.invoice_no LIKE %s OR sr.return_reason LIKE %s)")
        params.extend([like, like, like, like])
    if status:
        clauses.append("sr.status=%s")
        params.append(status)
    if date_from:
        clauses.append("sr.return_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("sr.return_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM sales_returns sr LEFT JOIN customers c ON c.id=sr.customer_id LEFT JOIN sales_invoices si ON si.id=sr.sales_invoice_id WHERE {where_sql}", params)
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT sr.*, c.company_name AS customer_name, si.invoice_no, rev.id AS reversal_id
            FROM sales_returns sr
            LEFT JOIN customers c ON c.id=sr.customer_id
            LEFT JOIN sales_invoices si ON si.id=sr.sales_invoice_id
            LEFT JOIN journal_entries rev ON rev.reference_type='sales_return_cancel' AND rev.reference_id=sr.id
            WHERE {where_sql}
            ORDER BY sr.return_date DESC, sr.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, customer_code, company_name, account_id FROM customers WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY company_name", [company_id, branch_id])
        return dictfetchall(cursor)


def get_invoices(company_id, branch_id, customer_id=None):
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'", "si.journal_entry_id IS NOT NULL"]
    params = [company_id, branch_id]
    if customer_id:
        clauses.append("si.customer_id=%s")
        params.append(customer_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT si.id, si.invoice_no, si.invoice_date, si.customer_id, si.grand_total, si.balance_amount, c.company_name AS customer_name
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id=si.customer_id
            WHERE {" AND ".join(clauses)}
            ORDER BY si.invoice_date DESC, si.id DESC
            """,
            params,
        )
        return dictfetchall(cursor)


def get_customer(company_id, branch_id, customer_id):
    if not customer_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM customers WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [customer_id, company_id, branch_id])
        return dictfetchone(cursor)


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
            SELECT si.*, c.company_name AS customer_name, c.account_id AS customer_account_id
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id=si.customer_id
            WHERE {" AND ".join(clauses)}
            LIMIT 1
            """,
            params,
        )
        return dictfetchone(cursor)


def get_invoice_items(invoice_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_invoice_items WHERE sales_invoice_id=%s ORDER BY id", [invoice_id])
        return dictfetchall(cursor)


def returned_quantity(invoice_item_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(SUM(sri.quantity), 0)
            FROM sales_return_items sri
            JOIN sales_returns sr ON sr.id=sri.sales_return_id
            WHERE sri.sales_invoice_item_id=%s AND sr.status <> 'Cancelled'
            """,
            [invoice_item_id],
        )
        return money(cursor.fetchone()[0])


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, item_code, item_name FROM item_services WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY item_name", [company_id, branch_id])
        return dictfetchall(cursor)


def default_form_data(company_id, branch_id, invoice=None):
    data = {
        "sales_return_no": generate_return_no(company_id, branch_id),
        "return_date": today_iso(),
        "customer_id": invoice.get("customer_id") if invoice else "",
        "sales_invoice_id": invoice.get("id") if invoice else "",
        "return_reason": "",
        "return_stock_action": "Return to Stock",
        "remarks": "",
        "status": "Posted",
        "subtotal": "0.00",
        "discount_total": "0.00",
        "tax_total": "0.00",
        "grand_total": "0.00",
        "refund_amount": "0.00",
        "items": [],
    }
    if invoice:
        for item in get_invoice_items(invoice["id"]):
            invoiced_qty = money(item.get("quantity"))
            already_returned_qty = returned_quantity(item["id"])
            available = invoiced_qty - already_returned_qty
            if available > 0:
                data["items"].append({
                    "item_service_id": item.get("item_service_id") or "",
                    "sales_invoice_item_id": item.get("id"),
                    "description": item.get("description") or "",
                    "invoiced_qty": str(invoiced_qty),
                    "already_returned_qty": str(already_returned_qty),
                    "quantity": str(available),
                    "rate": item.get("rate") or "0",
                    "discount_percent": item.get("discount_percent") or "0",
                    "discount_amount": item.get("discount_amount") or "0",
                    "tax_percent": item.get("tax_percent") or "0",
                    "tax_amount": "0.00",
                    "line_total": "0.00",
                    "max_quantity": str(available),
                    "errors": {},
                })
    if invoice and not data["items"]:
        data["items"] = [empty_item_row()]
    return data


def empty_item_row():
    return {"item_service_id": "", "sales_invoice_item_id": "", "description": "", "quantity": "1", "rate": "0.00", "discount_percent": "0", "discount_amount": "0", "tax_percent": "0", "tax_amount": "0.00", "line_total": "0.00", "max_quantity": "", "errors": {}}


def parse_post(post):
    items = []
    for index, description in enumerate(post.getlist("description")):
        items.append({
            "item_service_id": post.getlist("item_service_id")[index] if index < len(post.getlist("item_service_id")) else "",
            "sales_invoice_item_id": post.getlist("sales_invoice_item_id")[index] if index < len(post.getlist("sales_invoice_item_id")) else "",
            "description": description,
            "quantity": post.getlist("quantity")[index] if index < len(post.getlist("quantity")) else "",
            "rate": post.getlist("rate")[index] if index < len(post.getlist("rate")) else "",
            "discount_percent": post.getlist("discount_percent")[index] if index < len(post.getlist("discount_percent")) else "",
            "discount_amount": post.getlist("discount_amount")[index] if index < len(post.getlist("discount_amount")) else "",
            "tax_percent": post.getlist("tax_percent")[index] if index < len(post.getlist("tax_percent")) else "",
        })
    return {
        "sales_return_no": post.get("sales_return_no", ""),
        "return_date": post.get("return_date", ""),
        "customer_id": post.get("customer_id", ""),
        "sales_invoice_id": post.get("sales_invoice_id", ""),
        "return_reason": post.get("return_reason", ""),
        "return_stock_action": post.get("return_stock_action", "Return to Stock"),
        "remarks": post.get("remarks", ""),
        "status": "Posted",
        "items": items,
    }


def return_no_exists(company_id, branch_id, return_no, exclude_id=None):
    params = [company_id, branch_id, return_no]
    clause = "company_id=%s AND branch_id=%s AND lower(sales_return_no)=lower(%s)"
    if exclude_id:
        clause += " AND id<>%s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM sales_returns WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_and_calculate(data, company_id, branch_id, return_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["sales_return_no"], errors["sales_return_no"] = validators.clean_text(data.get("sales_return_no"), max_length=50, required=True, field_name="Return No")
    if not errors["sales_return_no"] and return_no_exists(company_id, branch_id, cleaned["sales_return_no"], return_id):
        errors["sales_return_no"] = "Return No already exists for the current branch."
    return_date, errors["return_date"] = validators.validate_date(data.get("return_date"), "Return Date", required=True)
    cleaned["return_date"] = return_date.isoformat() if return_date else ""
    cleaned["return_reason"], errors["return_reason"] = validators.clean_text(data.get("return_reason"), field_name="Return Reason")
    action = data.get("return_stock_action") or "Return to Stock"
    action_error = validators.validate_choice(action, ["Return to Stock", "Damaged / Not Saleable", "Do Not Affect Stock"], "Return Stock Action")
    if action_error:
        errors["return_stock_action"] = action_error
    cleaned["return_stock_action"] = action
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
    customer = get_customer(company_id, branch_id, data.get("customer_id"))
    if not customer:
        errors["customer_id"] = "Select a valid active customer."
    elif not customer.get("account_id"):
        errors["customer_id"] = "Selected customer does not have a linked receivable account."
    invoice = get_invoice(company_id, branch_id, data.get("sales_invoice_id"), customer["id"] if customer else None)
    if not invoice:
        errors["sales_invoice_id"] = "Select a valid posted invoice for this customer."
    elif not invoice.get("journal_entry_id"):
        errors["sales_invoice_id"] = "Selected invoice is not posted to accounting."
    cleaned["customer_id"] = customer["id"] if customer else ""
    cleaned["customer_account_id"] = customer.get("account_id") if customer else None
    cleaned["sales_invoice_id"] = invoice["id"] if invoice else ""

    rows = []
    tax_enabled = is_tax_enabled(company_id=company_id)
    subtotal = Decimal("0.00")
    discount_total = Decimal("0.00")
    tax_total = Decimal("0.00")
    for row in data.get("items") or []:
        row_errors = {}
        description, row_errors["description"] = validators.clean_text(row.get("description"), required=True, field_name="Description")
        quantity, row_errors["quantity"] = validators.validate_decimal(row.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        rate, row_errors["rate"] = validators.validate_money(row.get("rate"), "Rate", required=True)
        discount_percent, row_errors["discount_percent"] = validators.validate_percentage(row.get("discount_percent"), "Discount Percent")
        discount_amount, row_errors["discount_amount"] = validators.validate_money(row.get("discount_amount"), "Discount Amount")
        tax_input = 0 if not tax_enabled else row.get("tax_percent")
        tax_percent, row_errors["tax_percent"] = validators.validate_percentage(tax_input, "Tax Percent")
        invoice_item = get_invoice_item(invoice["id"], row.get("sales_invoice_item_id")) if invoice and row.get("sales_invoice_item_id") else None
        if row.get("sales_invoice_item_id") and not invoice_item:
            row_errors["sales_invoice_item_id"] = "Selected invoice item is invalid."
        if invoice_item and quantity:
            available = money(invoice_item.get("quantity")) - returned_quantity(invoice_item["id"])
            if quantity > available:
                row_errors["quantity"] = f"Returned quantity cannot exceed available quantity {available}."
        base = money(quantity or 0) * money(rate or 0)
        percent_discount = (base * money(discount_percent or 0) / Decimal("100")).quantize(Decimal("0.01"))
        discount = money(discount_amount or 0) if money(discount_amount or 0) > 0 else percent_discount
        if discount > base:
            row_errors["discount_amount"] = "Discount cannot exceed line amount."
        taxable = base - discount
        tax_percent = Decimal("0") if not tax_enabled else (tax_percent or Decimal("0"))
        tax_amount = (taxable * money(tax_percent or 0) / Decimal("100")).quantize(Decimal("0.01"))
        line_total = taxable + tax_amount
        row.update({"description": description, "quantity": quantity or Decimal("0"), "rate": rate or Decimal("0"), "discount_percent": discount_percent or Decimal("0"), "discount_amount": discount, "tax_percent": tax_percent or Decimal("0"), "tax_amount": tax_amount, "line_total": line_total, "errors": {k: v for k, v in row_errors.items() if v}})
        if row["errors"]:
            errors["items"] = "Please correct item row errors."
        else:
            subtotal += base
            discount_total += discount
            tax_total += tax_amount
            rows.append(row)
    if not rows:
        errors["items"] = "At least one return item is required."
    grand_total = subtotal - discount_total + tax_total
    if grand_total <= 0:
        errors["grand_total"] = "Return total must be greater than zero."
    cleaned.update({"items": data.get("items") or [], "subtotal": subtotal, "discount_total": discount_total, "tax_total": tax_total, "grand_total": grand_total, "refund_amount": grand_total, "status": "Posted"})
    return {k: v for k, v in errors.items() if v}, cleaned


def get_invoice_item(invoice_id, item_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_invoice_items WHERE id=%s AND sales_invoice_id=%s LIMIT 1", [item_id, invoice_id])
        return dictfetchone(cursor)


def save_return(company_id, branch_id, user_id, data, return_id=None):
    timestamp = now_text()
    if return_id:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE sales_returns SET return_reason=%s, remarks=%s, updated_by_id=%s, updated_at=%s WHERE id=%s AND company_id=%s AND branch_id=%s", [data.get("return_reason"), data.get("remarks"), user_id, timestamp, return_id, company_id, branch_id])
        return return_id
    with transaction.atomic():
        with connection.cursor() as cursor:
            has_action = column_exists("sales_returns", "return_stock_action")
            action_column = ", return_stock_action" if has_action else ""
            action_placeholder = ", %s" if has_action else ""
            action_value = [data.get("return_stock_action") or "Return to Stock"] if has_action else []
            cursor.execute(
                f"""
                INSERT INTO sales_returns (
                    company_id, branch_id, sales_return_no, return_date, customer_id, sales_invoice_id,
                    return_reason{action_column}, subtotal, discount_total, tax_total, grand_total, refund_amount,
                    status, journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s{action_placeholder},%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s)
                """,
                [company_id, branch_id, data["sales_return_no"], data["return_date"], data["customer_id"], data["sales_invoice_id"], data.get("return_reason")] + action_value + [str(data["subtotal"]), str(data["discount_total"]), str(data["tax_total"]), str(data["grand_total"]), str(data.get("refund_amount") or data["grand_total"]), "Posted", data.get("remarks"), user_id, user_id, timestamp, timestamp],
            )
            saved_id = cursor.lastrowid
            for item in data["items"]:
                if item.get("errors"):
                    continue
                cursor.execute(
                    """
                    INSERT INTO sales_return_items (
                        sales_return_id, item_service_id, sales_invoice_item_id, description, quantity, rate,
                        discount_percent, discount_amount, tax_percent, tax_amount, line_total, created_at, updated_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [saved_id, item.get("item_service_id") or None, item.get("sales_invoice_item_id") or None, item["description"], str(item["quantity"]), str(item["rate"]), str(item["discount_percent"]), str(item["discount_amount"]), str(item["tax_percent"]), str(item["tax_amount"]), str(item["line_total"]), timestamp, timestamp],
                )
            journal_id = post_sales_return_entry(company_id, branch_id, data["customer_account_id"], data["return_date"], saved_id, data["subtotal"], data["discount_total"], data["tax_total"], data["grand_total"], user_id)
            cursor.execute("UPDATE sales_returns SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
            post_sales_return_stock(company_id, branch_id, saved_id, user_id)
            update_invoice_balance(cursor, data["sales_invoice_id"], data["grand_total"], user_id, timestamp, subtract=True)
    return saved_id


def update_invoice_balance(cursor, invoice_id, amount, user_id, timestamp, subtract=True):
    cursor.execute("SELECT grand_total, received_amount, balance_amount, status FROM sales_invoices WHERE id=%s LIMIT 1", [invoice_id])
    row = cursor.fetchone()
    if not row:
        return
    received = money(row[1])
    balance = money(row[2]) - money(amount) if subtract else money(row[2]) + money(amount)
    if balance < 0:
        balance = Decimal("0.00")
    status = "Paid" if balance <= 0 else ("Partially Paid" if received > 0 else ("Draft" if row[3] == "Draft" else "Printed"))
    cursor.execute("UPDATE sales_invoices SET balance_amount=%s, status=%s, updated_by_id=%s, updated_at=%s WHERE id=%s", [str(balance), status, user_id, timestamp, invoice_id])


def get_return(company_id, branch_id, return_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sr.*, c.company_name AS customer_name, c.address AS customer_address, c.phone AS customer_phone,
                   si.invoice_no, si.invoice_date, je.entry_no AS journal_entry_no, rev.id AS reversal_id
            FROM sales_returns sr
            LEFT JOIN customers c ON c.id=sr.customer_id
            LEFT JOIN sales_invoices si ON si.id=sr.sales_invoice_id
            LEFT JOIN journal_entries je ON je.id=sr.journal_entry_id
            LEFT JOIN journal_entries rev ON rev.reference_type='sales_return_cancel' AND rev.reference_id=sr.id
            WHERE sr.id=%s AND sr.company_id=%s AND sr.branch_id=%s
            LIMIT 1
            """,
            [return_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_return_items(return_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_return_items WHERE sales_return_id=%s ORDER BY id", [return_id])
        return dictfetchall(cursor)


def cancel_return(request, sales_return):
    if sales_return.get("reversal_id"):
        raise ValueError("This sales return already has a cancellation reversal journal.")
    user_id = request.session.get("user_id")
    timestamp = now_text()
    with transaction.atomic():
        reversal_id = reverse_journal_entry(sales_return["journal_entry_id"], today_iso(), f"Cancel sales return {sales_return['sales_return_no']}", user_id)
        with connection.cursor() as cursor:
            reverse_stock_movements("sales_return", sales_return["id"], f"Cancel sales return {sales_return['sales_return_no']}", user_id)
            cursor.execute("UPDATE journal_entries SET reference_type='sales_return_cancel', reference_id=%s, description=%s, updated_at=%s WHERE id=%s", [sales_return["id"], f"Cancellation reversal for sales return {sales_return['sales_return_no']}", timestamp, reversal_id])
            cursor.execute("UPDATE sales_returns SET status='Cancelled', updated_by_id=%s, updated_at=%s WHERE id=%s", [user_id, timestamp, sales_return["id"]])
            update_invoice_balance(cursor, sales_return["sales_invoice_id"], sales_return["grand_total"], user_id, timestamp, subtract=False)
    log_user_activity(request, "CANCEL", "Sales Returns", "sales_returns", sales_return["id"], f"Cancelled sales return {sales_return['sales_return_no']}.")


def mark_printed(request, sales_return):
    log_user_activity(request, "PRINT", "Sales Returns", "sales_returns", sales_return["id"], f"Printed sales return {sales_return['sales_return_no']}.")


def get_print_context(company_id, branch_id, return_id):
    sales_return = get_return(company_id, branch_id, return_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return {"sales_return": sales_return, "items": get_return_items(return_id), "company": company, "branch": branch, "print_date": today_iso()}
