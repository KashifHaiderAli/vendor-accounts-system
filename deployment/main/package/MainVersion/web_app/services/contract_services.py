from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction

from authentication.auth_utils import dictfetchall, dictfetchone
from core.edition_utils import is_tax_enabled
from core import validators
from core.print_utils import build_print_context
from sales import invoice_services
from settings_module.services import get_numbering_settings, get_tax_settings, log_user_activity, now_text


PER_PAGE = 20
STATUSES = ["Active", "Expired", "Closed"]
BILLING_CYCLES = ["Monthly", "Quarterly", "Yearly", "One Time"]


def today_iso():
    return date.today().isoformat()


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def paginate(total_count, page, per_page=PER_PAGE):
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    return {"page": page, "per_page": per_page, "total_count": total_count, "total_pages": total_pages, "offset": (page - 1) * per_page, "pages": list(range(1, total_pages + 1))}


def generate_contract_no(company_id, branch_id):
    settings = get_numbering_settings(company_id, branch_id)
    prefix = settings.get("service_contract_prefix") or "SC"
    padding = int(settings.get("number_padding") or 4)
    doc_prefix = f"{prefix}-{date.today().year}-" if int(settings.get("use_year_in_number") or 0) == 1 else f"{prefix}-"
    with connection.cursor() as cursor:
        cursor.execute("SELECT contract_no FROM service_contracts WHERE company_id=%s AND branch_id=%s AND contract_no LIKE %s ORDER BY contract_no DESC LIMIT 1", [company_id, branch_id, f"{doc_prefix}%"])
        row = cursor.fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            number = 1
    return f"{doc_prefix}{number:0{padding}d}"


