from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import connection, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render

from authentication.auth_utils import dictfetchall, dictfetchone, user_has_permission
from authentication.decorators import login_required_custom
from core import validators
from core.inventory_utils import (
    InventoryError,
    average_cost,
    create_stock_movement,
    get_stock_balance,
    get_available_stock,
    inventory_ready,
    item_ledger,
    reverse_stock_movements,
    table_exists,
)
from settings_module.services import log_user_activity, now_text


def scope(request):
    return request.session.get("company_id"), request.session.get("current_branch_id")


def can_inventory(request, action="view"):
    role_name = str(request.session.get("role_name") or "").lower()
    is_admin = int(request.session.get("is_master_user") or 0) == 1 or "admin" in role_name
    return user_has_permission(request, "inventory", action) or is_admin


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def items(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, item_code, item_name, item_type, default_purchase_rate
            FROM item_services
            WHERE company_id=%s AND branch_id=%s AND is_active=1 AND lower(COALESCE(item_type,'')) <> 'service'
            ORDER BY item_name
            """,
            [company_id, branch_id],
        )
        return dictfetchall(cursor)


@login_required_custom
def index(request):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    rows = get_stock_balance(company_id, branch_id, {}) if inventory_ready() else []
    total_value = sum(money(row.get("stock_value")) for row in rows)
    low_count = sum(1 for row in rows if row.get("status") == "Low Stock")
    return render(request, "inventory/index.html", {"page_title": "Inventory", "total_value": total_value, "low_count": low_count, "ready": inventory_ready()})


@login_required_custom
def stock_balance(request):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    filters = {
        "date_as_of": request.GET.get("date_as_of", "").strip(),
        "item_service_id": request.GET.get("item_service_id", "").strip(),
        "low_stock_only": request.GET.get("low_stock_only") == "on",
    }
    rows = get_stock_balance(company_id, branch_id, filters)
    if request.GET.get("export") == "csv":
        return csv_response("stock_balance.csv", ["Item Code", "Item Name", "Available Qty", "Average Cost", "Stock Value", "Minimum Level", "Status"], [[r.get("item_code"), r.get("item_name"), r.get("available_qty"), r.get("average_cost"), r.get("stock_value"), r.get("minimum_stock_level"), r.get("status")] for r in rows])
    return render(request, "inventory/stock_balance.html", {"page_title": "Stock Balance", "rows": rows, "filters": filters, "items": items(company_id, branch_id), "print_mode": request.GET.get("print") == "1"})


@login_required_custom
def item_ledger_view(request):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    item_id = request.GET.get("item_service_id", "").strip()
    rows = item_ledger(company_id, branch_id, item_id, request.GET.get("date_from", ""), request.GET.get("date_to", ""))
    if request.GET.get("export") == "csv":
        return csv_response("item_ledger.csv", ["Date", "Type", "Source No", "Item", "Qty In", "Qty Out", "Balance", "Unit Cost", "Remarks"], [[r.get("movement_date"), r.get("movement_type"), r.get("source_no"), r.get("item_name"), r.get("quantity_in"), r.get("quantity_out"), r.get("balance"), r.get("unit_cost"), r.get("remarks")] for r in rows])
    return render(request, "inventory/item_ledger.html", {"page_title": "Item Ledger", "rows": rows, "items": items(company_id, branch_id), "selected_item": item_id, "date_from": request.GET.get("date_from", ""), "date_to": request.GET.get("date_to", ""), "print_mode": request.GET.get("print") == "1"})


def movement_report(request, direction):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    qty_clause = "quantity_in > 0" if direction == "in" else "quantity_out > 0"
    params = [company_id, branch_id]
    clauses = ["sm.company_id=%s", "sm.branch_id=%s", qty_clause]
    if request.GET.get("date_from"):
        clauses.append("sm.movement_date >= %s")
        params.append(request.GET["date_from"])
    if request.GET.get("date_to"):
        clauses.append("sm.movement_date <= %s")
        params.append(request.GET["date_to"])
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sm.*, i.item_code, i.item_name
            FROM stock_movements sm
            JOIN item_services i ON i.id=sm.item_service_id
            WHERE {' AND '.join(clauses)}
            ORDER BY sm.movement_date DESC, sm.id DESC
            """,
            params,
        )
        rows = dictfetchall(cursor)
    title = "Stock In" if direction == "in" else "Stock Out"
    if request.GET.get("export") == "csv":
        return csv_response(f"stock_{direction}.csv", ["Date", "Type", "Source No", "Item", "Qty In", "Qty Out", "Unit Cost"], [[r.get("movement_date"), r.get("movement_type"), r.get("source_no"), r.get("item_name"), r.get("quantity_in"), r.get("quantity_out"), r.get("unit_cost")] for r in rows])
    return render(request, "inventory/movements.html", {"page_title": title, "rows": rows, "direction": direction, "print_mode": request.GET.get("print") == "1"})


