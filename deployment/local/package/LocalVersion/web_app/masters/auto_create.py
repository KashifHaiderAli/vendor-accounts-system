from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import connection

from masters.master_utils import create_linked_account
from settings_module.services import get_numbering_settings, now_text


def normalized(value):
    return " ".join(str(value or "").strip().split()).lower()


def display_name(value):
    return " ".join(str(value or "").strip().split())


def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def generate_master_number(company_id, branch_id, prefix_field, table_name, code_field):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get(prefix_field) or "AUTO"
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
    with connection.cursor() as cursor:
        while True:
            candidate = f"{doc_prefix}{next_number:0{padding}d}"
            cursor.execute(
                f"""
                SELECT id
                FROM {table_name}
                WHERE company_id = %s AND branch_id = %s AND {code_field} = %s
                LIMIT 1
                """,
                [company_id, branch_id, candidate],
            )
            if not cursor.fetchone():
                return candidate
            next_number += 1


def find_customer_by_name(company_id, branch_id, name):
    clean = normalized(name)
    if not clean:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, customer_code, company_name, contact_person, phone, mobile, email,
                   address, ntn, strn, payment_terms_id, account_id
            FROM customers
            WHERE company_id = %s AND branch_id = %s
              AND lower(trim(company_name)) = %s
            LIMIT 1
            """,
            [company_id, branch_id, clean],
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def find_supplier_by_name(company_id, branch_id, name):
    clean = normalized(name)
    if not clean:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, supplier_code, supplier_name, contact_person, phone, mobile, email,
                   address, ntn, strn, account_id
            FROM suppliers
            WHERE company_id = %s AND branch_id = %s
              AND lower(trim(supplier_name)) = %s
            LIMIT 1
            """,
            [company_id, branch_id, clean],
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def find_item_by_name(company_id, branch_id, name):
    clean = normalized(name)
    if not clean:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, default_purchase_rate, default_sale_rate, default_tax_rate
            FROM item_services
            WHERE company_id = %s AND branch_id = %s
              AND lower(trim(item_name)) = %s
            LIMIT 1
            """,
            [company_id, branch_id, clean],
        )
        columns = [col[0] for col in cursor.description]
        row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def create_customer(company_id, branch_id, user_id, name, source_label, extra=None):
    extra = extra or {}
    company_name = display_name(name)
    customer_code = generate_master_number(company_id, branch_id, "customer_prefix", "customers", "customer_code")
    account_id = create_linked_account(company_id, branch_id, f"AR-{customer_code}", company_name, "Assets", "Accounts Receivable")
    timestamp = now_text()
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
                extra.get("contact_person") or "",
                extra.get("phone") or "",
                extra.get("mobile") or "",
                extra.get("email") or "",
                extra.get("address") or "",
                extra.get("ntn") or "",
                extra.get("strn") or "",
                extra.get("payment_terms_id") or None,
                account_id,
                f"Auto-created from {source_label}.",
                user_id,
                user_id,
                timestamp,
                timestamp,
            ],
        )
        customer_id = cursor.lastrowid
    return {"id": customer_id, "customer_code": customer_code, "company_name": company_name, "account_id": account_id}


def create_supplier(company_id, branch_id, user_id, name, source_label):
    supplier_name = display_name(name)
    supplier_code = generate_master_number(company_id, branch_id, "supplier_prefix", "suppliers", "supplier_code")
    account_id = create_linked_account(company_id, branch_id, f"AP-{supplier_code}", supplier_name, "Liabilities", "Accounts Payable")
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO suppliers (
                company_id, branch_id, supplier_code, supplier_name, contact_person,
                phone, mobile, email, address, ntn, strn, opening_balance,
                opening_balance_type, account_id, is_active, remarks,
                created_by_id, updated_by_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, '', '', '', '', '', '', '', 0, 'Credit', %s, 1, %s, %s, %s, %s, %s)
            """,
            [
                company_id,
                branch_id,
                supplier_code,
                supplier_name,
                account_id,
                f"Auto-created from {source_label}.",
                user_id,
                user_id,
                timestamp,
                timestamp,
            ],
        )
        supplier_id = cursor.lastrowid
    return {"id": supplier_id, "supplier_code": supplier_code, "supplier_name": supplier_name, "account_id": account_id}


