from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import connection

from accounts_module.reports_utils import get_account_ledger, get_trial_balance
from authentication.auth_utils import dictfetchall, dictfetchone, get_user_allowed_branches


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


def rows(sql, params=None):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchall(cursor)
    except Exception:
        return []


def row(sql, params=None):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            return dictfetchone(cursor)
    except Exception:
        return None


def scalar(sql, params=None, default=0):
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            value = cursor.fetchone()
            return value[0] if value and value[0] is not None else default
    except Exception:
        return default


def money(value):
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def percent(numerator, denominator):
    denominator = money(denominator)
    if denominator == 0:
        return Decimal("0.00")
    return ((money(numerator) / denominator) * Decimal("100")).quantize(Decimal("0.01"))


def current_scope(request):
    company_id = request.session.get("company_id")
    current_branch_id = request.session.get("current_branch_id")
    allowed = get_user_allowed_branches(request.session.get("user_id")) if request.session.get("user_id") else []
    allowed_ids = {int(branch["id"]) for branch in allowed}
    requested_branch = request.GET.get("branch_id")
    branch_id = current_branch_id
    if requested_branch:
        try:
            requested_id = int(requested_branch)
            if requested_id in allowed_ids:
                branch_id = requested_id
        except ValueError:
            branch_id = current_branch_id
    return company_id, branch_id, allowed


def date_filters(request, date_column, params):
    clauses = []
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if date_from:
        clauses.append(f"{date_column} >= %s")
        params.append(date_from)
    if date_to:
        clauses.append(f"{date_column} <= %s")
        params.append(date_to)
    return clauses


