from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from authentication.auth_utils import dictfetchall, dictfetchone
from core.system_settings import get_setting, set_setting
from settings_module.services import now_text


class InventoryError(ValueError):
    pass


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def table_exists(table_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [table_name])
        return cursor.fetchone() is not None


def column_exists(table_name, column_name):
    if not table_exists(table_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor.fetchall())


def is_inventory_enabled(company_id=None):
    return str(get_setting("enable_inventory_tracking", "1")).lower() not in {"0", "false", "no", "off"}


def set_inventory_enabled(enabled):
    set_setting("enable_inventory_tracking", "1" if enabled else "0")


def stock_reduce_on():
    value = get_setting("stock_reduce_on", "delivery_challan")
    return value if value in {"delivery_challan", "sales_invoice"} else "delivery_challan"


def set_stock_reduce_on(value):
    set_setting("stock_reduce_on", value if value in {"delivery_challan", "sales_invoice"} else "delivery_challan")


def inventory_ready():
    return table_exists("stock_movements")


def item_row(item_id):
    if not item_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM item_services WHERE id=%s LIMIT 1", [item_id])
        return dictfetchone(cursor)


def item_tracks_inventory(item_id):
    item = item_row(item_id)
    if not item:
        return False
    item_type = str(item.get("item_type") or "").lower()
    if item_type == "service":
        return False
    if column_exists("item_services", "track_inventory"):
        return int(item.get("track_inventory") if item.get("track_inventory") is not None else 1) == 1
    return True


def get_available_stock(company_id, branch_id, item_id, as_of_date=None):
    if not inventory_ready():
        return Decimal("0.00")
    params = [company_id, branch_id, item_id]
    clauses = ["company_id=%s", "branch_id=%s", "item_service_id=%s"]
    if as_of_date:
        clauses.append("movement_date <= %s")
        params.append(as_of_date)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COALESCE(SUM(quantity_in - quantity_out),0) FROM stock_movements WHERE {' AND '.join(clauses)}",
            params,
        )
        return money(cursor.fetchone()[0])


def average_cost(company_id, branch_id, item_id):
    if not inventory_ready():
        return Decimal("0.00")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(SUM(quantity_in * unit_cost),0), COALESCE(SUM(quantity_in),0)
            FROM stock_movements
            WHERE company_id=%s AND branch_id=%s AND item_service_id=%s AND quantity_in > 0
            """,
            [company_id, branch_id, item_id],
        )
        total_cost, total_qty = cursor.fetchone()
    total_qty = money(total_qty)
    if total_qty <= 0:
        item = item_row(item_id) or {}
        return money(item.get("opening_cost") or item.get("default_purchase_rate") or 0)
    return (money(total_cost) / total_qty).quantize(Decimal("0.01"))


def movement_exists(source_type, source_id, item_id, movement_type, quantity_in, quantity_out):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id FROM stock_movements
            WHERE source_type=%s AND source_id=%s AND item_service_id=%s AND movement_type=%s
              AND quantity_in=%s AND quantity_out=%s
            LIMIT 1
            """,
            [source_type, source_id, item_id, movement_type, str(money(quantity_in)), str(money(quantity_out))],
        )
        return cursor.fetchone() is not None


def create_stock_movement(company_id, branch_id, item_service_id, movement_date, movement_type, source_type, source_id=None, source_no="", quantity_in=0, quantity_out=0, unit_cost=0, remarks="", created_by_id=None):
    if not is_inventory_enabled(company_id) or not inventory_ready() or not item_tracks_inventory(item_service_id):
        return None
    qty_in = money(quantity_in)
    qty_out = money(quantity_out)
    if qty_in < 0 or qty_out < 0:
        raise InventoryError("Stock movement quantity cannot be negative.")
    if (qty_in > 0 and qty_out > 0) or (qty_in <= 0 and qty_out <= 0):
        raise InventoryError("Stock movement must have either quantity in or quantity out.")
    if qty_out > 0:
        validate_available_stock(company_id, branch_id, item_service_id, qty_out, source_no or source_type)
    if source_id and movement_exists(source_type, source_id, item_service_id, movement_type, qty_in, qty_out):
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stock_movements (
                company_id, branch_id, item_service_id, movement_date, movement_type, source_type, source_id,
                source_no, quantity_in, quantity_out, unit_cost, remarks, created_by_id, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [company_id, branch_id, item_service_id, movement_date, movement_type, source_type, source_id, source_no, str(qty_in), str(qty_out), str(money(unit_cost)), remarks, created_by_id, now_text()],
        )
        return cursor.lastrowid


