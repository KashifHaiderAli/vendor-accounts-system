from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from authentication.auth_utils import dictfetchall, dictfetchone
from core import validators
from core.inventory_utils import inventory_ready, post_delivery_challan_stock, reverse_stock_movements, validate_available_stock
from settings_module.services import get_numbering_settings, log_user_activity, now_text


PER_PAGE = 20
DC_STATUSES = ["Draft", "Printed", "Signed Received", "Invoiced", "Cancelled"]


def today_iso():
    return date.today().isoformat()


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


def generate_dc_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("delivery_challan_prefix") or "DC"
    padding = int(settings.get("number_padding") or 4)
    use_year = int(settings.get("use_year_in_number") or 0) == 1
    doc_prefix = f"{prefix}-{date.today().year}-" if use_year else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dc_no
            FROM delivery_challans
            WHERE company_id = %s AND branch_id = %s AND dc_no LIKE %s
            ORDER BY dc_no DESC
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


def list_challans(company_id, branch_id, search="", status="", date_from="", date_to="", page=1):
    clauses = ["dc.company_id = %s", "dc.branch_id = %s"]
    params = [company_id, branch_id]
    if search:
        like = f"%{search}%"
        clauses.append(
            """
            (dc.dc_no LIKE %s OR dc.po_number LIKE %s OR dc.delivered_by LIKE %s OR dc.received_by LIKE %s
             OR q.customer_name LIKE %s OR c.company_name LIKE %s)
            """
        )
        params.extend([like, like, like, like, like, like])
    if status:
        clauses.append("dc.status = %s")
        params.append(status)
    if date_from:
        clauses.append("dc.dc_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("dc.dc_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM delivery_challans dc
            LEFT JOIN customer_confirmations cc ON cc.id = dc.confirmation_id
            LEFT JOIN quotations q ON q.id = dc.quotation_id
            LEFT JOIN customers c ON c.id = dc.customer_id
            WHERE {where_sql}
            """,
            params,
        )
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT dc.*, cc.confirmation_no, q.quotation_no,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM delivery_challans dc
            LEFT JOIN customer_confirmations cc ON cc.id = dc.confirmation_id
            LEFT JOIN quotations q ON q.id = dc.quotation_id
            LEFT JOIN customers c ON c.id = dc.customer_id
            WHERE {where_sql}
            ORDER BY dc.dc_date DESC, dc.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, customer_code, company_name, contact_person, phone, mobile, email, address
            FROM customers
            WHERE company_id = %s AND branch_id = %s AND is_active = 1
            ORDER BY company_name
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


def get_items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, warranty_or_service_description
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


def get_quotation(company_id, branch_id, quotation_id):
    if not quotation_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT q.*, c.company_name AS master_customer_name, c.address AS master_customer_address,
                   c.phone AS master_customer_phone, c.mobile AS master_customer_mobile, c.email AS master_customer_email
            FROM quotations q
            LEFT JOIN customers c ON c.id = q.customer_id
            WHERE q.id = %s AND q.company_id = %s AND q.branch_id = %s AND q.status <> 'Cancelled'
            LIMIT 1
            """,
            [quotation_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["party_name"] = row.get("customer_name") or row.get("master_customer_name") or "Unregistered Party"
        row["party_address"] = row.get("customer_address") or row.get("master_customer_address") or ""
        row["party_phone"] = row.get("customer_phone") or row.get("master_customer_phone") or ""
    return row


def get_confirmation(company_id, branch_id, confirmation_id):
    if not confirmation_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.*, q.quotation_no, q.customer_name AS quotation_customer_name,
                   q.customer_address AS quotation_customer_address, q.customer_phone AS quotation_customer_phone,
                   c.company_name AS customer_name, c.address AS customer_address, c.phone AS customer_phone
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.id = %s AND cc.company_id = %s AND cc.branch_id = %s AND cc.status <> 'Cancelled'
            LIMIT 1
            """,
            [confirmation_id, company_id, branch_id],
        )
        row = dictfetchone(cursor)
    if row:
        row["party_name"] = row.get("quotation_customer_name") or row.get("customer_name") or "Unregistered Party"
        row["party_address"] = row.get("quotation_customer_address") or row.get("customer_address") or ""
        row["party_phone"] = row.get("quotation_customer_phone") or row.get("customer_phone") or ""
    return row


def get_confirmations(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cc.id, cc.confirmation_no, cc.quotation_id, cc.customer_id, cc.po_number,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name
            FROM customer_confirmations cc
            LEFT JOIN quotations q ON q.id = cc.quotation_id
            LEFT JOIN customers c ON c.id = cc.customer_id
            WHERE cc.company_id = %s AND cc.branch_id = %s AND cc.status <> 'Cancelled'
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
            WHERE q.company_id = %s AND q.branch_id = %s AND q.status <> 'Cancelled'
            ORDER BY q.quotation_date DESC, q.id DESC
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


def get_quotation_items(quotation_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT item_service_id, description, quantity
            FROM quotation_items
            WHERE quotation_id = %s
            ORDER BY id
            """,
            [quotation_id],
        )
        return dictfetchall(cursor)


def default_form_data(company_id, branch_id, quotation=None, confirmation=None):
    source_quotation = quotation
    if confirmation and confirmation.get("quotation_id") and not source_quotation:
        source_quotation = get_quotation(company_id, branch_id, confirmation["quotation_id"])
    items = items_from_quotation(source_quotation["id"]) if source_quotation else [empty_item_row()]
    return {
        "dc_no": generate_dc_no(company_id, branch_id),
        "dc_date": today_iso(),
        "customer_id": (confirmation or source_quotation or {}).get("customer_id") or "",
        "confirmation_id": confirmation.get("id") if confirmation else "",
        "quotation_id": source_quotation.get("id") if source_quotation else "",
        "po_number": confirmation.get("po_number") if confirmation else "",
        "delivered_by": "",
        "received_by": "",
        "signed_copy_path": "",
        "status": "Draft",
        "remarks": "",
        "items": items or [empty_item_row()],
    }


def items_from_quotation(quotation_id):
    return [
        {
            "item_service_id": row.get("item_service_id") or "",
            "description": row.get("description") or "",
            "quantity": row.get("quantity") or "0",
            "errors": {},
        }
        for row in get_quotation_items(quotation_id)
    ]


def empty_item_row():
    return {"item_service_id": "", "description": "", "quantity": "1.00", "errors": {}}


def parse_post(post):
    rows = []
    item_ids = post.getlist("item_service_id[]")
    descriptions = post.getlist("description[]")
    quantities = post.getlist("quantity[]")
    for index, description in enumerate(descriptions):
        rows.append(
            {
                "item_service_id": item_ids[index] if index < len(item_ids) else "",
                "description": description,
                "quantity": quantities[index] if index < len(quantities) else "",
            }
        )
    return {
        "dc_no": post.get("dc_no", ""),
        "dc_date": post.get("dc_date", ""),
        "customer_id": post.get("customer_id", ""),
        "confirmation_id": post.get("confirmation_id", ""),
        "quotation_id": post.get("quotation_id", ""),
        "po_number": post.get("po_number", ""),
        "delivered_by": post.get("delivered_by", ""),
        "received_by": post.get("received_by", ""),
        "signed_copy_path": post.get("signed_copy_path", ""),
        "status": post.get("status", "Draft"),
        "remarks": post.get("remarks", ""),
        "items": rows,
    }


def dc_no_exists(company_id, branch_id, dc_no, exclude_id=None):
    params = [company_id, branch_id, dc_no]
    clause = "company_id = %s AND branch_id = %s AND lower(dc_no) = lower(%s)"
    if exclude_id:
        clause += " AND id <> %s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM delivery_challans WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_and_clean(data, company_id, branch_id, challan_id=None, signed_only=False):
    errors = {}
    cleaned = {}
    if signed_only:
        cleaned["signed_copy_path"], errors["signed_copy_path"] = validators.clean_text(
            data.get("signed_copy_path"),
            max_length=500,
            field_name="Signed Copy Path",
        )
        cleaned["received_by"], errors["received_by"] = validators.clean_text(data.get("received_by"), max_length=150, field_name="Received By")
        cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
        return {k: v for k, v in errors.items() if v}, {**data, **cleaned}

    cleaned["dc_no"], errors["dc_no"] = validators.clean_text(data.get("dc_no"), max_length=50, required=True, field_name="DC No")
    if not errors["dc_no"] and dc_no_exists(company_id, branch_id, cleaned["dc_no"], challan_id):
        errors["dc_no"] = "DC No already exists for the current branch."
    dc_date, errors["dc_date"] = validators.validate_date(data.get("dc_date"), "DC Date", required=True)
    cleaned["dc_date"] = dc_date.isoformat() if dc_date else ""

    confirmation = get_confirmation(company_id, branch_id, data.get("confirmation_id"))
    quotation = get_quotation(company_id, branch_id, data.get("quotation_id"))
    if data.get("confirmation_id") and not confirmation:
        errors["confirmation_id"] = "Selected confirmation was not found."
    if data.get("quotation_id") and not quotation:
        errors["quotation_id"] = "Selected quotation was not found."

    customer_id = data.get("customer_id") or ""
    if confirmation and not customer_id:
        customer_id = confirmation.get("customer_id") or ""
    if quotation and not customer_id:
        customer_id = quotation.get("customer_id") or ""
    if not confirmation and not quotation and not customer_id:
        errors["customer_id"] = "Customer is required for direct delivery challan."
    if customer_id and not customer_exists(company_id, branch_id, customer_id):
        errors["customer_id"] = "Selected customer was not found."

    cleaned["customer_id"] = customer_id or None
    cleaned["confirmation_id"] = confirmation.get("id") if confirmation else (data.get("confirmation_id") or None)
    cleaned["quotation_id"] = quotation.get("id") if quotation else (data.get("quotation_id") or None)
    cleaned["po_number"], errors["po_number"] = validators.clean_text(data.get("po_number"), max_length=100, field_name="PO Number")
    cleaned["delivered_by"], errors["delivered_by"] = validators.clean_text(data.get("delivered_by"), max_length=150, field_name="Delivered By")
    cleaned["received_by"], errors["received_by"] = validators.clean_text(data.get("received_by"), max_length=150, field_name="Received By")
    cleaned["signed_copy_path"], errors["signed_copy_path"] = validators.clean_text(data.get("signed_copy_path"), max_length=500, field_name="Signed Copy Path")
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
    status = data.get("status") or "Draft"
    errors["status"] = validators.validate_choice(status, DC_STATUSES, "Status")
    cleaned["status"] = status
    rows, item_error = validate_items(data.get("items") or [], company_id, branch_id)
    cleaned["items"] = rows
    if item_error:
        errors["items"] = item_error
    return {k: v for k, v in errors.items() if v}, {**data, **cleaned}


def validate_items(items, company_id, branch_id):
    rows = []
    has_error = False
    for raw in items:
        if not any(str(raw.get(key) or "").strip() for key in ["item_service_id", "description", "quantity"]):
            continue
        errors = {}
        item_id = raw.get("item_service_id") or ""
        if item_id and not item_exists(company_id, branch_id, item_id):
            errors["item_service_id"] = "Selected item/service was not found."
        description, errors["description"] = validators.clean_text(raw.get("description"), required=True, field_name="Description")
        quantity, errors["quantity"] = validators.validate_decimal(raw.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        quantity = quantity or Decimal("0")
        if item_id and not errors:
            try:
                validate_available_stock(company_id, branch_id, item_id, quantity, "Delivery Challan")
            except ValueError as exc:
                errors["quantity"] = str(exc)
        errors = {key: value for key, value in errors.items() if value}
        if errors:
            has_error = True
        rows.append(
            {
                "item_service_id": item_id,
                "description": description,
                "quantity": str(quantity.quantize(Decimal("0.01"))),
                "errors": errors,
            }
        )
    if not rows:
        return [empty_item_row()], "At least one delivery item is required."
    return rows, "Please correct item row errors." if has_error else None


def get_challan(company_id, branch_id, challan_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dc.*, cc.confirmation_no, q.quotation_no,
                   COALESCE(NULLIF(q.customer_name, ''), c.company_name) AS party_name,
                   COALESCE(NULLIF(q.customer_address, ''), c.address) AS party_address,
                   COALESCE(NULLIF(q.customer_phone, ''), c.phone) AS party_phone,
                   cb.full_name AS created_by_name, ub.full_name AS updated_by_name
            FROM delivery_challans dc
            LEFT JOIN customer_confirmations cc ON cc.id = dc.confirmation_id
            LEFT JOIN quotations q ON q.id = dc.quotation_id
            LEFT JOIN customers c ON c.id = dc.customer_id
            LEFT JOIN users cb ON cb.id = dc.created_by_id
            LEFT JOIN users ub ON ub.id = dc.updated_by_id
            WHERE dc.id = %s AND dc.company_id = %s AND dc.branch_id = %s
            LIMIT 1
            """,
            [challan_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def get_challan_items(challan_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dci.*, i.item_code, i.item_name
            FROM delivery_challan_items dci
            LEFT JOIN item_services i ON i.id = dci.item_service_id
            WHERE dci.delivery_challan_id = %s
            ORDER BY dci.id
            """,
            [challan_id],
        )
        return dictfetchall(cursor)


def save_challan(company_id, branch_id, user_id, data, challan_id=None, signed_only=False):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if signed_only:
                cursor.execute(
                    """
                    UPDATE delivery_challans
                    SET signed_copy_path = %s, received_by = %s, remarks = %s,
                        status = 'Signed Received', updated_by_id = %s, updated_at = %s
                    WHERE id = %s AND company_id = %s AND branch_id = %s
                    """,
                    [data.get("signed_copy_path"), data.get("received_by"), data.get("remarks"), user_id, timestamp, challan_id, company_id, branch_id],
                )
                return challan_id
            if challan_id:
                if inventory_ready():
                    cursor.execute("SELECT id FROM stock_movements WHERE source_type='delivery_challan' AND source_id=%s LIMIT 1", [challan_id])
                    if cursor.fetchone():
                        raise ValueError("Stock-posted delivery challan item details cannot be edited. Cancel and recreate if stock quantities must change.")
                cursor.execute(
                    """
                    UPDATE delivery_challans
                    SET dc_no = %s, dc_date = %s, customer_id = %s, confirmation_id = %s,
                        quotation_id = %s, po_number = %s, delivered_by = %s, received_by = %s,
                        signed_copy_path = %s, status = %s, remarks = %s, updated_by_id = %s, updated_at = %s
                    WHERE id = %s AND company_id = %s AND branch_id = %s
                    """,
                    header_values(data) + [user_id, timestamp, challan_id, company_id, branch_id],
                )
                cursor.execute("DELETE FROM delivery_challan_items WHERE delivery_challan_id = %s", [challan_id])
                saved_id = challan_id
            else:
                cursor.execute(
                    """
                    INSERT INTO delivery_challans (
                        company_id, branch_id, dc_no, dc_date, customer_id, confirmation_id,
                        quotation_id, po_number, delivered_by, received_by, signed_copy_path,
                        status, remarks, created_by_id, updated_by_id, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [company_id, branch_id] + header_values(data) + [user_id, user_id, timestamp, timestamp],
                )
                saved_id = cursor.lastrowid
            insert_items(cursor, saved_id, data["items"], timestamp)
            post_delivery_challan_stock(company_id, branch_id, saved_id, user_id)
    return saved_id


def header_values(data):
    return [
        data.get("dc_no"),
        data.get("dc_date"),
        data.get("customer_id") or None,
        data.get("confirmation_id") or None,
        data.get("quotation_id") or None,
        data.get("po_number"),
        data.get("delivered_by"),
        data.get("received_by"),
        data.get("signed_copy_path"),
        data.get("status") or "Draft",
        data.get("remarks"),
    ]


def insert_items(cursor, challan_id, items, timestamp):
    for row in items:
        cursor.execute(
            """
            INSERT INTO delivery_challan_items (
                delivery_challan_id, item_service_id, description, quantity, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [challan_id, row.get("item_service_id") or None, row.get("description"), row.get("quantity"), timestamp, timestamp],
        )


def cancel_challan(request, challan):
    if challan.get("status") == "Invoiced":
        raise ValueError("Invoiced delivery challans cannot be cancelled.")
    if challan.get("status") == "Cancelled":
        raise ValueError("This delivery challan is already cancelled.")
    timestamp = now_text()
    company_id, branch_id = get_scope(request)
    with transaction.atomic():
        reverse_stock_movements("delivery_challan", challan["id"], f"Cancel delivery challan {challan['dc_no']}", request.session.get("user_id"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE delivery_challans
                SET status = 'Cancelled', updated_by_id = %s, updated_at = %s
                WHERE id = %s AND company_id = %s AND branch_id = %s
                """,
                [request.session.get("user_id"), timestamp, challan["id"], company_id, branch_id],
            )
    log_user_activity(request, "CANCEL", "Delivery Challans", "delivery_challans", challan["id"], f"Cancelled delivery challan {challan['dc_no']}.")


def mark_printed(request, challan):
    if challan.get("status") == "Draft":
        timestamp = now_text()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE delivery_challans SET status = 'Printed', updated_by_id = %s, updated_at = %s WHERE id = %s",
                [request.session.get("user_id"), timestamp, challan["id"]],
            )
    log_user_activity(request, "PRINT", "Delivery Challans", "delivery_challans", challan["id"], f"Printed delivery challan {challan['dc_no']}.")


def get_print_context(company_id, branch_id, challan_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id = %s LIMIT 1", [company_id])
        company = dictfetchone(cursor) or {}
        cursor.execute("SELECT * FROM branches WHERE id = %s AND company_id = %s LIMIT 1", [branch_id, company_id])
        branch = dictfetchone(cursor) or {}
    return {
        "company": company,
        "branch": branch,
        "challan": get_challan(company_id, branch_id, challan_id),
        "items": get_challan_items(challan_id),
        "print_date": today_iso(),
    }