def report_filters(request, company_id, branch_id):
    return {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "q": request.GET.get("q", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "customer_id": request.GET.get("customer_id", "").strip(),
        "supplier_id": request.GET.get("supplier_id", "").strip(),
        "account_id": request.GET.get("account_id", "").strip(),
        "cash_bank_account_id": request.GET.get("cash_bank_account_id", "").strip(),
        "branch_id": str(branch_id or ""),
        "customers": lookup_rows("customers", company_id, branch_id, "company_name"),
        "suppliers": lookup_rows("suppliers", company_id, branch_id, "supplier_name"),
        "accounts": lookup_rows("accounts", company_id, branch_id, "account_name", include_company_level=True),
        "cash_bank_accounts": lookup_rows("cash_bank_accounts", company_id, branch_id, "account_name"),
    }


def lookup_rows(table, company_id, branch_id, label_field, include_company_level=False):
    if not table_exists(table):
        return []
    branch_clause = "(branch_id = %s OR branch_id IS NULL)" if include_company_level else "branch_id = %s"
    return rows(
        f"SELECT id, {label_field} AS name FROM {table} WHERE company_id=%s AND {branch_clause} ORDER BY {label_field}",
        [company_id, branch_id],
    )


def customer_name_expr(alias="c"):
    return f"{alias}.company_name"


def quotation_party_expr():
    if column_exists("quotations", "customer_name"):
        return "COALESCE(NULLIF(q.customer_name, ''), c.company_name)"
    return "c.company_name"


def apply_search(clauses, params, search, expressions):
    if not search:
        return
    like = f"%{search}%"
    clauses.append("(" + " OR ".join([f"{expr} LIKE %s" for expr in expressions]) + ")")
    params.extend([like] * len(expressions))


def customer_ledger(company_id, branch_id, filters):
    customer_id = filters.get("customer_id")
    customer = None
    if customer_id:
        customer = row("SELECT * FROM customers WHERE company_id=%s AND branch_id=%s AND id=%s", [company_id, branch_id, customer_id])
    if not customer or not customer.get("account_id"):
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00"}
    account_id = customer["account_id"]
    opening = money(scalar(
        """
        SELECT COALESCE(SUM(jel.debit - jel.credit),0)
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id=jel.journal_entry_id
        WHERE je.company_id=%s AND je.branch_id=%s AND jel.account_id=%s AND je.entry_date < %s
        """,
        [company_id, branch_id, account_id, filters.get("date_from") or "0001-01-01"],
    ))
    data = get_account_ledger(company_id, branch_id, account_id, filters.get("date_from") or None, filters.get("date_to") or None)
    running = opening
    for item in data:
        running += money(item.get("debit")) - money(item.get("credit"))
        item["balance"] = running
    return data, {"Opening Balance": opening, "Closing Balance": running}


def customer_outstanding(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'", "COALESCE(si.balance_amount,0) > 0"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("customer_id"):
        clauses.append("si.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["si.invoice_no", "c.company_name", "si.po_number"])
    data = rows(
        f"""
        SELECT c.company_name AS customer, si.invoice_no, si.invoice_date, si.due_date,
               si.grand_total, si.received_amount, si.balance_amount, si.status
        FROM sales_invoices si
        JOIN customers c ON c.id=si.customer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY si.invoice_date DESC, si.id DESC
        """,
        params,
    )
    return data, {"Total Outstanding": sum(money(item.get("balance_amount")) for item in data)}


def customer_aging(company_id, branch_id, filters):
    data, _summary = customer_outstanding(company_id, branch_id, filters)
    today = date.today()
    buckets = {}
    for item in data:
        customer = item["customer"]
        buckets.setdefault(customer, {"customer": customer, "total": Decimal("0.00"), "b0_30": Decimal("0.00"), "b31_60": Decimal("0.00"), "b61_90": Decimal("0.00"), "b90_plus": Decimal("0.00")})
        balance = money(item.get("balance_amount"))
        base_date = parse_date(item.get("due_date") or item.get("invoice_date")) or today
        age = (today - base_date).days
        key = "b0_30" if age <= 30 else "b31_60" if age <= 60 else "b61_90" if age <= 90 else "b90_plus"
        buckets[customer][key] += balance
        buckets[customer]["total"] += balance
    data = list(buckets.values())
    return data, {"Total Outstanding": sum(item["total"] for item in data)}


def customer_statement(company_id, branch_id, filters):
    customer_id = filters.get("customer_id")
    if not customer_id:
        return [], {"Closing Balance": "0.00"}
    params = [company_id, branch_id, customer_id]
    date_clause_invoice, invoice_params = bounded_date_clause(filters, "invoice_date")
    date_clause_receipt, receipt_params = bounded_date_clause(filters, "receipt_date")
    date_clause_return, return_params = bounded_date_clause(filters, "return_date")
    data = rows(
        f"""
        SELECT invoice_date AS date, 'Invoice' AS type, invoice_no AS ref_no, 'Sales invoice' AS description,
               grand_total AS debit, 0 AS credit
        FROM sales_invoices
        WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND status <> 'Cancelled' {date_clause_invoice}
        UNION ALL
        SELECT receipt_date AS date, 'Receipt' AS type, receipt_no AS ref_no, 'Customer receipt' AS description,
               0 AS debit, amount AS credit
        FROM customer_receipts
        WHERE company_id=%s AND branch_id=%s AND customer_id=%s {date_clause_receipt}
        UNION ALL
        SELECT return_date AS date, 'Sales Return' AS type, sales_return_no AS ref_no, COALESCE(return_reason, 'Sales return') AS description,
               0 AS debit, grand_total AS credit
        FROM sales_returns
        WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND status <> 'Cancelled' {date_clause_return}
        ORDER BY date, ref_no
        """,
        params + invoice_params + params + receipt_params + params + return_params,
    )
    running = Decimal("0.00")
    for item in data:
        running += money(item.get("debit")) - money(item.get("credit"))
        item["balance"] = running
    return data, {"Closing Balance": running}


def supplier_ledger(company_id, branch_id, filters):
    supplier_id = filters.get("supplier_id")
    supplier = None
    if supplier_id:
        supplier = row("SELECT * FROM suppliers WHERE company_id=%s AND branch_id=%s AND id=%s", [company_id, branch_id, supplier_id])
    if not supplier or not supplier.get("account_id"):
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00"}
    account_id = supplier["account_id"]
    opening = money(scalar(
        """
        SELECT COALESCE(SUM(jel.credit - jel.debit),0)
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id=jel.journal_entry_id
        WHERE je.company_id=%s AND je.branch_id=%s AND jel.account_id=%s AND je.entry_date < %s
        """,
        [company_id, branch_id, account_id, filters.get("date_from") or "0001-01-01"],
    ))
    data = get_account_ledger(company_id, branch_id, account_id, filters.get("date_from") or None, filters.get("date_to") or None)
    running = opening
    for item in data:
        running += money(item.get("credit")) - money(item.get("debit"))
        item["balance"] = running
    return data, {"Opening Balance": opening, "Closing Balance": running}


def supplier_payable(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s", "sp.status <> 'Cancelled'", "COALESCE(sp.balance_amount,0) > 0"]
    clauses.extend(date_filters_from_values(filters, "sp.purchase_date", params))
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["sp.purchase_no", "s.supplier_name", "sp.supplier_bill_no"])
    data = rows(
        f"""
        SELECT s.supplier_name AS supplier, sp.purchase_no, sp.purchase_date, sp.supplier_bill_no,
               sp.grand_total, sp.paid_amount, sp.balance_amount, sp.status
        FROM supplier_purchases sp
        JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sp.purchase_date DESC, sp.id DESC
        """,
        params,
    )
    return data, {"Total Payable": sum(money(item.get("balance_amount")) for item in data)}


def supplier_aging(company_id, branch_id, filters):
    data, _summary = supplier_payable(company_id, branch_id, filters)
    today = date.today()
    buckets = {}
    for item in data:
        supplier = item["supplier"]
        buckets.setdefault(supplier, {"supplier": supplier, "total": Decimal("0.00"), "b0_30": Decimal("0.00"), "b31_60": Decimal("0.00"), "b61_90": Decimal("0.00"), "b90_plus": Decimal("0.00")})
        balance = money(item.get("balance_amount"))
        base_date = parse_date(item.get("purchase_date")) or today
        age = (today - base_date).days
        key = "b0_30" if age <= 30 else "b31_60" if age <= 60 else "b61_90" if age <= 90 else "b90_plus"
        buckets[supplier][key] += balance
        buckets[supplier]["total"] += balance
    data = list(buckets.values())
    return data, {"Total Payable": sum(item["total"] for item in data)}


def supplier_statement(company_id, branch_id, filters):
    supplier_id = filters.get("supplier_id")
    if not supplier_id:
        return [], {"Closing Balance": "0.00"}
    params = [company_id, branch_id, supplier_id]
    purchase_clause, purchase_params = bounded_date_clause(filters, "purchase_date")
    payment_clause, payment_params = bounded_date_clause(filters, "payment_date")
    return_clause, return_params = bounded_date_clause(filters, "return_date")
    data = rows(
        f"""
        SELECT purchase_date AS date, 'Purchase' AS type, purchase_no AS ref_no, 'Supplier purchase' AS description,
               0 AS debit, grand_total AS credit
        FROM supplier_purchases
        WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND status <> 'Cancelled' {purchase_clause}
        UNION ALL
        SELECT payment_date AS date, 'Payment' AS type, payment_no AS ref_no, 'Supplier payment' AS description,
               amount AS debit, 0 AS credit
        FROM supplier_payments
        WHERE company_id=%s AND branch_id=%s AND supplier_id=%s {payment_clause}
        UNION ALL
        SELECT return_date AS date, 'Purchase Return' AS type, purchase_return_no AS ref_no, COALESCE(return_reason, 'Purchase return') AS description,
               grand_total AS debit, 0 AS credit
        FROM purchase_returns
        WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND status <> 'Cancelled' {return_clause}
        ORDER BY date, ref_no
        """,
        params + purchase_params + params + payment_params + params + return_params,
    )
    running = Decimal("0.00")
    for item in data:
        running += money(item.get("credit")) - money(item.get("debit"))
        item["balance"] = running
    return data, {"Closing Balance": running}


def sales_invoice_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("status"):
        clauses.append("si.status=%s")
        params.append(filters["status"])
    if filters.get("customer_id"):
        clauses.append("si.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["si.invoice_no", "c.company_name", "si.po_number"])
    data = rows(
        f"""
        SELECT si.invoice_no, si.invoice_date, si.invoice_type, c.company_name AS customer,
               si.po_number, si.grand_total, si.received_amount, si.balance_amount, si.status
        FROM sales_invoices si
        JOIN customers c ON c.id=si.customer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY si.invoice_date DESC, si.id DESC
        """,
        params,
    )
    return data, totals(data, ["grand_total", "received_amount", "balance_amount"])


def receipt_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["cr.company_id=%s", "cr.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "cr.receipt_date", params))
    if filters.get("customer_id"):
        clauses.append("cr.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["cr.receipt_no", "c.company_name", "cr.cheque_reference_no", "si.invoice_no"])
    data = rows(
        f"""
        SELECT cr.receipt_no, cr.receipt_date, c.company_name AS customer, cr.payment_mode,
               cb.account_name AS cash_bank, cr.cheque_reference_no, cr.amount, si.invoice_no AS adjusted_invoice
        FROM customer_receipts cr
        JOIN customers c ON c.id=cr.customer_id
        JOIN cash_bank_accounts cb ON cb.id=cr.cash_bank_account_id
        LEFT JOIN sales_invoices si ON si.id=cr.adjusted_invoice_id
        WHERE {' AND '.join(clauses)}
        ORDER BY cr.receipt_date DESC, cr.id DESC
        """,
        params,
    )
    return data, {"Total Received": sum(money(item.get("amount")) for item in data)}


def purchase_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sp.purchase_date", params))
    if filters.get("status"):
        clauses.append("sp.status=%s")
        params.append(filters["status"])
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["sp.purchase_no", "s.supplier_name", "sp.supplier_bill_no"])
    data = rows(
        f"""
        SELECT sp.purchase_no, sp.purchase_date, s.supplier_name AS supplier, sp.supplier_bill_no,
               sp.grand_total, sp.paid_amount, sp.balance_amount, sp.status
        FROM supplier_purchases sp
        JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sp.purchase_date DESC, sp.id DESC
        """,
        params,
    )
    return data, totals(data, ["grand_total", "paid_amount", "balance_amount"])


def supplier_payment_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sp.payment_date", params))
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["sp.payment_no", "s.supplier_name", "sp.cheque_reference_no", "pur.purchase_no"])
    data = rows(
        f"""
        SELECT sp.payment_no, sp.payment_date, s.supplier_name AS supplier, sp.payment_mode,
               cb.account_name AS cash_bank, sp.cheque_reference_no, sp.amount, pur.purchase_no AS adjusted_purchase
        FROM supplier_payments sp
        JOIN suppliers s ON s.id=sp.supplier_id
        JOIN cash_bank_accounts cb ON cb.id=sp.cash_bank_account_id
        LEFT JOIN supplier_purchases pur ON pur.id=sp.adjusted_purchase_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sp.payment_date DESC, sp.id DESC
        """,
        params,
    )
    return data, {"Total Paid": sum(money(item.get("amount")) for item in data)}


def cash_bank_book(company_id, branch_id, filters, account_type):
    params = [company_id, branch_id, account_type]
    clauses = ["je.company_id=%s", "je.branch_id=%s", "lower(cb.account_type)=lower(%s)"]
    clauses.extend(date_filters_from_values(filters, "je.entry_date", params))
    if filters.get("cash_bank_account_id"):
        clauses.append("cb.id=%s")
        params.append(filters["cash_bank_account_id"])
    data = rows(
        f"""
        SELECT je.entry_date AS date, je.entry_no, cb.account_name AS account,
               COALESCE(jel.description, je.description) AS description, jel.debit, jel.credit
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id=jel.journal_entry_id
        JOIN cash_bank_accounts cb ON cb.account_id=jel.account_id
        WHERE {' AND '.join(clauses)}
        ORDER BY je.entry_date, je.entry_no, jel.id
        """,
        params,
    )
    running = Decimal("0.00")
    for item in data:
        running += money(item.get("debit")) - money(item.get("credit"))
        item["balance"] = running
    return data, {"Closing Balance": running}


def general_ledger(company_id, branch_id, filters):
    account_id = filters.get("account_id")
    if account_id:
        account = row("SELECT account_name FROM accounts WHERE company_id=%s AND (branch_id=%s OR branch_id IS NULL) AND id=%s", [company_id, branch_id, account_id])
        if not account:
            return [], {"Closing Balance": "0.00"}
        data = get_account_ledger(company_id, branch_id, account_id, filters.get("date_from") or None, filters.get("date_to") or None)
        for item in data:
            item["account"] = account.get("account_name")
            item["balance"] = item.pop("running_balance")
        return data, {"Closing Balance": data[-1]["balance"] if data else "0.00"}
    params = [company_id, branch_id]
    clauses = ["je.company_id=%s", "je.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "je.entry_date", params))
    data = rows(
        f"""
        SELECT je.entry_date AS date, je.entry_no, a.account_name AS account,
               COALESCE(jel.description, je.description) AS description, jel.debit, jel.credit
        FROM journal_entry_lines jel
        JOIN journal_entries je ON je.id=jel.journal_entry_id
        JOIN accounts a ON a.id=jel.account_id
        WHERE {' AND '.join(clauses)}
        ORDER BY je.entry_date DESC, je.entry_no DESC, jel.id
        """,
        params,
    )
    return data, totals(data, ["debit", "credit"])


def trial_balance(company_id, branch_id, filters):
    data = get_trial_balance(company_id, branch_id, filters.get("date_to") or None)
    return data, {
        "Total Debit": sum(money(item.get("balance_debit")) for item in data),
        "Total Credit": sum(money(item.get("balance_credit")) for item in data),
    }


def profit_loss(company_id, branch_id, filters):
    trial, _summary = trial_balance(company_id, branch_id, filters)
    groups = {"Income": Decimal("0.00"), "Expenses": Decimal("0.00")}
    for item in trial:
        account_type = item.get("account_type")
        if account_type == "Income":
            groups["Income"] += money(item.get("balance_credit")) - money(item.get("balance_debit"))
        elif account_type == "Expenses":
            groups["Expenses"] += money(item.get("balance_debit")) - money(item.get("balance_credit"))
    net = groups["Income"] - groups["Expenses"]
    data = [
        {"section": "Income", "amount": groups["Income"]},
        {"section": "Less Expenses / Cost", "amount": groups["Expenses"]},
        {"section": "Net Profit / Loss", "amount": net},
    ]
    return data, {"Net Profit / Loss": net}


def balance_sheet(company_id, branch_id, filters):
    trial, _summary = trial_balance(company_id, branch_id, filters)
    groups = {"Assets": Decimal("0.00"), "Liabilities": Decimal("0.00"), "Equity": Decimal("0.00")}
    for item in trial:
        account_type = item.get("account_type")
        if account_type == "Assets":
            groups["Assets"] += money(item.get("balance_debit")) - money(item.get("balance_credit"))
        elif account_type == "Liabilities":
            groups["Liabilities"] += money(item.get("balance_credit")) - money(item.get("balance_debit"))
        elif account_type == "Equity":
            groups["Equity"] += money(item.get("balance_credit")) - money(item.get("balance_debit"))
    data = [{"section": key, "amount": value} for key, value in groups.items()]
    data.append({"section": "Assets - Liabilities - Equity", "amount": groups["Assets"] - groups["Liabilities"] - groups["Equity"]})
    return data, groups


def placeholder_report(_company_id, _branch_id, _filters):
    return [], {"Status": "This report route is reserved for the reporting phase and will be expanded from the same framework."}


def date_filters_from_values(filters, date_column, params):
    clauses = []
    if filters.get("date_from"):
        clauses.append(f"{date_column} >= %s")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append(f"{date_column} <= %s")
        params.append(filters["date_to"])
    return clauses


def bounded_date_clause(filters, column_name):
    clause = ""
    params = []
    if filters.get("date_from"):
        clause += f" AND {column_name} >= %s"
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clause += f" AND {column_name} <= %s"
        params.append(filters["date_to"])
    return clause, params


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def totals(data, keys):
    return {key.replace("_", " ").title(): sum(money(item.get(key)) for item in data) for key in keys}
