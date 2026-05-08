from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection, transaction

from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from masters.master_utils import create_linked_account
from settings_module.services import get_company_settings, get_numbering_settings, get_tax_settings, log_user_activity, now_text


PER_PAGE = 20
TAX_OPTIONS = ["no_tax", "tax_inclusive", "tax_exclusive"]
STATUSES = ["Draft", "Printed", "Converted", "Cancelled"]


def today_iso():
    return date.today().isoformat()


def format_money(value):
    return str(Decimal(str(value or "0")).quantize(Decimal("0.01")))


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
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1,
        "next_page": page + 1,
    }


def list_quotations(company_id, branch_id, search="", status="", date_from="", date_to="", page=1):
    clauses = ["q.company_id = %s", "q.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append("(q.quotation_no LIKE %s OR q.subject LIKE %s OR q.customer_name LIKE %s OR c.company_name LIKE %s)")
        params.extend([like, like, like, like])
    if status:
        clauses.append("q.status = %s")
        params.append(status)
    if date_from:
        clauses.append("q.quotation_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("q.quotation_date <= %s")
        params.append(date_to)

    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT q.*, COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS display_customer_name
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            WHERE {where_sql}
            ORDER BY q.quotation_date DESC, q.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        rows = dictfetchall(cursor)
    for row in rows:
        row["display_status"] = display_status(row)
    return rows, pagination


def display_status(quotation):
    status = quotation.get("status") or "Draft"
    valid_till = quotation.get("valid_till")
    if status not in {"Converted", "Cancelled"} and valid_till and str(valid_till) < today_iso():
        return "Expired"
    return status


def get_quotation(company_id, branch_id, quotation_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT q.*, c.company_name AS master_customer_name, c.address AS master_customer_address,
                   c.phone AS master_customer_phone, c.mobile AS master_customer_mobile, c.email AS master_customer_email,
                   c.ntn AS master_customer_ntn, c.strn AS master_customer_strn,
                   pt.name AS payment_terms_name, pt.days AS payment_terms_days,
                   cb.full_name AS created_by_name, ub.full_name AS updated_by_name
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            LEFT JOIN payment_terms pt ON pt.id = q.payment_terms_id
            LEFT JOIN users cb ON cb.id = q.created_by_id
            LEFT JOIN users ub ON ub.id = q.updated_by_id
            WHERE q.id = %s AND q.company_id = %s AND q.branch_id = %s
            LIMIT 1
            """,
            [quotation_id, company_id, branch_id],
        )
        quotation = dictfetchone(cursor)
    if quotation:
        quotation["display_status"] = display_status(quotation)
        apply_customer_display_fields(quotation)
    return quotation


def apply_customer_display_fields(quotation):
    quotation["display_customer_name"] = quotation.get("customer_name") or quotation.get("master_customer_name") or ""
    quotation["display_customer_address"] = quotation.get("customer_address") or quotation.get("master_customer_address") or ""
    quotation["display_customer_phone"] = quotation.get("customer_phone") or quotation.get("master_customer_phone") or ""
    quotation["display_customer_mobile"] = quotation.get("customer_mobile") or quotation.get("master_customer_mobile") or ""
    quotation["display_customer_email"] = quotation.get("customer_email") or quotation.get("master_customer_email") or ""
    quotation["display_customer_ntn"] = quotation.get("customer_ntn") or quotation.get("master_customer_ntn") or ""
    quotation["display_customer_strn"] = quotation.get("customer_strn") or quotation.get("master_customer_strn") or ""


def get_quotation_items(quotation_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT qi.*, i.item_code, i.item_name
            FROM quotation_items qi
            LEFT JOIN item_services i ON i.id = qi.item_service_id
            WHERE qi.quotation_id = %s
            ORDER BY qi.id ASC
            """,
            [quotation_id],
        )
        return dictfetchall(cursor)


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, customer_code, company_name, contact_person, payment_terms_id,
                   address, phone, mobile, email, ntn, strn
            FROM customers
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY company_name ASC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, default_sale_rate, default_tax_rate,
                   warranty_or_service_description
            FROM item_services
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY item_name ASC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_payment_terms(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, name, days
            FROM payment_terms
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY name ASC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def customer_exists(company_id, branch_id, customer_id):
    if not customer_id:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM customers WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [customer_id, company_id, branch_id],
        )
        return cursor.fetchone() is not None


def get_customer(company_id, branch_id, customer_id):
    if not customer_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM customers
            WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1
            LIMIT 1
            """,
            [customer_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def item_exists(company_id, branch_id, item_id):
    if not item_id:
        return True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM item_services WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [item_id, company_id, branch_id],
        )
        return cursor.fetchone() is not None


def payment_terms_exists(company_id, branch_id, payment_terms_id):
    if not payment_terms_id:
        return True
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM payment_terms WHERE id = %s AND company_id = %s AND branch_id = %s AND is_active = 1 LIMIT 1",
            [payment_terms_id, company_id, branch_id],
        )
        return cursor.fetchone() is not None


def quotation_no_exists(company_id, branch_id, quotation_no, exclude_id=None):
    params = [company_id, branch_id, quotation_no]
    clause = "company_id = %s AND branch_id = %s AND lower(quotation_no) = lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM quotations WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def generate_document_number(company_id, branch_id, document_type):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get(f"{document_type}_prefix") or "DOC"
    padding = int(settings.get("number_padding") or 4)
    use_year = int(settings.get("use_year_in_number") or 0) == 1
    year = str(date.today().year)
    doc_prefix = f"{prefix}-{year}-" if use_year else f"{prefix}-"
    like = f"{doc_prefix}%"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT quotation_no
            FROM quotations
            WHERE company_id = %s AND branch_id = %s AND quotation_no LIKE %s
            ORDER BY quotation_no DESC
            LIMIT 1
            """,
            [company_id, branch_id, like],
        )
        row = cursor.fetchone()
    next_number = 1
    if row:
        try:
            next_number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            next_number = 1
    return f"{doc_prefix}{next_number:0{padding}d}"


def generate_master_number(company_id, branch_id, prefix_field, table_name, code_field):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get(prefix_field) or "CUS"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {code_field}
            FROM {table_name}
            WHERE company_id = %s AND branch_id = %s AND {code_field} LIKE %s
            ORDER BY {code_field} DESC
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


def default_form_data(company_id, branch_id):
    quotation_date = date.today()
    validity_days = 15
    tax_settings = get_tax_settings(company_id, branch_id)
    return {
        "quotation_no": generate_document_number(company_id, branch_id, "quotation"),
        "quotation_date": quotation_date.isoformat(),
        "customer_id": "",
        "customer_mode": "existing",
        "customer_name": "",
        "customer_phone": "",
        "customer_mobile": "",
        "customer_email": "",
        "customer_address": "",
        "customer_ntn": "",
        "customer_strn": "",
        "is_customer_saved": 0,
        "contact_person": "",
        "subject": "",
        "validity_days": validity_days,
        "valid_till": (quotation_date + timedelta(days=validity_days)).isoformat(),
        "payment_terms_id": "",
        "tax_option": "tax_exclusive" if int(tax_settings.get("default_tax_applicable") or 0) else "no_tax",
        "terms_conditions": "",
        "remarks": "",
        "status": "Draft",
        "subtotal": "0.00",
        "discount_total": "0.00",
        "tax_total": "0.00",
        "grand_total": "0.00",
        "items": [empty_item_row(tax_settings.get("default_sales_tax_percent") or 0)],
    }


def empty_item_row(default_tax=0):
    return {
        "item_service_id": "",
        "description": "",
        "quantity": "1.00",
        "rate": "0.00",
        "discount_percent": "0.00",
        "discount_amount": "0.00",
        "tax_percent": str(default_tax or "0"),
        "tax_amount": "0.00",
        "line_total": "0.00",
        "errors": {},
    }


def parse_quotation_post(post):
    data = {
        "quotation_no": post.get("quotation_no", "").strip().upper(),
        "quotation_date": post.get("quotation_date", "").strip(),
        "customer_id": post.get("customer_id") or "",
        "customer_mode": post.get("customer_mode", "existing").strip() or "existing",
        "customer_name": post.get("customer_name", "").strip(),
        "customer_phone": post.get("customer_phone", "").strip(),
        "customer_mobile": post.get("customer_mobile", "").strip(),
        "customer_email": post.get("customer_email", "").strip(),
        "customer_address": post.get("customer_address", "").strip(),
        "customer_ntn": post.get("customer_ntn", "").strip(),
        "customer_strn": post.get("customer_strn", "").strip(),
        "contact_person": post.get("contact_person", "").strip(),
        "subject": post.get("subject", "").strip(),
        "validity_days": post.get("validity_days", "").strip(),
        "valid_till": post.get("valid_till", "").strip(),
        "payment_terms_id": post.get("payment_terms_id") or "",
        "tax_option": post.get("tax_option", "").strip() or "no_tax",
        "terms_conditions": post.get("terms_conditions", "").strip(),
        "remarks": post.get("remarks", "").strip(),
        "status": post.get("status", "").strip() or "Draft",
        "items": [],
    }
    fields = ["item_service_id", "description", "quantity", "rate", "discount_percent", "discount_amount", "tax_percent"]
    lists = {field: post.getlist(f"{field}[]") for field in fields}
    max_rows = max([len(values) for values in lists.values()] + [0])
    for index in range(max_rows):
        row = {}
        for field in fields:
            values = lists[field]
            row[field] = values[index].strip() if index < len(values) and values[index] is not None else ""
        row["errors"] = {}
        if any(str(row.get(field) or "").strip() for field in fields):
            data["items"].append(row)
    return data


def validate_and_calculate(data, company_id, branch_id, quotation_id=None):
    errors = {}
    item_errors = []
    cleaned, error = validators.clean_text(data.get("quotation_no"), max_length=50, required=True, field_name="Quotation No")
    data["quotation_no"] = cleaned.upper()
    if error:
        errors["quotation_no"] = error
    elif quotation_no_exists(company_id, branch_id, data["quotation_no"], quotation_id):
        errors["quotation_no"] = "Quotation No already exists for the current branch."

    quotation_date, error = validators.validate_date(data.get("quotation_date"), "Quotation Date", required=True)
    if error:
        errors["quotation_date"] = error
    validity_days, error = validators.validate_integer(data.get("validity_days"), "Validity Days", min_value=0, required=True)
    if error:
        errors["validity_days"] = error
    valid_till, error = validators.validate_date(data.get("valid_till"), "Valid Till")
    if error:
        errors["valid_till"] = error
    if quotation_date and valid_till and valid_till < quotation_date:
        errors["valid_till"] = "Valid Till cannot be before Quotation Date."

    customer_mode_error = validators.validate_choice(data.get("customer_mode"), ["existing", "new"], "Customer Mode")
    if customer_mode_error:
        errors["customer_mode"] = customer_mode_error

    if data.get("customer_mode") == "existing":
        customer = get_customer(company_id, branch_id, data.get("customer_id"))
        if not data.get("customer_id"):
            errors["customer_id"] = "Customer is required."
        elif not customer:
            errors["customer_id"] = "Selected customer was not found."
        else:
            copy_customer_snapshot(data, customer)
            data["is_customer_saved"] = 1
    else:
        data["customer_id"] = ""
        data["is_customer_saved"] = 0
        data["customer_name"], error = validators.clean_text(data.get("customer_name"), max_length=200, required=True, field_name="Customer Name")
        if error:
            errors["customer_name"] = error
        data["customer_phone"], error = validators.validate_phone(data.get("customer_phone"), "Customer Phone")
        if error:
            errors["customer_phone"] = error
        data["customer_mobile"], error = validators.validate_mobile(data.get("customer_mobile"), "Customer Mobile")
        if error:
            errors["customer_mobile"] = error
        data["customer_email"], error = validators.validate_email(data.get("customer_email"), "Customer Email")
        if error:
            errors["customer_email"] = error
        for field, label, max_length in [
            ("customer_ntn", "Customer NTN", 100),
            ("customer_strn", "Customer STRN", 100),
        ]:
            data[field], error = validators.clean_text(data.get(field), max_length=max_length, field_name=label)
            if error:
                errors[field] = error

    data["contact_person"], error = validators.clean_text(data.get("contact_person"), max_length=150, field_name="Contact Person")
    if error:
        errors["contact_person"] = error
    data["subject"], error = validators.clean_text(data.get("subject"), max_length=255, field_name="Subject")
    if error:
        errors["subject"] = error

    if data.get("payment_terms_id") and not payment_terms_exists(company_id, branch_id, data["payment_terms_id"]):
        errors["payment_terms_id"] = "Selected payment terms were not found."

    choice_error = validators.validate_choice(data.get("tax_option"), TAX_OPTIONS, "Tax Option")
    if choice_error:
        errors["tax_option"] = choice_error
    status_error = validators.validate_choice(data.get("status"), STATUSES, "Status")
    if status_error:
        errors["status"] = status_error

    calculated_items, totals = calculate_items(data.get("items") or [], data.get("tax_option"), company_id, branch_id)
    for row in calculated_items:
        item_errors.append(row.get("errors") or {})
    if not calculated_items:
        errors["items"] = "At least one item line is required."
    elif any(item_errors):
        errors["items"] = "Please correct the highlighted item row errors."

    data["items"] = calculated_items
    data.update(totals)
    data["quotation_date"] = quotation_date.isoformat() if quotation_date else data.get("quotation_date")
    data["validity_days"] = validity_days if validity_days is not None else data.get("validity_days")
    data["valid_till"] = valid_till.isoformat() if valid_till else ""
    return errors, data


def copy_customer_snapshot(data, customer):
    data["customer_name"] = customer.get("company_name") or ""
    data["customer_phone"] = customer.get("phone") or ""
    data["customer_mobile"] = customer.get("mobile") or ""
    data["customer_email"] = customer.get("email") or ""
    data["customer_address"] = customer.get("address") or ""
    data["customer_ntn"] = customer.get("ntn") or ""
    data["customer_strn"] = customer.get("strn") or ""
    if not data.get("contact_person"):
        data["contact_person"] = customer.get("contact_person") or ""
    if not data.get("payment_terms_id"):
        data["payment_terms_id"] = customer.get("payment_terms_id") or ""


def calculate_items(items, tax_option, company_id, branch_id):
    calculated = []
    totals = {
        "subtotal": Decimal("0.00"),
        "discount_total": Decimal("0.00"),
        "tax_total": Decimal("0.00"),
        "grand_total": Decimal("0.00"),
    }
    for row in items:
        errors = {}
        item_id = row.get("item_service_id") or ""
        if item_id and not item_exists(company_id, branch_id, item_id):
            errors["item_service_id"] = "Selected item/service was not found."
        description, error = validators.clean_text(row.get("description"), required=True, field_name="Description")
        if error:
            errors["description"] = error
        quantity, error = validators.validate_decimal(row.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        if error:
            errors["quantity"] = error
        rate, error = validators.validate_money(row.get("rate"), "Rate", allow_negative=False)
        if error:
            errors["rate"] = error
        discount_percent, error = validators.validate_percentage(row.get("discount_percent") or 0, "Discount Percent")
        if error:
            errors["discount_percent"] = error
        posted_discount, error = validators.validate_money(row.get("discount_amount") or 0, "Discount Amount", allow_negative=False)
        if error:
            errors["discount_amount"] = error
        tax_percent, error = validators.validate_percentage(row.get("tax_percent") or 0, "Tax Percent")
        if error:
            errors["tax_percent"] = error

        quantity = quantity or Decimal("0")
        rate = rate or Decimal("0")
        discount_percent = discount_percent or Decimal("0")
        posted_discount = posted_discount or Decimal("0")
        tax_percent = Decimal("0") if tax_option == "no_tax" else (tax_percent or Decimal("0"))

        gross = (quantity * rate).quantize(Decimal("0.01"))
        discount_amount = (gross * discount_percent / Decimal("100")).quantize(Decimal("0.01")) if discount_percent > 0 else posted_discount
        if discount_amount > gross:
            errors["discount_amount"] = "Discount Amount cannot exceed Quantity x Rate."
        net_amount = gross - discount_amount
        if net_amount < 0:
            errors["line_total"] = "Line total cannot be negative."
            net_amount = Decimal("0.00")

        if tax_option == "tax_exclusive":
            tax_amount = (net_amount * tax_percent / Decimal("100")).quantize(Decimal("0.01"))
            line_total = net_amount + tax_amount
        elif tax_option == "tax_inclusive" and tax_percent > 0:
            divisor = Decimal("100") + tax_percent
            tax_amount = (net_amount * tax_percent / divisor).quantize(Decimal("0.01"))
            line_total = net_amount
        else:
            tax_amount = Decimal("0.00")
            line_total = net_amount

        totals["subtotal"] += gross
        totals["discount_total"] += discount_amount
        totals["tax_total"] += tax_amount
        totals["grand_total"] += line_total
        calculated.append(
            {
                "item_service_id": item_id,
                "description": description,
                "quantity": str(quantity.quantize(Decimal("0.01"))),
                "rate": format_money(rate),
                "discount_percent": str(discount_percent.quantize(Decimal("0.01"))),
                "discount_amount": format_money(discount_amount),
                "tax_percent": str(tax_percent.quantize(Decimal("0.01"))),
                "tax_amount": format_money(tax_amount),
                "line_total": format_money(line_total),
                "errors": errors,
            }
        )
    return calculated, {key: format_money(value) for key, value in totals.items()}


def save_quotation(company_id, branch_id, user_id, data, quotation_id=None):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if quotation_id:
                cursor.execute(
                    """
                    UPDATE quotations
                    SET quotation_no = %s, quotation_date = %s, customer_id = %s,
                        customer_name = %s, customer_phone = %s, customer_mobile = %s,
                        customer_email = %s, customer_address = %s, customer_ntn = %s,
                        customer_strn = %s, is_customer_saved = %s, contact_person = %s,
                        subject = %s, validity_days = %s, valid_till = %s,
                        payment_terms_id = %s, tax_option = %s,
                        subtotal = %s, discount_total = %s, tax_total = %s,
                        grand_total = %s, terms_conditions = %s, remarks = %s,
                        status = %s, updated_by_id = %s, updated_at = %s
                    WHERE id = %s AND company_id = %s AND branch_id = %s
                    """,
                    header_values(data)
                    + [user_id, timestamp, quotation_id, company_id, branch_id],
                )
                cursor.execute("DELETE FROM quotation_items WHERE quotation_id = %s", [quotation_id])
                saved_id = quotation_id
            else:
                cursor.execute(
                    """
                    INSERT INTO quotations (
                        company_id, branch_id, quotation_no, quotation_date, customer_id,
                        customer_name, customer_phone, customer_mobile, customer_email,
                        customer_address, customer_ntn, customer_strn, is_customer_saved,
                        contact_person, subject, validity_days, valid_till, payment_terms_id,
                        tax_option, subtotal, discount_total, tax_total, grand_total,
                        terms_conditions, remarks, status, created_by_id, updated_by_id,
                        created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [company_id, branch_id] + header_values(data) + [user_id, user_id, timestamp, timestamp],
                )
                saved_id = cursor.lastrowid
            insert_items(cursor, saved_id, data["items"], timestamp)
    return saved_id


def header_values(data):
    return [
        data["quotation_no"],
        data["quotation_date"],
        data.get("customer_id") or None,
        data.get("customer_name"),
        data.get("customer_phone"),
        data.get("customer_mobile"),
        data.get("customer_email"),
        data.get("customer_address"),
        data.get("customer_ntn"),
        data.get("customer_strn"),
        data.get("is_customer_saved") or 0,
        data.get("contact_person"),
        data.get("subject"),
        data.get("validity_days") or 0,
        data.get("valid_till") or None,
        data.get("payment_terms_id") or None,
        data.get("tax_option"),
        data.get("subtotal"),
        data.get("discount_total"),
        data.get("tax_total"),
        data.get("grand_total"),
        data.get("terms_conditions"),
        data.get("remarks"),
        data.get("status") or "Draft",
    ]


def insert_items(cursor, quotation_id, items, timestamp):
    for row in items:
        cursor.execute(
            """
            INSERT INTO quotation_items (
                quotation_id, item_service_id, description, quantity, rate,
                discount_percent, discount_amount, tax_percent, tax_amount,
                line_total, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                quotation_id,
                row.get("item_service_id") or None,
                row.get("description"),
                row.get("quantity"),
                row.get("rate"),
                row.get("discount_percent"),
                row.get("discount_amount"),
                row.get("tax_percent"),
                row.get("tax_amount"),
                row.get("line_total"),
                timestamp,
                timestamp,
            ],
        )


def duplicate_quotation(request, quotation):
    company_id, branch_id = get_scope(request)
    items = get_quotation_items(quotation["id"])
    new_date = date.today()
    validity_days = int(quotation.get("validity_days") or 15)
    data = {
        **quotation,
        "quotation_no": generate_document_number(company_id, branch_id, "quotation"),
        "quotation_date": new_date.isoformat(),
        "valid_till": (new_date + timedelta(days=validity_days)).isoformat(),
        "status": "Draft",
        "customer_mode": "existing" if quotation.get("customer_id") else "new",
        "items": [
            {
                "item_service_id": item.get("item_service_id") or "",
                "description": item.get("description") or "",
                "quantity": item.get("quantity") or "0",
                "rate": item.get("rate") or "0",
                "discount_percent": item.get("discount_percent") or "0",
                "discount_amount": item.get("discount_amount") or "0",
                "tax_percent": item.get("tax_percent") or "0",
            }
            for item in items
        ],
    }
    errors, calculated = validate_and_calculate(data, company_id, branch_id)
    if errors:
        raise ValueError("Unable to duplicate quotation because the original quotation has invalid data.")
    new_id = save_quotation(company_id, branch_id, request.session.get("user_id"), calculated)
    log_user_activity(request, "CREATE", "Quotations", "quotations", new_id, f"Duplicated quotation {quotation['quotation_no']}.")
    return new_id


def customer_name_exists(company_id, branch_id, company_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM customers
            WHERE company_id = %s AND branch_id = %s AND lower(company_name) = lower(%s)
            LIMIT 1
            """,
            [company_id, branch_id, company_name],
        )
        return cursor.fetchone() is not None


def customer_email_exists(company_id, branch_id, email):
    if not email:
        return False
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id
            FROM customers
            WHERE company_id = %s AND branch_id = %s AND lower(email) = lower(%s)
            LIMIT 1
            """,
            [company_id, branch_id, email],
        )
        return cursor.fetchone() is not None


def add_quotation_party_as_customer(request, quotation):
    company_id, branch_id = get_scope(request)
    if quotation.get("customer_id") and int(quotation.get("is_customer_saved") or 0) == 1:
        raise ValueError("This quotation is already linked to a customer.")
    company_name = quotation.get("customer_name") or quotation.get("display_customer_name")
    if not company_name:
        raise ValueError("Quotation customer name is missing.")
    if customer_name_exists(company_id, branch_id, company_name):
        raise ValueError("Customer with this name already exists. Please edit quotation and select existing customer.")
    if customer_email_exists(company_id, branch_id, quotation.get("customer_email")):
        raise ValueError("A customer with this email already exists. Please edit quotation and select existing customer.")

    timestamp = now_text()
    user_id = request.session.get("user_id")
    with transaction.atomic():
        customer_code = generate_master_number(company_id, branch_id, "customer_prefix", "customers", "customer_code")
        account_id = create_linked_account(
            company_id,
            branch_id,
            f"AR-{customer_code}",
            company_name,
            "Assets",
            "Accounts Receivable",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO customers (
                    company_id, branch_id, customer_code, company_name, contact_person,
                    phone, mobile, email, address, ntn, strn, payment_terms_id,
                    credit_limit, opening_balance, opening_balance_type, account_id,
                    is_active, remarks, created_by_id, updated_by_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 'Debit', %s, 1, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    branch_id,
                    customer_code,
                    company_name,
                    quotation.get("contact_person"),
                    quotation.get("customer_phone"),
                    quotation.get("customer_mobile"),
                    quotation.get("customer_email"),
                    quotation.get("customer_address"),
                    quotation.get("customer_ntn"),
                    quotation.get("customer_strn"),
                    quotation.get("payment_terms_id"),
                    account_id,
                    f"Created from quotation {quotation['quotation_no']}.",
                    user_id,
                    user_id,
                    timestamp,
                    timestamp,
                ],
            )
            customer_id = cursor.lastrowid
            cursor.execute(
                """
                UPDATE quotations
                SET customer_id = %s, is_customer_saved = 1, updated_by_id = %s, updated_at = %s
                WHERE id = %s AND company_id = %s AND branch_id = %s
                """,
                [customer_id, user_id, timestamp, quotation["id"], company_id, branch_id],
            )
    log_user_activity(request, "CREATE", "Customers", "customers", customer_id, f"Created customer from quotation {quotation['quotation_no']}.")
    return customer_id


def cancel_quotation(request, quotation):
    if quotation.get("status") == "Converted":
        raise ValueError("Converted quotations cannot be cancelled.")
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE quotations
            SET status = 'Cancelled', updated_by_id = %s, updated_at = %s
            WHERE id = %s AND company_id = %s AND branch_id = %s
            """,
            [
                request.session.get("user_id"),
                timestamp,
                quotation["id"],
                request.session.get("company_id"),
                request.session.get("current_branch_id"),
            ],
        )
    log_user_activity(request, "CANCEL", "Quotations", "quotations", quotation["id"], f"Cancelled quotation {quotation['quotation_no']}.")


def mark_printed(request, quotation, action_label):
    if quotation.get("status") == "Draft":
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE quotations
                SET status = 'Printed', updated_by_id = %s, updated_at = %s
                WHERE id = %s
                """,
                [request.session.get("user_id"), timestamp, quotation["id"]],
            )
    log_user_activity(request, "PRINT", "Quotations", "quotations", quotation["id"], f"{action_label} quotation {quotation['quotation_no']}.")


def get_print_context(company_id, branch_id, quotation_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id = %s LIMIT 1", [company_id])
        company = dictfetchone(cursor) or {}
        cursor.execute("SELECT * FROM branches WHERE id = %s AND company_id = %s LIMIT 1", [branch_id, company_id])
        branch = dictfetchone(cursor) or {}
    quotation = get_quotation(company_id, branch_id, quotation_id)
    return {
        "company": company,
        "branch": branch,
        "company_settings": get_company_settings(company_id, branch_id) or {},
        "quotation": quotation,
        "items": get_quotation_items(quotation_id),
    }
