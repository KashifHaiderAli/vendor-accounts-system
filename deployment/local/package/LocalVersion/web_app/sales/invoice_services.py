from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection, transaction

from accounts_module.accounting_engine import AccountingError, post_sales_invoice_entry, reverse_journal_entry
from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from core.calculation_utils import calculate_line_total
from core.edition_utils import is_tax_enabled
from core.inventory_utils import post_sales_invoice_stock, reverse_stock_movements, validate_available_stock
from core.print_utils import build_print_context
from settings_module.services import get_company_settings, get_numbering_settings, get_tax_settings, log_user_activity, now_text


PER_PAGE = 20
INVOICE_TYPES = ["tax_invoice", "cash_memo"]
INVOICE_TYPE_LABELS = {"tax_invoice": "Tax Invoice", "cash_memo": "Cash Memo"}
INVOICE_STATUSES = ["Draft", "Printed", "Partially Paid", "Paid", "Cancelled"]


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
    return {"page": page, "per_page": per_page, "total_count": total_count, "total_pages": total_pages, "offset": (page - 1) * per_page, "pages": list(range(1, total_pages + 1))}


def generate_invoice_no(company_id, branch_id, invoice_type):
    settings = get_numbering_settings(company_id, branch_id)
    prefix_field = "cash_memo_prefix" if invoice_type == "cash_memo" else "invoice_prefix"
    prefix = settings.get(prefix_field) or ("CM" if invoice_type == "cash_memo" else "INV")
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT invoice_no
            FROM sales_invoices
            WHERE company_id = %s AND branch_id = %s AND invoice_no LIKE %s
            ORDER BY invoice_no DESC
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