def validate_available_stock(company_id, branch_id, item_id, required_qty, source_context=""):
    if not is_inventory_enabled(company_id) or not inventory_ready():
        return True
    if not item_tracks_inventory(item_id):
        return True
    available = get_available_stock(company_id, branch_id, item_id)
    required = money(required_qty)
    if required > available:
        item = item_row(item_id) or {}
        name = item.get("item_name") or f"Item {item_id}"
        raise InventoryError(f"Insufficient stock for {name}. Available: {available}, Required: {required}.")
    return True


def reverse_stock_movements(source_type, source_id, reason, created_by_id=None):
    if not inventory_ready():
        return 0
    reverse_source_type = f"{source_type}_cancel"
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM stock_movements WHERE source_type=%s AND source_id=%s LIMIT 1", [reverse_source_type, source_id])
        if cursor.fetchone():
            return 0
        cursor.execute("SELECT * FROM stock_movements WHERE source_type=%s AND source_id=%s ORDER BY id", [source_type, source_id])
        movements = dictfetchall(cursor)
    created = 0
    for movement in movements:
        create_stock_movement(
            movement["company_id"],
            movement["branch_id"],
            movement["item_service_id"],
            date.today().isoformat(),
            "cancellation_reverse",
            reverse_source_type,
            source_id,
            movement.get("source_no") or "",
            quantity_in=movement.get("quantity_out") or 0,
            quantity_out=movement.get("quantity_in") or 0,
            unit_cost=movement.get("unit_cost") or 0,
            remarks=reason,
            created_by_id=created_by_id,
        )
        created += 1
    return created