def stock_in(request):
    return movement_report(request, "in")


def stock_out(request):
    return movement_report(request, "out")


def low_stock(request):
    q = request.GET.copy()
    q["low_stock_only"] = "on"
    request.GET = q
    return stock_balance(request)


def valuation(request):
    return stock_balance(request)


@login_required_custom
def adjustments(request):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    rows = []
    if inventory_ready() and table_exists("stock_adjustments"):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM stock_adjustments WHERE company_id=%s AND branch_id=%s ORDER BY adjustment_date DESC, id DESC", [company_id, branch_id])
            rows = dictfetchall(cursor)
    return render(request, "inventory/adjustments_list.html", {"page_title": "Stock Adjustments", "rows": rows, "can_add": can_inventory(request, "add")})


def next_adjustment_no(company_id, branch_id):
    prefix = f"ADJ-{date.today().year}-"
    with connection.cursor() as cursor:
        cursor.execute("SELECT adjustment_no FROM stock_adjustments WHERE company_id=%s AND branch_id=%s AND adjustment_no LIKE %s ORDER BY adjustment_no DESC LIMIT 1", [company_id, branch_id, f"{prefix}%"])
        row = cursor.fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            number = 1
    return f"{prefix}{number:04d}"


@login_required_custom
def adjustment_form(request):
    if not can_inventory(request, "add"):
        return render(request, "errors/403.html", status=403)
    if not inventory_ready() or not table_exists("stock_adjustments"):
        messages.error(request, "Inventory tables are not installed. Run python manage.py upgrade_schema_inventory first.")
        return redirect("inventory:adjustments")
    company_id, branch_id = scope(request)
    form_data = {"adjustment_no": next_adjustment_no(company_id, branch_id), "adjustment_date": date.today().isoformat(), "adjustment_type": "Stock In", "reason": "", "items": [{"item_service_id": "", "quantity": "1", "unit_cost": "0", "remarks": ""}]}
    errors = {}
    if request.method == "POST":
        form_data = parse_adjustment_post(request.POST)
        errors, form_data = validate_adjustment(company_id, branch_id, form_data)
        if not errors:
            try:
                adjustment_id = save_adjustment(company_id, branch_id, request.session.get("user_id"), form_data)
                log_user_activity(request, "CREATE", "Inventory", "stock_adjustments", adjustment_id, f"Created stock adjustment {form_data['adjustment_no']}.")
                messages.success(request, "Stock adjustment posted successfully.")
                return redirect("inventory:adjustment_detail", adjustment_id=adjustment_id)
            except ValueError as exc:
                messages.error(request, str(exc))
    return render(request, "inventory/adjustment_form.html", {"page_title": "New Stock Adjustment", "form_data": form_data, "form_items": form_data.get("items", []), "errors": errors, "items": items(company_id, branch_id)})


def parse_adjustment_post(post):
    rows = []
    item_ids = post.getlist("item_service_id[]")
    quantities = post.getlist("quantity[]")
    costs = post.getlist("unit_cost[]")
    remarks = post.getlist("item_remarks[]")
    for index, item_id in enumerate(item_ids):
        rows.append({"item_service_id": item_id, "quantity": quantities[index] if index < len(quantities) else "", "unit_cost": costs[index] if index < len(costs) else "0", "remarks": remarks[index] if index < len(remarks) else ""})
    return {"adjustment_no": post.get("adjustment_no", ""), "adjustment_date": post.get("adjustment_date", ""), "adjustment_type": post.get("adjustment_type", "Stock In"), "reason": post.get("reason", ""), "items": rows}


def validate_adjustment(company_id, branch_id, data):
    errors = {}
    cleaned = dict(data)
    cleaned["adjustment_no"], errors["adjustment_no"] = validators.clean_text(data.get("adjustment_no"), max_length=50, required=True, field_name="Adjustment No")
    adj_date, errors["adjustment_date"] = validators.validate_date(data.get("adjustment_date"), "Adjustment Date", required=True)
    cleaned["adjustment_date"] = adj_date.isoformat() if adj_date else ""
    errors["adjustment_type"] = validators.validate_choice(data.get("adjustment_type"), ["Stock In", "Stock Out"], "Adjustment Type")
    cleaned["reason"], errors["reason"] = validators.clean_text(data.get("reason"), field_name="Reason")
    rows = []
    for row in data.get("items") or []:
        if not row.get("item_service_id"):
            continue
        qty, err = validators.validate_decimal(row.get("quantity"), "Quantity", min_value=0, allow_zero=False, required=True)
        if err:
            errors["items"] = err
            continue
        unit_cost, cost_err = validators.validate_money(row.get("unit_cost") or 0, "Unit Cost", allow_negative=False)
        if cost_err:
            errors["items"] = cost_err
            continue
        if data.get("adjustment_type") == "Stock Out":
            try:
                from core.inventory_utils import validate_available_stock
                validate_available_stock(company_id, branch_id, row["item_service_id"], qty, "Stock Adjustment")
            except ValueError as exc:
                errors["items"] = str(exc)
        rows.append({**row, "quantity": str(qty), "unit_cost": str(unit_cost or Decimal("0.00"))})
    if not rows:
        errors["items"] = "At least one stock item is required."
    cleaned["items"] = rows
    return {k: v for k, v in errors.items() if v}, cleaned