def list_invoices(company_id, branch_id, search="", invoice_type="", status="", date_from="", date_to="", page=1):
    clauses = ["si.company_id = %s", "si.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(si.invoice_no LIKE %s OR si.po_number LIKE %s OR dc.dc_no LIKE %s OR q.customer_name LIKE %s OR c.company_name LIKE %s)")
        params.extend([like, like, like, like, like])
    if invoice_type:
        clauses.append("si.invoice_type = %s")
        params.append(invoice_type)
    if status:
        clauses.append("si.status = %s")
        params.append(status)
    if date_from:
        clauses.append("si.invoice_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("si.invoice_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM sales_invoices si
            LEFT JOIN delivery_challans dc ON dc.id = si.delivery_challan_id
            LEFT JOIN customer_confirmations cc ON cc.id = si.confirmation_id
            LEFT JOIN quotations q ON q.id = COALESCE(dc.quotation_id, cc.quotation_id)
            LEFT JOIN customers c ON c.id = si.customer_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT si.*, dc.dc_no, COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM sales_invoices si
            LEFT JOIN delivery_challans dc ON dc.id = si.delivery_challan_id
            LEFT JOIN customer_confirmations cc ON cc.id = si.confirmation_id
            LEFT JOIN quotations q ON q.id = COALESCE(dc.quotation_id, cc.quotation_id)
            LEFT JOIN customers c ON c.id = si.customer_id
            WHERE {where_sql}
            ORDER BY si.invoice_date DESC, si.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        rows = dictfetchall(cursor)
    for row in rows:
        row["invoice_type_label"] = INVOICE_TYPE_LABELS.get(row.get("invoice_type"), row.get("invoice_type") or "-")
    return rows, pagination


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, customer_code, company_name, account_id, contact_person, phone, mobile, email, address, ntn, strn, payment_terms_id
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
        cursor.execute(
            "SELECT * FROM customers WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [customer_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, default_sale_rate, default_tax_rate, warranty_or_service_description
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
        cursor.execute("SELECT id FROM item_services WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [item_id, company_id, branch_id])
        return cursor.fetchone() is not None


def get_payment_terms(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name, days FROM payment_terms WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY name", [company_id, branch_id])
        return dictfetchall(cursor)


def payment_terms_exists(company_id, branch_id, payment_terms_id):
    if not payment_terms_id:
        return True
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM payment_terms WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [payment_terms_id, company_id, branch_id])
        return cursor.fetchone() is not None


def get_delivery_challan(company_id, branch_id, dc_id):
    if not dc_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dc.*, cc.quotation_id AS confirmation_quotation_id, cc.po_number AS confirmation_po_number,
                   q.customer_name AS quotation_customer_name, q.customer_address AS quotation_customer_address,
                   c.company_name AS customer_name
            FROM delivery_challans dc
            LEFT JOIN customer_confirmations cc ON cc.id = dc.confirmation_id
            LEFT JOIN quotations q ON q.id = dc.quotation_id
            LEFT JOIN customers c ON c.id = dc.customer_id
            WHERE dc.id=%s AND dc.company_id=%s AND dc.branch_id=%s AND dc.status <> 'Cancelled'
            LIMIT 1
            """,
            [dc_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["party_name"] = row.get("quotation_customer_name") or row.get("customer_name") or "Unregistered Party"
    return row


def get_confirmation(company_id, branch_id, confirmation_id):
    if not confirmation_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.*, q.customer_name AS quotation_customer_name, c.company_name AS customer_name
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.id=%s AND cc.company_id=%s AND cc.branch_id=%s AND cc.status <> 'Cancelled'
            LIMIT 1
            """,
            [confirmation_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["party_name"] = row.get("quotation_customer_name") or row.get("customer_name") or "Unregistered Party"
    return row


def get_quotation(company_id, branch_id, quotation_id):
    if not quotation_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT q.*, c.company_name AS master_customer_name
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            WHERE q.id=%s AND q.company_id=%s AND q.branch_id=%s AND q.status <> 'Cancelled'
            LIMIT 1
            """,
            [quotation_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["party_name"] = row.get("customer_name") or row.get("master_customer_name") or "Unregistered Party"
    return row


def get_delivery_challans(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dc.id, dc.dc_no, dc.customer_id, dc.confirmation_id, dc.quotation_id, dc.po_number,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM delivery_challans dc
            LEFT JOIN quotations q ON q.id = dc.quotation_id
            LEFT JOIN customers c ON c.id = dc.customer_id
            WHERE dc.company_id=%s AND dc.branch_id=%s AND dc.status <> 'Cancelled'
            ORDER BY dc.dc_date DESC, dc.id DESC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_confirmations(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.id, cc.confirmation_no, cc.customer_id, cc.quotation_id, cc.po_number,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.company_id=%s AND cc.branch_id=%s AND cc.status <> 'Cancelled'
            ORDER BY cc.confirmation_date DESC, cc.id DESC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_quotations(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT q.id, q.quotation_no, q.customer_id,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            WHERE q.company_id=%s AND q.branch_id=%s AND q.status <> 'Cancelled'
            ORDER BY q.quotation_date DESC, q.id DESC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def default_form_data(company_id, branch_id, invoice_type="tax_invoice", dc=None, confirmation=None, quotation=None):
    source_quote = quotation
    if dc and dc.get("quotation_id"):
        source_quote = get_quotation(company_id, branch_id, dc["quotation_id"])
    if confirmation and confirmation.get("quotation_id"):
        source_quote = get_quotation(company_id, branch_id, confirmation["quotation_id"])
    customer_id = (dc or confirmation or source_quote or {}).get("customer_id") or ""
    payment_terms_id = ""
    due_date = ""
    if customer_id:
        customer = get_customer(company_id, branch_id, customer_id)
        payment_terms_id = customer.get("payment_terms_id") if customer else ""
        if payment_terms_id:
            days = payment_terms_days(payment_terms_id)
            if days is not None:
                due_date = (date.today() + timedelta(days=int(days))).isoformat()
    return {
        "invoice_no": generate_invoice_no(company_id, branch_id, invoice_type),
        "invoice_date": today_iso(),
        "invoice_type": invoice_type,
        "customer_id": customer_id,
        "delivery_challan_id": dc.get("id") if dc else "",
        "confirmation_id": (dc or confirmation or {}).get("confirmation_id") or (confirmation.get("id") if confirmation else ""),
        "po_number": (dc or confirmation or {}).get("po_number") or "",
        "payment_terms_id": payment_terms_id or "",
        "due_date": due_date,
        "remarks": "",
        "status": "Draft",
        "subtotal": "0.00",
        "discount_total": "0.00",
        "tax_total": "0.00",
        "grand_total": "0.00",
        "received_amount": "0.00",
        "balance_amount": "0.00",
        "items": source_items(company_id, branch_id, dc, source_quote),
    }


def payment_terms_days(payment_terms_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT days FROM payment_terms WHERE id=%s LIMIT 1", [payment_terms_id])
        row = cursor.fetchone()
        return row[0] if row else None


def source_items(company_id, branch_id, dc=None, quotation=None):
    if quotation:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT item_service_id, description, quantity, rate, discount_percent, discount_amount, tax_percent
                FROM quotation_items
                WHERE quotation_id = %s
                ORDER BY id
                """,
                [quotation["id"]],
            )
            rows = dictfetchall(cursor)
        return [
            {
                "item_service_id": row.get("item_service_id") or "",
                "description": row.get("description") or "",
                "quantity": row.get("quantity") or "0",
                "rate": row.get("rate") or "0",
                "discount_percent": row.get("discount_percent") or "0",
                "discount_amount": row.get("discount_amount") or "0",
                "tax_percent": row.get("tax_percent") or default_tax(company_id, branch_id),
                "tax_amount": "0.00",
                "line_total": "0.00",
                "errors": {},
            }
            for row in rows
        ] or [empty_item_row(company_id, branch_id)]
    if dc:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT dci.item_service_id, dci.description, dci.quantity, i.default_sale_rate, i.default_tax_rate
                FROM delivery_challan_items dci
                LEFT JOIN item_services i ON i.id = dci.item_service_id
                WHERE dci.delivery_challan_id = %s
                ORDER BY dci.id
                """,
                [dc["id"]],
            )
            rows = dictfetchall(cursor)
        return [
            {
                "item_service_id": row.get("item_service_id") or "",
                "description": row.get("description") or "",
                "quantity": row.get("quantity") or "0",
                "rate": row.get("default_sale_rate") or "0",
                "discount_percent": "0",
                "discount_amount": "0",
                "tax_percent": row.get("default_tax_rate") or default_tax(company_id, branch_id),
                "tax_amount": "0.00",
                "line_total": "0.00",
                "errors": {},
            }
            for row in rows
        ] or [empty_item_row(company_id, branch_id)]
    return [empty_item_row(company_id, branch_id)]


def default_tax(company_id, branch_id):
    settings = get_tax_settings(company_id, branch_id) or {}
    return settings.get("default_sales_tax_percent") or "0"


def empty_item_row(company_id=None, branch_id=None):
    return {"item_service_id": "", "description": "", "quantity": "1.00", "rate": "0.00", "discount_percent": "0.00", "discount_amount": "0.00", "tax_percent": default_tax(company_id, branch_id) if company_id and branch_id else "0.00", "tax_amount": "0.00", "line_total": "0.00", "errors": {}}


def parse_post(post):
    rows = []
    item_ids = post.getlist("item_service_id[]")
    descriptions = post.getlist("description[]")
    quantities = post.getlist("quantity[]")
    rates = post.getlist("rate[]")
    discount_percents = post.getlist("discount_percent[]")
    discount_amounts = post.getlist("discount_amount[]")
    tax_percents = post.getlist("tax_percent[]")
    for index, description in enumerate(descriptions):
        rows.append({
            "item_service_id": item_ids[index] if index < len(item_ids) else "",
            "description": description,
            "quantity": quantities[index] if index < len(quantities) else "",
            "rate": rates[index] if index < len(rates) else "",
            "discount_percent": discount_percents[index] if index < len(discount_percents) else "",
            "discount_amount": discount_amounts[index] if index < len(discount_amounts) else "",
            "tax_percent": tax_percents[index] if index < len(tax_percents) else "",
        })
    return {
        "invoice_no": post.get("invoice_no", ""),
        "invoice_date": post.get("invoice_date", ""),
        "invoice_type": post.get("invoice_type", "tax_invoice"),
        "customer_id": post.get("customer_id", ""),
        "delivery_challan_id": post.get("delivery_challan_id", ""),
        "confirmation_id": post.get("confirmation_id", ""),
        "po_number": post.get("po_number", ""),
        "payment_terms_id": post.get("payment_terms_id", ""),
        "due_date": post.get("due_date", ""),
        "remarks": post.get("remarks", ""),
        "status": post.get("status", "Draft"),
        "received_amount": "0",
        "items": rows,
    }


def invoice_no_exists(company_id, branch_id, invoice_no, exclude_id=None):
    params = [company_id, branch_id, invoice_no]
    clause = "company_id=%s AND branch_id=%s AND lower(invoice_no)=lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM sales_invoices WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_and_calculate(data, company_id, branch_id, invoice_id=None):
    errors = {}
    cleaned = {}
    cleaned["invoice_no"], errors["invoice_no"] = validators.clean_text(data.get("invoice_no"), max_length=50, required=True, field_name="Invoice No")
    if not errors["invoice_no"] and invoice_no_exists(company_id, branch_id, cleaned["invoice_no"], invoice_id):
        errors["invoice_no"] = "Invoice No already exists for the current branch."
    inv_date, errors["invoice_date"] = validators.validate_date(data.get("invoice_date"), "Invoice Date", required=True)
    cleaned["invoice_date"] = inv_date.isoformat() if inv_date else ""
    invoice_type = data.get("invoice_type") or "tax_invoice"
    if not is_tax_enabled(company_id=company_id):
        invoice_type = "cash_memo"
    errors["invoice_type"] = validators.validate_choice(invoice_type, INVOICE_TYPES, "Invoice Type")
    cleaned["invoice_type"] = invoice_type

    dc = get_delivery_challan(company_id, branch_id, data.get("delivery_challan_id"))
    confirmation = get_confirmation(company_id, branch_id, data.get("confirmation_id"))
    if data.get("delivery_challan_id") and not dc:
        errors["delivery_challan_id"] = "Selected delivery challan was not found."
    if data.get("confirmation_id") and not confirmation:
        errors["confirmation_id"] = "Selected confirmation was not found."
    customer_id = data.get("customer_id") or (dc or {}).get("customer_id") or (confirmation or {}).get("customer_id") or ""
    customer = get_customer(company_id, branch_id, customer_id)
    if not customer:
        errors["customer_id"] = "Customer is required before posting invoice. Add the quotation party as customer first."
    elif not customer.get("account_id"):
        errors["customer_id"] = "Selected customer has no linked receivable account. Please fix Customer Master first."
    cleaned["customer_id"] = customer_id
    cleaned["customer_account_id"] = customer.get("account_id") if customer else None
    cleaned["delivery_challan_id"] = (dc or {}).get("id") or None
    cleaned["confirmation_id"] = (confirmation or {}).get("id") or None
    cleaned["po_number"], errors["po_number"] = validators.clean_text(data.get("po_number"), max_length=100, field_name="PO Number")
    if data.get("payment_terms_id") and not payment_terms_exists(company_id, branch_id, data.get("payment_terms_id")):
        errors["payment_terms_id"] = "Selected payment terms were not found."
    cleaned["payment_terms_id"] = data.get("payment_terms_id") or None
    due_date, errors["due_date"] = validators.validate_date(data.get("due_date"), "Due Date", required=False)
    cleaned["due_date"] = due_date.isoformat() if due_date else None
    if inv_date and due_date and due_date < inv_date:
        errors["due_date"] = "Due Date cannot be before Invoice Date."
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")

    rows, item_error, totals = calculate_items(data.get("items") or [], company_id, branch_id)
    cleaned["items"] = rows
    if item_error:
        errors["items"] = item_error
    if totals["grand_total"] <= 0:
        errors["grand_total"] = "Grand Total must be greater than zero."
    if not cleaned.get("delivery_challan_id"):
        for row in rows:
            if row.get("item_service_id") and not row.get("errors"):
                try:
                    validate_available_stock(company_id, branch_id, row["item_service_id"], row["quantity"], "Sales Invoice")
                except ValueError as exc:
                    row.setdefault("errors", {})["quantity"] = str(exc)
                    errors["items"] = "Please correct item row errors."
    cleaned["received_amount"] = "0.00"
    cleaned["balance_amount"] = format_money(totals["grand_total"])
    cleaned["subtotal"] = format_money(totals["subtotal"])
    cleaned["discount_total"] = format_money(totals["discount_total"])
    cleaned["tax_total"] = format_money(totals["tax_total"])
    cleaned["grand_total"] = format_money(totals["grand_total"])
    status = data.get("status") or "Draft"
    errors["status"] = validators.validate_choice(status, INVOICE_STATUSES, "Status")
    cleaned["status"] = status
    return {k: v for k, v in errors.items() if v}, {**data, **cleaned}


def calculate_items(items, company_id, branch_id):
    tax_enabled = is_tax_enabled(company_id=company_id)
    rows = []
    has_error = False
    totals = {"subtotal": Decimal("0.00"), "discount_total": Decimal("0.00"), "tax_total": Decimal("0.00"), "grand_total": Decimal("0.00")}
    for raw in items:
        if not any(str(raw.get(key) or "").strip() for key in ["item_service_id", "description", "quantity", "rate"]):
            continue
        errors = {}
        item_id = raw.get("item_service_id") or ""
        if item_id and not item_exists(company_id, branch_id, item_id):
            errors["item_service_id"] = "Selected item/service was not found."
        description, errors["description"] = validators.clean_text(raw.get("description"), required=True, field_name="Description")
        quantity, errors["quantity"] = validators.validate_decimal(raw.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        rate, errors["rate"] = validators.validate_money(raw.get("rate"), "Rate", allow_negative=False)
        discount_percent, errors["discount_percent"] = validators.validate_percentage(raw.get("discount_percent") or 0, "Discount Percent")
        posted_discount, errors["discount_amount"] = validators.validate_money(raw.get("discount_amount") or 0, "Discount Amount", allow_negative=False)
        tax_input = 0 if not tax_enabled else (raw.get("tax_percent") or default_tax(company_id, branch_id))
        tax_percent, errors["tax_percent"] = validators.validate_percentage(tax_input, "Tax Percent")
        quantity = quantity or Decimal("0")
        rate = rate or Decimal("0")
        discount_percent = discount_percent or Decimal("0")
        posted_discount = posted_discount or Decimal("0")
        tax_percent = Decimal("0") if not tax_enabled else (tax_percent or Decimal("0"))
        base = (quantity * rate).quantize(Decimal("0.01"))
        if posted_discount > base:
            errors["discount_amount"] = "Discount Amount cannot exceed Quantity x Rate."
        line = calculate_line_total(quantity, rate, discount_percent, posted_discount, tax_percent, "tax_exclusive")
        discount = line["discount_amount"]
        tax_amount = line["tax_amount"]
        line_total = line["line_total"]
        errors = {k: v for k, v in errors.items() if v}
        if errors:
            has_error = True
        totals["subtotal"] += base
        totals["discount_total"] += discount
        totals["tax_total"] += tax_amount
        totals["grand_total"] += line_total
        rows.append({"item_service_id": item_id, "description": description, "quantity": str(quantity.quantize(Decimal("0.01"))), "rate": format_money(rate), "discount_percent": str(discount_percent.quantize(Decimal("0.01"))), "discount_amount": format_money(discount), "tax_percent": str(tax_percent.quantize(Decimal("0.01"))), "tax_amount": format_money(tax_amount), "line_total": format_money(line_total), "errors": errors})
    if not rows:
        return [empty_item_row(company_id, branch_id)], "At least one invoice item is required.", totals
    return rows, "Please correct item row errors." if has_error else None, totals


def save_invoice(company_id, branch_id, user_id, data, invoice_id=None):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if invoice_id:
                cursor.execute(
                    """
                    UPDATE sales_invoices
                    SET po_number=%s, payment_terms_id=%s, due_date=%s, remarks=%s, updated_by_id=%s, updated_at=%s
                    WHERE id=%s AND company_id=%s AND branch_id=%s
                    """,
                    [data.get("po_number"), data.get("payment_terms_id"), data.get("due_date"), data.get("remarks"), user_id, timestamp, invoice_id, company_id, branch_id],
                )
                return invoice_id
            cursor.execute(
                """
                INSERT INTO sales_invoices (
                    company_id, branch_id, invoice_no, invoice_date, invoice_type, customer_id,
                    delivery_challan_id, confirmation_id, po_number, payment_terms_id, due_date,
                    subtotal, discount_total, tax_total, grand_total, received_amount, balance_amount,
                    status, journal_entry_id, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
                """,
                [company_id, branch_id] + header_values(data) + [user_id, user_id, timestamp, timestamp],
            )
            saved_id = cursor.lastrowid
            insert_items(cursor, saved_id, data["items"], timestamp)
            journal_id = post_sales_invoice_entry(company_id, branch_id, data["customer_account_id"], data["invoice_date"], saved_id, data["subtotal"], data["discount_total"], data["tax_total"], data["grand_total"], user_id)
            cursor.execute("UPDATE sales_invoices SET journal_entry_id=%s WHERE id=%s", [journal_id, saved_id])
            post_sales_invoice_stock(company_id, branch_id, saved_id, user_id)
            if data.get("delivery_challan_id"):
                cursor.execute("UPDATE delivery_challans SET status='Invoiced', updated_by_id=%s, updated_at=%s WHERE id=%s", [user_id, timestamp, data["delivery_challan_id"]])
            if data.get("confirmation_id"):
                cursor.execute("UPDATE customer_confirmations SET status='Invoiced', updated_by_id=%s, updated_at=%s WHERE id=%s", [user_id, timestamp, data["confirmation_id"]])
    return saved_id


def header_values(data):
    return [data["invoice_no"], data["invoice_date"], data["invoice_type"], data["customer_id"], data.get("delivery_challan_id") or None, data.get("confirmation_id") or None, data.get("po_number"), data.get("payment_terms_id") or None, data.get("due_date") or None, data["subtotal"], data["discount_total"], data["tax_total"], data["grand_total"], data["received_amount"], data["balance_amount"], data.get("status") or "Draft", data.get("remarks")]


def insert_items(cursor, invoice_id, items, timestamp):
    for row in items:
        cursor.execute(
            """
            INSERT INTO sales_invoice_items (
                sales_invoice_id, item_service_id, description, quantity, rate,
                discount_percent, discount_amount, tax_percent, tax_amount, line_total,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [invoice_id, row.get("item_service_id") or None, row["description"], row["quantity"], row["rate"], row["discount_percent"], row["discount_amount"], row["tax_percent"], row["tax_amount"], row["line_total"], timestamp, timestamp],
        )


def get_invoice(company_id, branch_id, invoice_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT si.*, c.customer_code, c.company_name, c.contact_person, c.address AS customer_address, c.phone AS customer_phone,
                   c.ntn AS customer_ntn, c.strn AS customer_strn, dc.dc_no, cc.confirmation_no,
                   je.entry_no AS journal_entry_no, pt.name AS payment_terms_name,
                   cb.full_name AS created_by_name, ub.full_name AS updated_by_name
            FROM sales_invoices si
            LEFT JOIN customers c ON c.id = si.customer_id
            LEFT JOIN delivery_challans dc ON dc.id = si.delivery_challan_id
            LEFT JOIN customer_confirmations cc ON cc.id = si.confirmation_id
            LEFT JOIN journal_entries je ON je.id = si.journal_entry_id
            LEFT JOIN payment_terms pt ON pt.id = si.payment_terms_id
            LEFT JOIN users cb ON cb.id = si.created_by_id
            LEFT JOIN users ub ON ub.id = si.updated_by_id
            WHERE si.id=%s AND si.company_id=%s AND si.branch_id=%s
            LIMIT 1
            """,
            [invoice_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["invoice_type_label"] = INVOICE_TYPE_LABELS.get(row.get("invoice_type"), row.get("invoice_type") or "-")
    return row


def get_invoice_items(invoice_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sii.*, i.item_code, i.item_name
            FROM sales_invoice_items sii
            LEFT JOIN item_services i ON i.id = sii.item_service_id
            WHERE sii.sales_invoice_id=%s
            ORDER BY sii.id
            """,
            [invoice_id],
        )
        return dictfetchall(cursor)


def active_invoice_for_source(company_id, branch_id, field_name, source_id, exclude_id=None):
    if not source_id:
        return None
    params = [company_id, branch_id, source_id]
    clause = f"company_id=%s AND branch_id=%s AND {field_name}=%s AND status <> 'Cancelled'"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM sales_invoices WHERE {clause} LIMIT 1", params)
        return dictfetchone(cursor)


def invoice_has_future_receipts(_invoice_id):
    return False


def cancel_invoice(request, invoice):
    if invoice.get("status") == "Cancelled":
        raise ValueError("This invoice is already cancelled.")
    if invoice_has_future_receipts(invoice["id"]):
        raise ValueError("This invoice has receipts and cannot be cancelled.")
    timestamp = now_text()
    company_id, branch_id = get_scope(request)
    with transaction.atomic():
        reversal_id = None
        if invoice.get("journal_entry_id"):
            reversal_id = reverse_journal_entry(invoice["journal_entry_id"], today_iso(), f"Cancel sales invoice {invoice['invoice_no']}", request.session.get("user_id"))
            with connection.cursor() as cursor:
                cursor.execute("UPDATE journal_entries SET reference_type='sales_invoice_cancel', reference_id=%s WHERE id=%s", [invoice["id"], reversal_id])
        with connection.cursor() as cursor:
            reverse_stock_movements("sales_invoice", invoice["id"], f"Cancel sales invoice {invoice['invoice_no']}", request.session.get("user_id"))
            cursor.execute("UPDATE sales_invoices SET status='Cancelled', updated_by_id=%s, updated_at=%s WHERE id=%s AND company_id=%s AND branch_id=%s", [request.session.get("user_id"), timestamp, invoice["id"], company_id, branch_id])
            if invoice.get("delivery_challan_id") and not active_invoice_for_source(company_id, branch_id, "delivery_challan_id", invoice["delivery_challan_id"], invoice["id"]):
                dc_status = "Signed Received" if source_dc_signed(invoice["delivery_challan_id"]) else "Printed"
                cursor.execute("UPDATE delivery_challans SET status=%s, updated_by_id=%s, updated_at=%s WHERE id=%s", [dc_status, request.session.get("user_id"), timestamp, invoice["delivery_challan_id"]])
            if invoice.get("confirmation_id") and not active_invoice_for_source(company_id, branch_id, "confirmation_id", invoice["confirmation_id"], invoice["id"]):
                cursor.execute("UPDATE customer_confirmations SET status='Open', updated_by_id=%s, updated_at=%s WHERE id=%s", [request.session.get("user_id"), timestamp, invoice["confirmation_id"]])
    log_user_activity(request, "CANCEL", "Sales Invoices", "sales_invoices", invoice["id"], f"Cancelled invoice {invoice['invoice_no']}.")
    return reversal_id


def source_dc_signed(dc_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT signed_copy_path FROM delivery_challans WHERE id=%s LIMIT 1", [dc_id])
        row = cursor.fetchone()
        return bool(row and row[0])


def mark_printed(request, invoice, digital=False):
    if invoice.get("status") == "Draft":
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE sales_invoices SET status='Printed', updated_by_id=%s, updated_at=%s WHERE id=%s", [request.session.get("user_id"), timestamp, invoice["id"]])
    label = "Digital printed" if digital else "Printed"
    log_user_activity(request, "PRINT", "Sales Invoices", "sales_invoices", invoice["id"], f"{label} invoice {invoice['invoice_no']}.")


def get_print_context(company_id, branch_id, invoice_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor) or {}
        cursor.execute("SELECT * FROM branches WHERE id=%s AND company_id=%s LIMIT 1", [branch_id, company_id])
        branch = dictfetchone(cursor) or {}
    return {"company": company, "branch": branch, "company_settings": get_company_settings(company_id, branch_id) or {}, "tax_settings": get_tax_settings(company_id, branch_id) or {}, "invoice": get_invoice(company_id, branch_id, invoice_id), "items": get_invoice_items(invoice_id), "print_date": today_iso(), **build_print_context(company_id)}