def create_item(company_id, branch_id, user_id, name, source_label, sale_rate=None, purchase_rate=None):
    item_name = display_name(name)[:200]
    item_code = generate_master_number(company_id, branch_id, "item_prefix", "item_services", "item_code")
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO item_services (
                company_id, branch_id, item_code, item_name, item_type, category,
                default_purchase_rate, default_sale_rate, default_tax_rate,
                warranty_or_service_description, is_active, remarks,
                created_by_id, updated_by_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 'Product', '', %s, %s, 0, '', 1, %s, %s, %s, %s, %s)
            """,
            [
                company_id,
                branch_id,
                item_code,
                item_name,
                str(money(purchase_rate)),
                str(money(sale_rate)),
                f"Auto-created from {source_label}.",
                user_id,
                user_id,
                timestamp,
                timestamp,
            ],
        )
        item_id = cursor.lastrowid
    return {"id": item_id, "item_code": item_code, "item_name": item_name}


def resolve_sales_customer_and_items(data, company_id, branch_id, user_id, post, source_label):
    errors = {}
    created = []
    customer_confirmed = post.get("auto_create_customer_confirmed") == "1"
    items_confirmed = post.get("auto_create_items_confirmed") == "1"

    customer_name = data.get("customer_name") or ""
    customer_name_allowed = "customer_mode" not in data or data.get("customer_mode") == "new"
    if not data.get("customer_id") and customer_name and customer_name_allowed:
        existing = find_customer_by_name(company_id, branch_id, customer_name)
        if existing:
            data["customer_id"] = existing["id"]
            data["customer_mode"] = "existing"
        elif customer_confirmed:
            customer = create_customer(
                company_id,
                branch_id,
                user_id,
                customer_name,
                source_label,
                {
                    "contact_person": data.get("contact_person"),
                    "phone": data.get("customer_phone"),
                    "mobile": data.get("customer_mobile"),
                    "email": data.get("customer_email"),
                    "address": data.get("customer_address"),
                    "ntn": data.get("customer_ntn"),
                    "strn": data.get("customer_strn"),
                    "payment_terms_id": data.get("payment_terms_id"),
                },
            )
            data["customer_id"] = customer["id"]
            data["customer_mode"] = "existing"
            created.append({"type": "customer", "id": customer["id"], "name": customer["company_name"]})
        else:
            errors["customer_id"] = "Customer is not selected from Customer Master. Please select an existing customer or confirm to add a new customer."

    item_cache = {}
    missing_items = False
    for row in data.get("items") or []:
        if row.get("item_service_id"):
            continue
        item_name = display_name(row.get("description"))
        if not item_name:
            continue
        key = normalized(item_name)
        item = item_cache.get(key) or find_item_by_name(company_id, branch_id, item_name)
        if not item and items_confirmed:
            item = create_item(company_id, branch_id, user_id, item_name, source_label, sale_rate=row.get("rate"))
            created.append({"type": "item", "id": item["id"], "name": item["item_name"]})
        if item:
            item_cache[key] = item
            row["item_service_id"] = item["id"]
        else:
            missing_items = True
            row.setdefault("errors", {})["item_service_id"] = "Confirm auto-create or select an item from Item Master."
    if missing_items:
        errors["items"] = "Some items are not selected from Item Master. Please select existing items or confirm to add them as new items."
    return errors, data, created


def resolve_sales_customer_only(data, company_id, branch_id, user_id, post, source_label):
    errors = {}
    created = []
    customer_confirmed = post.get("auto_create_customer_confirmed") == "1"
    customer_name = data.get("customer_name") or ""
    customer_name_allowed = "customer_mode" not in data or data.get("customer_mode") == "new"
    if not data.get("customer_id") and customer_name and customer_name_allowed:
        existing = find_customer_by_name(company_id, branch_id, customer_name)
        if existing:
            data["customer_id"] = existing["id"]
            data["customer_mode"] = "existing"
        elif customer_confirmed:
            customer = create_customer(company_id, branch_id, user_id, customer_name, source_label)
            data["customer_id"] = customer["id"]
            data["customer_mode"] = "existing"
            created.append({"type": "customer", "id": customer["id"], "name": customer["company_name"]})
        else:
            errors["customer_id"] = "Customer is not selected from Customer Master. Please select an existing customer or confirm to add a new customer."
    return errors, data, created


def resolve_purchase_supplier_and_items(data, company_id, branch_id, user_id, post, source_label):
    errors = {}
    created = []
    supplier_confirmed = post.get("auto_create_supplier_confirmed") == "1"
    items_confirmed = post.get("auto_create_items_confirmed") == "1"

    supplier_name = data.get("supplier_name") or ""
    if not data.get("supplier_id") and supplier_name:
        existing = find_supplier_by_name(company_id, branch_id, supplier_name)
        if existing:
            data["supplier_id"] = existing["id"]
        elif supplier_confirmed:
            supplier = create_supplier(company_id, branch_id, user_id, supplier_name, source_label)
            data["supplier_id"] = supplier["id"]
            created.append({"type": "supplier", "id": supplier["id"], "name": supplier["supplier_name"]})
        else:
            errors["supplier_id"] = "Supplier is not selected from Supplier Master. Please select an existing supplier or confirm to add a new supplier."

    item_cache = {}
    missing_items = False
    for row in data.get("items") or []:
        if row.get("item_service_id"):
            continue
        item_name = display_name(row.get("description"))
        if not item_name:
            continue
        key = normalized(item_name)
        item = item_cache.get(key) or find_item_by_name(company_id, branch_id, item_name)
        if not item and items_confirmed:
            item = create_item(company_id, branch_id, user_id, item_name, source_label, purchase_rate=row.get("purchase_rate"))
            created.append({"type": "item", "id": item["id"], "name": item["item_name"]})
        if item:
            item_cache[key] = item
            row["item_service_id"] = item["id"]
        else:
            missing_items = True
            row.setdefault("errors", {})["item_service_id"] = "Confirm auto-create or select an item from Item Master."
    if missing_items:
        errors["items"] = "Some purchase items are not selected from Item Master. Please select existing items or confirm to add them as new items."
    return errors, data, created