def ensure_opening_stock_movements(company_id, branch_id, user_id=None):
    if not inventory_ready():
        return 0
    if not column_exists("item_services", "opening_stock"):
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM item_services
            WHERE company_id=%s AND branch_id=%s AND COALESCE(opening_stock,0) > 0
            """,
            [company_id, branch_id],
        )
        items = dictfetchall(cursor)
    count = 0
    for item in items:
        if not item_tracks_inventory(item["id"]):
            continue
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM stock_movements WHERE source_type='opening_stock' AND source_id=%s LIMIT 1", [item["id"]])
            if cursor.fetchone():
                continue
        create_stock_movement(company_id, branch_id, item["id"], date.today().isoformat(), "opening_stock_in", "opening_stock", item["id"], item.get("item_code") or "", item.get("opening_stock") or 0, 0, item.get("opening_cost") or item.get("default_purchase_rate") or 0, "Opening stock", user_id)
        count += 1
    return count


def post_supplier_purchase_stock(company_id, branch_id, purchase_id, user_id=None):
    if not inventory_ready():
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM supplier_purchases WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [purchase_id, company_id, branch_id])
        purchase = dictfetchone(cursor)
        cursor.execute("SELECT * FROM supplier_purchase_items WHERE supplier_purchase_id=%s ORDER BY id", [purchase_id])
        items = dictfetchall(cursor)
    if not purchase:
        return 0
    count = 0
    for item in items:
        if item.get("item_service_id"):
            create_stock_movement(company_id, branch_id, item["item_service_id"], purchase["purchase_date"], "purchase_in", "supplier_purchase", purchase_id, purchase["purchase_no"], item.get("quantity") or 0, 0, item.get("purchase_rate") or 0, "Supplier purchase stock in", user_id)
            count += 1
    return count


def post_delivery_challan_stock(company_id, branch_id, challan_id, user_id=None):
    if not inventory_ready():
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM delivery_challans WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [challan_id, company_id, branch_id])
        challan = dictfetchone(cursor)
        cursor.execute("SELECT * FROM delivery_challan_items WHERE delivery_challan_id=%s ORDER BY id", [challan_id])
        items = dictfetchall(cursor)
    if not challan:
        return 0
    count = 0
    for item in items:
        if item.get("item_service_id"):
            cost = average_cost(company_id, branch_id, item["item_service_id"])
            create_stock_movement(company_id, branch_id, item["item_service_id"], challan["dc_date"], "delivery_out", "delivery_challan", challan_id, challan["dc_no"], 0, item.get("quantity") or 0, cost, "Delivery challan stock out", user_id)
            count += 1
    return count


def post_sales_invoice_stock(company_id, branch_id, invoice_id, user_id=None):
    if not inventory_ready():
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_invoices WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [invoice_id, company_id, branch_id])
        invoice = dictfetchone(cursor)
        cursor.execute("SELECT * FROM sales_invoice_items WHERE sales_invoice_id=%s ORDER BY id", [invoice_id])
        items = dictfetchall(cursor)
    if not invoice or invoice.get("delivery_challan_id"):
        return 0
    count = 0
    for item in items:
        if item.get("item_service_id"):
            cost = average_cost(company_id, branch_id, item["item_service_id"])
            create_stock_movement(company_id, branch_id, item["item_service_id"], invoice["invoice_date"], "invoice_out", "sales_invoice", invoice_id, invoice["invoice_no"], 0, item.get("quantity") or 0, cost, "Direct invoice stock out", user_id)
            count += 1
    return count


def post_sales_return_stock(company_id, branch_id, return_id, user_id=None):
    if not inventory_ready():
        return 0
    action_column = column_exists("sales_returns", "return_stock_action")
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sales_returns WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [return_id, company_id, branch_id])
        sales_return = dictfetchone(cursor)
        cursor.execute("SELECT * FROM sales_return_items WHERE sales_return_id=%s ORDER BY id", [return_id])
        items = dictfetchall(cursor)
    if not sales_return:
        return 0
    action = sales_return.get("return_stock_action") if action_column else "Return to Stock"
    if action not in {"Return to Stock", "", None}:
        return 0
    count = 0
    for item in items:
        if item.get("item_service_id"):
            create_stock_movement(company_id, branch_id, item["item_service_id"], sales_return["return_date"], "sales_return_in", "sales_return", return_id, sales_return["sales_return_no"], item.get("quantity") or 0, 0, item.get("rate") or 0, "Sales return stock in", user_id)
            count += 1
    return count


def post_purchase_return_stock(company_id, branch_id, return_id, user_id=None):
    if not inventory_ready():
        return 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM purchase_returns WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [return_id, company_id, branch_id])
        purchase_return = dictfetchone(cursor)
        cursor.execute("SELECT * FROM purchase_return_items WHERE purchase_return_id=%s ORDER BY id", [return_id])
        items = dictfetchall(cursor)
    if not purchase_return:
        return 0
    count = 0
    for item in items:
        if item.get("item_service_id"):
            create_stock_movement(company_id, branch_id, item["item_service_id"], purchase_return["return_date"], "purchase_return_out", "purchase_return", return_id, purchase_return["purchase_return_no"], 0, item.get("quantity") or 0, item.get("purchase_rate") or 0, "Purchase return stock out", user_id)
            count += 1
    return count


def get_stock_balance(company_id, branch_id, filters=None):
    filters = filters or {}
    if not inventory_ready():
        return []
    date_clause = ""
    join_params = [company_id, branch_id]
    if filters.get("date_as_of"):
        date_clause = "AND sm.movement_date <= %s"
        join_params.append(filters["date_as_of"])
    item_filter = ""
    where_params = [company_id, branch_id]
    if filters.get("item_service_id"):
        item_filter = "AND i.id=%s"
        where_params.append(filters["item_service_id"])
    rows = []
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT i.id, i.item_code, i.item_name, i.item_type,
                   COALESCE(i.unit,'') AS unit,
                   COALESCE(i.minimum_stock_level,0) AS minimum_stock_level,
                   COALESCE(SUM(CASE WHEN sm.movement_type='opening_stock_in' THEN sm.quantity_in ELSE 0 END),0) AS opening_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='purchase_in' THEN sm.quantity_in ELSE 0 END),0) AS purchase_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='sales_return_in' THEN sm.quantity_in ELSE 0 END),0) AS sales_return_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='adjustment_in' THEN sm.quantity_in ELSE 0 END),0) AS adjustment_in,
                   COALESCE(SUM(CASE WHEN sm.movement_type='delivery_out' THEN sm.quantity_out ELSE 0 END),0) AS delivery_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='invoice_out' THEN sm.quantity_out ELSE 0 END),0) AS invoice_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='purchase_return_out' THEN sm.quantity_out ELSE 0 END),0) AS purchase_return_qty,
                   COALESCE(SUM(CASE WHEN sm.movement_type='adjustment_out' THEN sm.quantity_out ELSE 0 END),0) AS adjustment_out,
                   COALESCE(SUM(sm.quantity_in - sm.quantity_out),0) AS available_qty
            FROM item_services i
            LEFT JOIN stock_movements sm ON sm.item_service_id=i.id AND sm.company_id=%s AND sm.branch_id=%s {date_clause}
            WHERE i.company_id=%s AND i.branch_id=%s AND i.is_active=1 AND LOWER(COALESCE(i.item_type,'')) <> 'service' {item_filter}
            GROUP BY i.id
            ORDER BY i.item_name
            """,
            join_params + where_params,
        )
        rows = dictfetchall(cursor)
    result = []
    for row in rows:
        avg = average_cost(company_id, branch_id, row["id"])
        row["average_cost"] = avg
        row["stock_value"] = money(row.get("available_qty")) * avg
        row["status"] = "Low Stock" if money(row.get("available_qty")) <= money(row.get("minimum_stock_level")) else "OK"
        if filters.get("low_stock_only") and row["status"] != "Low Stock":
            continue
        result.append(row)
    return result