def list_contracts(company_id, branch_id, search="", status="", billing_cycle="", expiring_soon=False, billing_due=False, date_from="", date_to="", page=1):
    clauses = ["sc.company_id=%s", "sc.branch_id=%s"]
    params = [company_id, branch_id]
    today = today_iso()
    if search:
        like = f"%{search}%"
        clauses.append("(sc.contract_no LIKE %s OR c.company_name LIKE %s OR sc.service_type LIKE %s)")
        params.extend([like, like, like])
    if status:
        clauses.append("sc.status=%s")
        params.append(status)
    if billing_cycle:
        clauses.append("sc.billing_cycle=%s")
        params.append(billing_cycle)
    if expiring_soon:
        clauses.append("sc.end_date IS NOT NULL AND sc.end_date BETWEEN %s AND date(%s, '+30 day')")
        params.extend([today, today])
    if billing_due:
        clauses.append("sc.next_billing_date IS NOT NULL AND sc.next_billing_date <= %s AND sc.status='Active'")
        params.append(today)
    if date_from:
        clauses.append("sc.start_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("sc.start_date <= %s")
        params.append(date_to)
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM service_contracts sc LEFT JOIN customers c ON c.id=sc.customer_id WHERE {where_sql}", params)
        pagination = paginate(int(cursor.fetchone()[0] or 0), page)
        cursor.execute(
            f"""
            SELECT sc.*, c.company_name AS customer_name
            FROM service_contracts sc
            LEFT JOIN customers c ON c.id=sc.customer_id
            WHERE {where_sql}
            ORDER BY sc.start_date DESC, sc.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [pagination["per_page"], pagination["offset"]],
        )
        return dictfetchall(cursor), pagination


def get_customers(company_id, branch_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, customer_code, company_name, account_id, payment_terms_id FROM customers WHERE company_id=%s AND branch_id=%s AND is_active=1 ORDER BY company_name", [company_id, branch_id])
        return dictfetchall(cursor)


def get_customer(company_id, branch_id, customer_id):
    if not customer_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM customers WHERE id=%s AND company_id=%s AND branch_id=%s AND is_active=1 LIMIT 1", [customer_id, company_id, branch_id])
        return dictfetchone(cursor)


def default_form_data(company_id, branch_id):
    return {"contract_no": generate_contract_no(company_id, branch_id), "customer_id": "", "service_type": "", "start_date": today_iso(), "end_date": "", "billing_cycle": "Monthly", "contract_amount": "0.00", "tax_applicable": 0, "next_billing_date": today_iso(), "renewal_reminder_date": "", "contract_details": "", "status": "Active", "remarks": ""}


def parse_post(post):
    return {"contract_no": post.get("contract_no", ""), "customer_id": post.get("customer_id", ""), "service_type": post.get("service_type", ""), "start_date": post.get("start_date", ""), "end_date": post.get("end_date", ""), "billing_cycle": post.get("billing_cycle", ""), "contract_amount": post.get("contract_amount", ""), "tax_applicable": validators.normalize_bool(post.get("tax_applicable")), "next_billing_date": post.get("next_billing_date", ""), "renewal_reminder_date": post.get("renewal_reminder_date", ""), "contract_details": post.get("contract_details", ""), "status": post.get("status", "Active"), "remarks": post.get("remarks", "")}


def contract_no_exists(company_id, branch_id, contract_no, exclude_id=None):
    params = [company_id, branch_id, contract_no]
    clause = "company_id=%s AND branch_id=%s AND lower(contract_no)=lower(%s)"
    if exclude_id:
        clause += " AND id<>%s"
        params.append(exclude_id)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM service_contracts WHERE {clause} LIMIT 1", params)
        return cursor.fetchone() is not None


def validate_contract(data, company_id, branch_id, contract_id=None):
    errors = {}
    cleaned = dict(data)
    cleaned["contract_no"], errors["contract_no"] = validators.clean_text(data.get("contract_no"), max_length=50, required=True, field_name="Contract No")
    if not errors["contract_no"] and contract_no_exists(company_id, branch_id, cleaned["contract_no"], contract_id):
        errors["contract_no"] = "Contract No already exists for the current branch."
    customer = get_customer(company_id, branch_id, data.get("customer_id"))
    if not customer:
        errors["customer_id"] = "Select a valid active customer."
    elif not customer.get("account_id"):
        errors["customer_id"] = "Selected customer does not have a linked receivable account."
    cleaned["customer_id"] = customer["id"] if customer else ""
    cleaned["service_type"], errors["service_type"] = validators.clean_text(data.get("service_type"), max_length=150, required=True, field_name="Service Type")
    start_date, errors["start_date"] = validators.validate_date(data.get("start_date"), "Start Date", required=True)
    end_date, errors["end_date"] = validators.validate_date(data.get("end_date"), "End Date", required=False)
    next_billing_date, errors["next_billing_date"] = validators.validate_date(data.get("next_billing_date"), "Next Billing Date", required=False)
    renewal_date, errors["renewal_reminder_date"] = validators.validate_date(data.get("renewal_reminder_date"), "Renewal Reminder Date", required=False)
    if start_date and end_date and end_date < start_date:
        errors["end_date"] = "End Date cannot be before Start Date."
    cleaned["start_date"] = start_date.isoformat() if start_date else ""
    cleaned["end_date"] = end_date.isoformat() if end_date else ""
    cleaned["next_billing_date"] = next_billing_date.isoformat() if next_billing_date else ""
    cleaned["renewal_reminder_date"] = renewal_date.isoformat() if renewal_date else ""
    errors["billing_cycle"] = validators.validate_choice(data.get("billing_cycle"), BILLING_CYCLES, "Billing Cycle")
    cleaned["billing_cycle"] = data.get("billing_cycle")
    amount, errors["contract_amount"] = validators.validate_money(data.get("contract_amount"), "Contract Amount", allow_zero=False, required=True)
    cleaned["contract_amount"] = amount or Decimal("0.00")
    cleaned["tax_applicable"] = validators.normalize_bool(data.get("tax_applicable")) if is_tax_enabled(company_id=company_id) else 0
    errors["status"] = validators.validate_choice(data.get("status"), STATUSES, "Status")
    cleaned["status"] = data.get("status") or "Active"
    cleaned["contract_details"], errors["contract_details"] = validators.clean_text(data.get("contract_details"), field_name="Contract Details")
    cleaned["remarks"], errors["remarks"] = validators.clean_text(data.get("remarks"), field_name="Remarks")
    return {k: v for k, v in errors.items() if v}, cleaned


def save_contract(company_id, branch_id, user_id, data, contract_id=None):
    timestamp = now_text()
    if contract_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE service_contracts SET customer_id=%s, service_type=%s, start_date=%s, end_date=%s,
                    billing_cycle=%s, contract_amount=%s, tax_applicable=%s, next_billing_date=%s,
                    renewal_reminder_date=%s, contract_details=%s, status=%s, remarks=%s,
                    updated_by_id=%s, updated_at=%s
                WHERE id=%s AND company_id=%s AND branch_id=%s
                """,
                [data["customer_id"], data["service_type"], data["start_date"], data.get("end_date") or None, data["billing_cycle"], str(data["contract_amount"]), data["tax_applicable"], data.get("next_billing_date") or None, data.get("renewal_reminder_date") or None, data.get("contract_details"), data["status"], data.get("remarks"), user_id, timestamp, contract_id, company_id, branch_id],
            )
        return contract_id
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO service_contracts (
                company_id, branch_id, contract_no, customer_id, service_type, start_date, end_date,
                billing_cycle, contract_amount, tax_applicable, next_billing_date, renewal_reminder_date,
                contract_details, status, remarks, created_by_id, updated_by_id, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [company_id, branch_id, data["contract_no"], data["customer_id"], data["service_type"], data["start_date"], data.get("end_date") or None, data["billing_cycle"], str(data["contract_amount"]), data["tax_applicable"], data.get("next_billing_date") or None, data.get("renewal_reminder_date") or None, data.get("contract_details"), data["status"], data.get("remarks"), user_id, user_id, timestamp, timestamp],
        )
        return cursor.lastrowid


def get_contract(company_id, branch_id, contract_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sc.*, c.company_name AS customer_name, c.address AS customer_address, c.phone AS customer_phone,
                   c.account_id AS customer_account_id, c.payment_terms_id
            FROM service_contracts sc
            LEFT JOIN customers c ON c.id=sc.customer_id
            WHERE sc.id=%s AND sc.company_id=%s AND sc.branch_id=%s
            LIMIT 1
            """,
            [contract_id, company_id, branch_id],
        )
        return dictfetchone(cursor)


def close_contract(request, contract):
    timestamp = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE service_contracts SET status='Closed', updated_by_id=%s, updated_at=%s WHERE id=%s", [request.session.get("user_id"), timestamp, contract["id"]])
    log_user_activity(request, "CLOSE", "Service Contracts", "service_contracts", contract["id"], f"Closed service contract {contract['contract_no']}.")


def add_months(source_date, months):
    year = source_date.year + (source_date.month - 1 + months) // 12
    month = (source_date.month - 1 + months) % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(source_date.day, days[month - 1]))


def next_billing_after(contract):
    current = date.fromisoformat(contract.get("next_billing_date") or today_iso())
    if contract["billing_cycle"] == "Monthly":
        return add_months(current, 1).isoformat(), "Active"
    if contract["billing_cycle"] == "Quarterly":
        return add_months(current, 3).isoformat(), "Active"
    if contract["billing_cycle"] == "Yearly":
        return add_months(current, 12).isoformat(), "Active"
    return "", "Closed"


def generate_invoice_from_contract(request, contract):
    if contract.get("status") != "Active":
        raise ValueError("Only active contracts can generate invoices.")
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    user_id = request.session.get("user_id")
    tax_enabled = is_tax_enabled(request=request, company_id=company_id)
    tax = get_tax_settings(company_id, branch_id) if tax_enabled else {}
    invoice_type = "tax_invoice" if tax_enabled and int(contract.get("tax_applicable") or 0) == 1 else "cash_memo"
    tax_percent = tax.get("default_sales_tax_percent") or "0" if invoice_type == "tax_invoice" else "0"
    period_note = f"{contract['billing_cycle']} billing"
    if contract.get("next_billing_date"):
        period_note = f"{period_note} due {contract['next_billing_date']}"
    data = invoice_services.default_form_data(company_id, branch_id, invoice_type)
    data.update({"customer_id": contract["customer_id"], "payment_terms_id": contract.get("payment_terms_id") or "", "remarks": f"Generated from service contract {contract['contract_no']}."})
    data["items"] = [{"item_service_id": "", "description": f"{contract['service_type']} - {period_note}", "quantity": "1", "rate": str(contract["contract_amount"]), "discount_percent": "0", "discount_amount": "0", "tax_percent": str(tax_percent)}]
    errors, cleaned = invoice_services.validate_and_calculate(data, company_id, branch_id)
    if errors:
        raise ValueError(f"Invoice validation failed: {errors}")
    with transaction.atomic():
        invoice_id = invoice_services.save_invoice(company_id, branch_id, user_id, cleaned)
        next_date, status = next_billing_after(contract)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE service_contracts SET next_billing_date=%s, status=%s, updated_by_id=%s, updated_at=%s WHERE id=%s", [next_date or None, status, user_id, now_text(), contract["id"]])
    log_user_activity(request, "GENERATE_INVOICE", "Service Contracts", "service_contracts", contract["id"], f"Generated invoice from service contract {contract['contract_no']}.")
    return invoice_id


def mark_printed(request, contract):
    log_user_activity(request, "PRINT", "Service Contracts", "service_contracts", contract["id"], f"Printed service contract {contract['contract_no']}.")


def get_print_context(company_id, branch_id, contract_id):
    contract = get_contract(company_id, branch_id, contract_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return {"contract": contract, "company": company, "branch": branch, "print_date": today_iso(), **build_print_context(company_id)}