def save_adjustment(company_id, branch_id, user_id, data):
    timestamp = now_text()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO stock_adjustments (company_id, branch_id, adjustment_no, adjustment_date, adjustment_type, reason, status, created_by_id, updated_by_id, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,'Posted',%s,%s,%s,%s)
                """,
                [company_id, branch_id, data["adjustment_no"], data["adjustment_date"], data["adjustment_type"], data.get("reason"), user_id, user_id, timestamp, timestamp],
            )
            adj_id = cursor.lastrowid
            movement_type = "adjustment_in" if data["adjustment_type"] == "Stock In" else "adjustment_out"
            for row in data["items"]:
                cursor.execute("INSERT INTO stock_adjustment_items (adjustment_id, item_service_id, quantity, unit_cost, remarks) VALUES (%s,%s,%s,%s,%s)", [adj_id, row["item_service_id"], row["quantity"], row["unit_cost"], row.get("remarks")])
                create_stock_movement(company_id, branch_id, row["item_service_id"], data["adjustment_date"], movement_type, "stock_adjustment", adj_id, data["adjustment_no"], quantity_in=row["quantity"] if movement_type == "adjustment_in" else 0, quantity_out=row["quantity"] if movement_type == "adjustment_out" else 0, unit_cost=row["unit_cost"], remarks=row.get("remarks") or data.get("reason"), created_by_id=user_id)
    return adj_id


@login_required_custom
def adjustment_detail(request, adjustment_id):
    if not can_inventory(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    adjustment, rows = get_adjustment(company_id, branch_id, adjustment_id)
    if not adjustment:
        messages.error(request, "Stock adjustment was not found.")
        return redirect("inventory:adjustments")
    return render(request, "inventory/adjustment_detail.html", {"page_title": adjustment["adjustment_no"], "adjustment": adjustment, "items": rows, "can_cancel": adjustment.get("status") != "Cancelled" and can_inventory(request, "delete")})


def get_adjustment(company_id, branch_id, adjustment_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM stock_adjustments WHERE id=%s AND company_id=%s AND branch_id=%s LIMIT 1", [adjustment_id, company_id, branch_id])
        adjustment = dictfetchone(cursor)
        cursor.execute("SELECT sai.*, i.item_code, i.item_name FROM stock_adjustment_items sai JOIN item_services i ON i.id=sai.item_service_id WHERE sai.adjustment_id=%s ORDER BY sai.id", [adjustment_id])
        rows = dictfetchall(cursor)
    return adjustment, rows


@login_required_custom
def cancel_adjustment(request, adjustment_id):
    if not can_inventory(request, "delete"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = scope(request)
    adjustment, _rows = get_adjustment(company_id, branch_id, adjustment_id)
    if not adjustment:
        messages.error(request, "Stock adjustment was not found.")
        return redirect("inventory:adjustments")
    if request.method == "POST":
        try:
            with transaction.atomic():
                reverse_stock_movements("stock_adjustment", adjustment_id, f"Cancel stock adjustment {adjustment['adjustment_no']}", request.session.get("user_id"))
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE stock_adjustments SET status='Cancelled', updated_by_id=%s, updated_at=%s WHERE id=%s", [request.session.get("user_id"), now_text(), adjustment_id])
            messages.success(request, "Stock adjustment cancelled successfully.")
            return redirect("inventory:adjustment_detail", adjustment_id=adjustment_id)
        except ValueError as exc:
            messages.error(request, str(exc))
    return render(request, "inventory/confirm_cancel_adjustment.html", {"page_title": "Cancel Stock Adjustment", "adjustment": adjustment})


@login_required_custom
def print_adjustment(request, adjustment_id):
    company_id, branch_id = scope(request)
    adjustment, rows = get_adjustment(company_id, branch_id, adjustment_id)
    return render(request, "inventory/adjustment_print.html", {"adjustment": adjustment, "items": rows, "print_date": date.today()})


def csv_response(filename, headers, rows):
    content = [",".join(headers)]
    for row in rows:
        content.append(",".join([f'"{str(value or "").replace(chr(34), chr(34) + chr(34))}"' for value in row]))
    response = HttpResponse("\n".join(content), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