def item_ledger(company_id, branch_id, item_id=None, date_from="", date_to=""):
    if not inventory_ready():
        return []
    clauses = ["sm.company_id=%s", "sm.branch_id=%s"]
    params = [company_id, branch_id]
    if item_id:
        clauses.append("sm.item_service_id=%s")
        params.append(item_id)
    if date_from:
        clauses.append("sm.movement_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("sm.movement_date <= %s")
        params.append(date_to)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sm.*, i.item_code, i.item_name
            FROM stock_movements sm
            JOIN item_services i ON i.id=sm.item_service_id
            WHERE {' AND '.join(clauses)}
            ORDER BY sm.movement_date, sm.id
            """,
            params,
        )
        data = dictfetchall(cursor)
    balances = {}
    for row in data:
        key = row["item_service_id"]
        balances[key] = balances.get(key, Decimal("0.00")) + money(row.get("quantity_in")) - money(row.get("quantity_out"))
        row["balance"] = balances[key]
    return data


def rebuild_stock_movements_from_transactions(company_id, branch_id, user_id=None, reset=False):
    if not inventory_ready():
        raise InventoryError("Inventory schema is not upgraded. Run upgrade_schema_inventory first.")
    with transaction.atomic():
        if reset:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM stock_movements WHERE company_id=%s AND branch_id=%s", [company_id, branch_id])
        counts = {"opening": ensure_opening_stock_movements(company_id, branch_id, user_id), "purchases": 0, "delivery_challans": 0, "invoices": 0, "sales_returns": 0, "purchase_returns": 0}
        for table, id_field, fn, key in [
            ("supplier_purchases", "id", post_supplier_purchase_stock, "purchases"),
            ("delivery_challans", "id", post_delivery_challan_stock, "delivery_challans"),
            ("sales_invoices", "id", post_sales_invoice_stock, "invoices"),
            ("sales_returns", "id", post_sales_return_stock, "sales_returns"),
            ("purchase_returns", "id", post_purchase_return_stock, "purchase_returns"),
        ]:
            if not table_exists(table):
                continue
            status_field = "status"
            with connection.cursor() as cursor:
                extra = " AND delivery_challan_id IS NULL" if table == "sales_invoices" else ""
                cursor.execute(f"SELECT {id_field} FROM {table} WHERE company_id=%s AND branch_id=%s AND COALESCE({status_field},'') <> 'Cancelled'{extra} ORDER BY id", [company_id, branch_id])
                ids = [row[0] for row in cursor.fetchall()]
            for pk in ids:
                try:
                    counts[key] += fn(company_id, branch_id, pk, user_id)
                except InventoryError:
                    continue
    return counts
