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
        "as_of_date": request.GET.get("as_of_date", "").strip(),
        "q": request.GET.get("q", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "confirmation_type": request.GET.get("confirmation_type", "").strip(),
        "reference_type": request.GET.get("reference_type", "").strip(),
        "customer_id": request.GET.get("customer_id", "").strip(),
        "supplier_id": request.GET.get("supplier_id", "").strip(),
        "account_id": request.GET.get("account_id", "").strip(),
        "cash_bank_account_id": request.GET.get("cash_bank_account_id", "").strip(),
        "item_service_id": request.GET.get("item_service_id", "").strip(),
        "expense_head_id": request.GET.get("expense_head_id", "").strip(),
        "payment_mode": request.GET.get("payment_mode", "").strip(),
        "invoice_type": request.GET.get("invoice_type", "").strip(),
        "user_id": request.GET.get("user_id", "").strip(),
        "action": request.GET.get("action", "").strip(),
        "module": request.GET.get("module", "").strip(),
        "branch_id": str(branch_id or ""),
        "customers": get_filter_customers(company_id, branch_id),
        "suppliers": get_filter_suppliers(company_id, branch_id),
        "items": get_filter_items(company_id, branch_id),
        "expense_heads": lookup_rows("expense_heads", company_id, branch_id, "expense_name"),
        "accounts": get_filter_accounts(company_id, branch_id),
        "cash_bank_accounts": get_filter_cash_bank_accounts(company_id, branch_id),
        "users": get_filter_users(company_id),
    }


def lookup_rows(table, company_id, branch_id, label_field, include_company_level=False):
    if not table_exists(table):
        return []
    branch_clause = "(branch_id = %s OR branch_id IS NULL)" if include_company_level else "branch_id = %s"
    return rows(
        f"SELECT id, {label_field} AS name FROM {table} WHERE company_id=%s AND {branch_clause} ORDER BY {label_field}",
        [company_id, branch_id],
    )


def lookup_users(company_id):
    if not table_exists("users"):
        return []
    return rows(
        "SELECT id, full_name AS name FROM users WHERE company_id=%s AND is_active=1 ORDER BY full_name",
        [company_id],
    )


def get_filter_customers(company_id, branch_id):
    if not table_exists("customers"):
        return []
    return rows(
        """
        SELECT id, COALESCE(NULLIF(customer_code,''), '-') || ' - ' || company_name AS name
        FROM customers
        WHERE company_id=%s AND branch_id=%s AND is_active=1
        ORDER BY company_name
        """,
        [company_id, branch_id],
    )


def get_filter_suppliers(company_id, branch_id):
    if not table_exists("suppliers"):
        return []
    return rows(
        """
        SELECT id, COALESCE(NULLIF(supplier_code,''), '-') || ' - ' || supplier_name AS name
        FROM suppliers
        WHERE company_id=%s AND branch_id=%s AND is_active=1
        ORDER BY supplier_name
        """,
        [company_id, branch_id],
    )


def get_filter_items(company_id, branch_id):
    if not table_exists("item_services"):
        return []
    return rows(
        """
        SELECT id, COALESCE(NULLIF(item_code,''), '-') || ' - ' || item_name AS name
        FROM item_services
        WHERE company_id=%s AND branch_id=%s AND is_active=1
        ORDER BY item_name
        """,
        [company_id, branch_id],
    )


def get_filter_accounts(company_id, branch_id):
    if not table_exists("accounts"):
        return []
    return rows(
        """
        SELECT id, COALESCE(NULLIF(account_code,''), '-') || ' - ' || account_name AS name
        FROM accounts
        WHERE company_id=%s AND (branch_id=%s OR branch_id IS NULL)
        ORDER BY account_code, account_name
        """,
        [company_id, branch_id],
    )


def get_filter_cash_bank_accounts(company_id, branch_id):
    if not table_exists("cash_bank_accounts"):
        return []
    return rows(
        """
        SELECT id, account_name AS name
        FROM cash_bank_accounts
        WHERE company_id=%s AND branch_id=%s AND is_active=1
        ORDER BY account_name
        """,
        [company_id, branch_id],
    )


def get_filter_users(company_id):
    return lookup_users(company_id)


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
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00"}
    params = [company_id, branch_id, customer_id]
    opening = Decimal("0.00")
    if filters.get("date_from"):
        opening += money(scalar(
            """
            SELECT COALESCE(SUM(grand_total),0)
            FROM sales_invoices
            WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND status <> 'Cancelled' AND invoice_date < %s
            """,
            [company_id, branch_id, customer_id, filters["date_from"]],
        ))
        opening -= money(scalar(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM customer_receipts
            WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND receipt_date < %s
            """,
            [company_id, branch_id, customer_id, filters["date_from"]],
        ))
        opening -= money(scalar(
            """
            SELECT COALESCE(SUM(grand_total),0)
            FROM sales_returns
            WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND status <> 'Cancelled' AND return_date < %s
            """,
            [company_id, branch_id, customer_id, filters["date_from"]],
        ))
    date_clause_invoice, invoice_params = bounded_date_clause(filters, "invoice_date")
    date_clause_receipt, receipt_params = bounded_date_clause(filters, "cr.receipt_date")
    date_clause_return, return_params = bounded_date_clause(filters, "sr.return_date")
    data = rows(
        f"""
        SELECT invoice_date AS date, 'Invoice' AS type, invoice_no AS ref_no, invoice_no AS against_invoice, 'Sales invoice' AS description,
               grand_total AS debit, 0 AS credit
        FROM sales_invoices
        WHERE company_id=%s AND branch_id=%s AND customer_id=%s AND status <> 'Cancelled' {date_clause_invoice}
        UNION ALL
        SELECT cr.receipt_date AS date, 'Receipt' AS type, cr.receipt_no AS ref_no, si.invoice_no AS against_invoice, 'Customer receipt' AS description,
               0 AS debit, cr.amount AS credit
        FROM customer_receipts cr
        LEFT JOIN sales_invoices si ON si.id=cr.adjusted_invoice_id
        WHERE cr.company_id=%s AND cr.branch_id=%s AND cr.customer_id=%s {date_clause_receipt}
        UNION ALL
        SELECT sr.return_date AS date, 'Sales Return' AS type, sr.sales_return_no AS ref_no, si.invoice_no AS against_invoice, COALESCE(sr.return_reason, 'Sales return') AS description,
               0 AS debit, sr.grand_total AS credit
        FROM sales_returns sr
        LEFT JOIN sales_invoices si ON si.id=sr.sales_invoice_id
        WHERE sr.company_id=%s AND sr.branch_id=%s AND sr.customer_id=%s AND sr.status <> 'Cancelled' {date_clause_return}
        ORDER BY date, ref_no
        """,
        params + invoice_params + params + receipt_params + params + return_params,
    )
    running = opening
    for item in data:
        running += money(item.get("debit")) - money(item.get("credit"))
        item["balance"] = running
    invoice_summary = rows(
        """
        SELECT si.invoice_no, si.invoice_date, si.grand_total,
               COALESCE(si.received_amount,0) AS received,
               COALESCE(SUM(sr.grand_total),0) AS returns_credits,
               si.balance_amount AS balance,
               si.status
        FROM sales_invoices si
        LEFT JOIN sales_returns sr ON sr.sales_invoice_id=si.id AND sr.status <> 'Cancelled'
        WHERE si.company_id=%s AND si.branch_id=%s AND si.customer_id=%s AND si.status <> 'Cancelled'
        GROUP BY si.id, si.invoice_no, si.invoice_date, si.grand_total, si.received_amount, si.balance_amount, si.status
        ORDER BY si.invoice_date, si.invoice_no
        """,
        [company_id, branch_id, customer_id],
    )
    return data, {"Opening Balance": opening, "Closing Balance": running, "Invoice Summary Rows": len(invoice_summary)}


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
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00"}
    params = [company_id, branch_id, supplier_id]
    opening = Decimal("0.00")
    if filters.get("date_from"):
        opening += money(scalar(
            """
            SELECT COALESCE(SUM(grand_total),0)
            FROM supplier_purchases
            WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND status <> 'Cancelled' AND purchase_date < %s
            """,
            [company_id, branch_id, supplier_id, filters["date_from"]],
        ))
        opening -= money(scalar(
            """
            SELECT COALESCE(SUM(amount),0)
            FROM supplier_payments
            WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND payment_date < %s
            """,
            [company_id, branch_id, supplier_id, filters["date_from"]],
        ))
        opening -= money(scalar(
            """
            SELECT COALESCE(SUM(grand_total),0)
            FROM purchase_returns
            WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND status <> 'Cancelled' AND return_date < %s
            """,
            [company_id, branch_id, supplier_id, filters["date_from"]],
        ))
    purchase_clause, purchase_params = bounded_date_clause(filters, "purchase_date")
    payment_clause, payment_params = bounded_date_clause(filters, "pay.payment_date")
    return_clause, return_params = bounded_date_clause(filters, "pr.return_date")
    data = rows(
        f"""
        SELECT purchase_date AS date, 'Purchase' AS type, purchase_no AS ref_no, purchase_no AS against_purchase, supplier_bill_no, 'Supplier purchase' AS description,
               0 AS debit, grand_total AS credit
        FROM supplier_purchases
        WHERE company_id=%s AND branch_id=%s AND supplier_id=%s AND status <> 'Cancelled' {purchase_clause}
        UNION ALL
        SELECT pay.payment_date AS date, 'Payment' AS type, pay.payment_no AS ref_no, sp.purchase_no AS against_purchase, sp.supplier_bill_no, 'Supplier payment' AS description,
               pay.amount AS debit, 0 AS credit
        FROM supplier_payments pay
        LEFT JOIN supplier_purchases sp ON sp.id=pay.adjusted_purchase_id
        WHERE pay.company_id=%s AND pay.branch_id=%s AND pay.supplier_id=%s {payment_clause}
        UNION ALL
        SELECT pr.return_date AS date, 'Purchase Return' AS type, pr.purchase_return_no AS ref_no, sp.purchase_no AS against_purchase, sp.supplier_bill_no, COALESCE(pr.return_reason, 'Purchase return') AS description,
               pr.grand_total AS debit, 0 AS credit
        FROM purchase_returns pr
        LEFT JOIN supplier_purchases sp ON sp.id=pr.supplier_purchase_id
        WHERE pr.company_id=%s AND pr.branch_id=%s AND pr.supplier_id=%s AND pr.status <> 'Cancelled' {return_clause}
        ORDER BY date, ref_no
        """,
        params + purchase_params + params + payment_params + params + return_params,
    )
    running = opening
    for item in data:
        running += money(item.get("credit")) - money(item.get("debit"))
        item["balance"] = running
    purchase_summary = rows(
        """
        SELECT sp.purchase_no, sp.supplier_bill_no, sp.purchase_date, sp.grand_total,
               COALESCE(sp.paid_amount,0) AS paid,
               COALESCE(SUM(pr.grand_total),0) AS returns_debits,
               sp.balance_amount AS balance,
               sp.status
        FROM supplier_purchases sp
        LEFT JOIN purchase_returns pr ON pr.supplier_purchase_id=sp.id AND pr.status <> 'Cancelled'
        WHERE sp.company_id=%s AND sp.branch_id=%s AND sp.supplier_id=%s AND sp.status <> 'Cancelled'
        GROUP BY sp.id, sp.purchase_no, sp.supplier_bill_no, sp.purchase_date, sp.grand_total, sp.paid_amount, sp.balance_amount, sp.status
        ORDER BY sp.purchase_date, sp.purchase_no
        """,
        [company_id, branch_id, supplier_id],
    )
    return data, {"Opening Balance": opening, "Closing Balance": running, "Purchase Summary Rows": len(purchase_summary)}


def sales_invoice_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("status"):
        clauses.append("si.status=%s")
        params.append(filters["status"])
    if filters.get("invoice_type"):
        clauses.append("si.invoice_type=%s")
        params.append(filters["invoice_type"])
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


def item_sales_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("item_service_id"):
        clauses.append("sii.item_service_id=%s")
        params.append(filters["item_service_id"])
    if filters.get("customer_id"):
        clauses.append("si.customer_id=%s")
        params.append(filters["customer_id"])
    if filters.get("invoice_type"):
        clauses.append("si.invoice_type=%s")
        params.append(filters["invoice_type"])
    if filters.get("status"):
        clauses.append("si.status=%s")
        params.append(filters["status"])
    data = rows(
        f"""
        SELECT COALESCE(i.item_code, '-') AS item_code,
               COALESCE(i.item_name, sii.description) AS item_name,
               COALESCE(i.item_type, 'manual') AS item_type,
               SUM(COALESCE(sii.quantity,0)) AS qty_sold,
               SUM(COALESCE(sii.quantity,0) * COALESCE(sii.rate,0)) AS gross_amount,
               SUM(COALESCE(sii.discount_amount,0)) AS discount,
               SUM(COALESCE(sii.tax_amount,0)) AS tax,
               SUM(COALESCE(sii.line_total,0)) AS net_total
        FROM sales_invoice_items sii
        JOIN sales_invoices si ON si.id=sii.sales_invoice_id
        LEFT JOIN item_services i ON i.id=sii.item_service_id
        WHERE {' AND '.join(clauses)}
        GROUP BY sii.item_service_id, COALESCE(i.item_code, '-'), COALESCE(i.item_name, sii.description), COALESCE(i.item_type, 'manual')
        ORDER BY item_name
        """,
        params,
    )
    return data, totals(data, ["qty_sold", "gross_amount", "discount", "tax", "net_total"])


def item_purchase_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s", "sp.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "sp.purchase_date", params))
    if filters.get("item_service_id"):
        clauses.append("spi.item_service_id=%s")
        params.append(filters["item_service_id"])
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    if filters.get("status"):
        clauses.append("sp.status=%s")
        params.append(filters["status"])
    data = rows(
        f"""
        SELECT COALESCE(i.item_code, '-') AS item_code,
               COALESCE(i.item_name, spi.description) AS item_name,
               COALESCE(i.item_type, 'manual') AS item_type,
               SUM(COALESCE(spi.quantity,0)) AS qty_purchased,
               SUM(COALESCE(spi.quantity,0) * COALESCE(spi.purchase_rate,0)) AS purchase_amount,
               SUM(COALESCE(spi.tax_amount,0)) AS tax,
               SUM(COALESCE(spi.line_total,0)) AS net_total
        FROM supplier_purchase_items spi
        JOIN supplier_purchases sp ON sp.id=spi.supplier_purchase_id
        LEFT JOIN item_services i ON i.id=spi.item_service_id
        WHERE {' AND '.join(clauses)}
        GROUP BY spi.item_service_id, COALESCE(i.item_code, '-'), COALESCE(i.item_name, spi.description), COALESCE(i.item_type, 'manual')
        ORDER BY item_name
        """,
        params,
    )
    return data, totals(data, ["qty_purchased", "purchase_amount", "tax", "net_total"])


def item_profit_report(company_id, branch_id, filters):
    sales, _summary = item_sales_report(company_id, branch_id, filters)
    purchase, _purchase_summary = item_purchase_report(company_id, branch_id, filters)
    cost_by_item = {}
    for row_item in purchase:
        key = row_item.get("item_name")
        qty = money(row_item.get("qty_purchased"))
        cost = money(row_item.get("purchase_amount"))
        cost_by_item[key] = (cost / qty) if qty else Decimal("0.00")
    data = []
    for item in sales:
        qty = money(item.get("qty_sold"))
        sales_amount = money(item.get("net_total"))
        avg_cost = cost_by_item.get(item.get("item_name"), Decimal("0.00"))
        purchase_cost = (avg_cost * qty).quantize(Decimal("0.01"))
        profit = sales_amount - purchase_cost
        data.append(
            {
                "item": item.get("item_name"),
                "qty_sold": qty,
                "sales_amount": sales_amount,
                "purchase_cost": purchase_cost,
                "gross_profit": profit,
                "profit_percent": percent(profit, sales_amount),
                "cost_note": "Estimated average cost" if purchase_cost else "No purchase cost found",
            }
        )
    return data, totals(data, ["qty_sold", "sales_amount", "purchase_cost", "gross_profit"])


def item_history_report(company_id, branch_id, filters):
    item_id = filters.get("item_service_id")
    if not item_id:
        return [], {"Note": "Select an item/service to view transaction history. This is not a stock ledger."}
    date_clause_si, params_si = bounded_date_clause(filters, "si.invoice_date")
    date_clause_sr, params_sr = bounded_date_clause(filters, "sr.return_date")
    date_clause_sp, params_sp = bounded_date_clause(filters, "sp.purchase_date")
    date_clause_pr, params_pr = bounded_date_clause(filters, "pr.return_date")
    data = rows(
        f"""
        SELECT si.invoice_date AS date, 'Sales Invoice' AS type, si.invoice_no AS document_no,
               c.company_name AS party, 0 AS qty_in, sii.quantity AS qty_out, sii.rate AS rate, sii.line_total AS amount
        FROM sales_invoice_items sii
        JOIN sales_invoices si ON si.id=sii.sales_invoice_id
        LEFT JOIN customers c ON c.id=si.customer_id
        WHERE si.company_id=%s AND si.branch_id=%s AND si.status <> 'Cancelled' AND sii.item_service_id=%s {date_clause_si}
        UNION ALL
        SELECT sr.return_date AS date, 'Sales Return' AS type, sr.sales_return_no AS document_no,
               c.company_name AS party, sri.quantity AS qty_in, 0 AS qty_out, sri.rate AS rate, sri.line_total AS amount
        FROM sales_return_items sri
        JOIN sales_returns sr ON sr.id=sri.sales_return_id
        LEFT JOIN customers c ON c.id=sr.customer_id
        WHERE sr.company_id=%s AND sr.branch_id=%s AND sr.status <> 'Cancelled' AND sri.item_service_id=%s {date_clause_sr}
        UNION ALL
        SELECT sp.purchase_date AS date, 'Supplier Purchase' AS type, sp.purchase_no AS document_no,
               s.supplier_name AS party, spi.quantity AS qty_in, 0 AS qty_out, spi.purchase_rate AS rate, spi.line_total AS amount
        FROM supplier_purchase_items spi
        JOIN supplier_purchases sp ON sp.id=spi.supplier_purchase_id
        LEFT JOIN suppliers s ON s.id=sp.supplier_id
        WHERE sp.company_id=%s AND sp.branch_id=%s AND sp.status <> 'Cancelled' AND spi.item_service_id=%s {date_clause_sp}
        UNION ALL
        SELECT pr.return_date AS date, 'Purchase Return' AS type, pr.purchase_return_no AS document_no,
               s.supplier_name AS party, 0 AS qty_in, pri.quantity AS qty_out, pri.purchase_rate AS rate, pri.line_total AS amount
        FROM purchase_return_items pri
        JOIN purchase_returns pr ON pr.id=pri.purchase_return_id
        LEFT JOIN suppliers s ON s.id=pr.supplier_id
        WHERE pr.company_id=%s AND pr.branch_id=%s AND pr.status <> 'Cancelled' AND pri.item_service_id=%s {date_clause_pr}
        ORDER BY date, document_no
        """,
        [company_id, branch_id, item_id] + params_si
        + [company_id, branch_id, item_id] + params_sr
        + [company_id, branch_id, item_id] + params_sp
        + [company_id, branch_id, item_id] + params_pr,
    )
    return data, {"Qty In": sum(money(item.get("qty_in")) for item in data), "Qty Out": sum(money(item.get("qty_out")) for item in data), "Note": "No stock balance is shown because inventory tracking is not implemented."}


def service_sales_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'", "lower(COALESCE(i.item_type,''))='service'"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("item_service_id"):
        clauses.append("sii.item_service_id=%s")
        params.append(filters["item_service_id"])
    data = rows(
        f"""
        SELECT COALESCE(i.item_name, sii.description) AS service,
               SUM(COALESCE(sii.quantity,0)) AS qty_count,
               SUM((COALESCE(sii.quantity,0) * COALESCE(sii.rate,0)) - COALESCE(sii.discount_amount,0)) AS sales_amount,
               SUM(COALESCE(sii.tax_amount,0)) AS tax,
               SUM(COALESCE(sii.line_total,0)) AS net_total
        FROM sales_invoice_items sii
        JOIN sales_invoices si ON si.id=sii.sales_invoice_id
        LEFT JOIN item_services i ON i.id=sii.item_service_id
        WHERE {' AND '.join(clauses)}
        GROUP BY sii.item_service_id, COALESCE(i.item_name, sii.description)
        ORDER BY service
        """,
        params,
    )
    return data, totals(data, ["qty_count", "sales_amount", "tax", "net_total"])


def expense_report(company_id, branch_id, filters):
    if not table_exists("expense_vouchers"):
        return [], {"Note": "Expense voucher table is not available."}
    params = [company_id, branch_id]
    clauses = ["ev.company_id=%s", "ev.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "ev.voucher_date", params))
    if filters.get("expense_head_id"):
        clauses.append("ev.expense_head_id=%s")
        params.append(filters["expense_head_id"])
    if filters.get("cash_bank_account_id"):
        clauses.append("ev.cash_bank_account_id=%s")
        params.append(filters["cash_bank_account_id"])
    if filters.get("payment_mode"):
        clauses.append("ev.payment_mode=%s")
        params.append(filters["payment_mode"])
    if filters.get("status"):
        clauses.append("ev.status=%s")
        params.append(filters["status"])
    apply_search(clauses, params, filters.get("q"), ["ev.voucher_no", "eh.expense_name", "cb.account_name", "ev.cheque_reference_no", "ev.remarks"])
    data = rows(
        f"""
        SELECT ev.voucher_no, ev.voucher_date, eh.expense_name AS expense_head,
               cb.account_name AS cash_bank, ev.payment_mode, ev.amount, ev.tax_amount AS tax,
               ev.total_amount AS total, ev.status, ev.remarks
        FROM expense_vouchers ev
        JOIN expense_heads eh ON eh.id=ev.expense_head_id
        JOIN cash_bank_accounts cb ON cb.id=ev.cash_bank_account_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ev.voucher_date DESC, ev.id DESC
        """,
        params,
    )
    return data, {"Total Expense": sum(money(item.get("amount")) for item in data), "Total Tax": sum(money(item.get("tax")) for item in data), "Grand Total": sum(money(item.get("total")) for item in data)}


def income_report(company_id, branch_id, filters):
    data, summary = sales_invoice_report(company_id, branch_id, filters)
    for item in data:
        item["subtotal"] = item.get("subtotal") or scalar("SELECT subtotal FROM sales_invoices WHERE invoice_no=%s AND company_id=%s AND branch_id=%s", [item.get("invoice_no"), company_id, branch_id])
        item["discount_total"] = item.get("discount_total") or scalar("SELECT discount_total FROM sales_invoices WHERE invoice_no=%s AND company_id=%s AND branch_id=%s", [item.get("invoice_no"), company_id, branch_id])
        item["tax_total"] = item.get("tax_total") or scalar("SELECT tax_total FROM sales_invoices WHERE invoice_no=%s AND company_id=%s AND branch_id=%s", [item.get("invoice_no"), company_id, branch_id])
    return data, totals(data, ["subtotal", "discount_total", "tax_total", "grand_total"])


def tax_summary_report(company_id, branch_id, filters):
    sales_tax = tax_scalar("sales_invoices", "invoice_date", "tax_total", company_id, branch_id, filters, "status <> 'Cancelled'")
    sales_return_tax = tax_scalar("sales_returns", "return_date", "tax_total", company_id, branch_id, filters, "status <> 'Cancelled'")
    purchase_tax = tax_scalar("supplier_purchases", "purchase_date", "tax_total", company_id, branch_id, filters, "status <> 'Cancelled'")
    purchase_return_tax = tax_scalar("purchase_returns", "return_date", "tax_total", company_id, branch_id, filters, "status <> 'Cancelled'")
    expense_tax = tax_scalar("expense_vouchers", "voucher_date", "tax_amount", company_id, branch_id, filters, "status <> 'Cancelled'") if table_exists("expense_vouchers") else Decimal("0.00")
    net_output = sales_tax - sales_return_tax
    net_input = purchase_tax - purchase_return_tax + expense_tax
    net = net_output - net_input
    data = [
        {"section": "Output Tax from Sales", "amount": sales_tax},
        {"section": "Less Sales Return Tax", "amount": sales_return_tax},
        {"section": "Net Output Tax", "amount": net_output},
        {"section": "Input Tax from Purchases", "amount": purchase_tax},
        {"section": "Less Purchase Return Tax", "amount": purchase_return_tax},
        {"section": "Input Tax from Expenses", "amount": expense_tax},
        {"section": "Net Input Tax", "amount": net_input},
        {"section": "Net Tax Payable / (Receivable)", "amount": net},
    ]
    return data, {"Net Output Tax": net_output, "Net Input Tax": net_input, "Net Tax Payable / (Receivable)": net}


def account_ledger_report(company_id, branch_id, filters):
    account_id = filters.get("account_id")
    if not account_id:
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00", "Note": "Select an account to view the ledger."}
    account = row("SELECT account_name FROM accounts WHERE company_id=%s AND (branch_id=%s OR branch_id IS NULL) AND id=%s", [company_id, branch_id, account_id])
    if not account:
        return [], {"Opening Balance": "0.00", "Closing Balance": "0.00"}
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
        item["account"] = account.get("account_name")
        running += money(item.get("debit")) - money(item.get("credit"))
        item["balance"] = running
    return data, {"Opening Balance": opening, "Closing Balance": running}


def user_activity_report(company_id, branch_id, filters, action_filter=None):
    params = [company_id, branch_id]
    clauses = ["ual.company_id=%s", "(ual.branch_id=%s OR ual.branch_id IS NULL)"]
    clauses.extend(date_filters_from_values(filters, "substr(ual.activity_datetime,1,10)", params))
    if filters.get("user_id"):
        clauses.append("ual.user_id=%s")
        params.append(filters["user_id"])
    if action_filter:
        values = action_filter if isinstance(action_filter, (list, tuple)) else [action_filter]
        clauses.append("(" + " OR ".join(["lower(ual.action_type)=lower(%s)" for _ in values]) + ")")
        params.extend(values)
    elif filters.get("action"):
        clauses.append("ual.action_type LIKE %s")
        params.append(f"%{filters['action']}%")
    if filters.get("module"):
        clauses.append("ual.module_name LIKE %s")
        params.append(f"%{filters['module']}%")
    apply_search(clauses, params, filters.get("q"), ["ual.description", "ual.table_name", "ual.module_name", "ual.action_type", "u.username", "u.full_name"])
    data = rows(
        f"""
        SELECT ual.activity_datetime AS datetime, COALESCE(u.full_name, u.username, '-') AS user,
               ual.action_type AS action, ual.module_name AS module, ual.table_name AS record_type,
               ual.record_id, ual.description,
               CASE WHEN instr(COALESCE(ual.description,''), 'ip=') > 0 THEN substr(ual.description, instr(ual.description, 'ip=') + 3) ELSE '' END AS ip
        FROM user_activity_log ual
        LEFT JOIN users u ON u.id=ual.user_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ual.activity_datetime DESC, ual.id DESC
        """,
        params,
    )
    return data, {"Rows": len(data)}


def login_logout_report(company_id, branch_id, filters):
    return user_activity_report(company_id, branch_id, filters, ["login", "logout", "LOGIN", "LOGOUT"])


def print_report(company_id, branch_id, filters):
    return user_activity_report(company_id, branch_id, filters, ["print", "PRINT"])


def export_report(company_id, branch_id, filters):
    return user_activity_report(company_id, branch_id, filters, ["export", "EXPORT", "REPORT_EXPORT"])


def backup_restore_report(company_id, branch_id, filters):
    return user_activity_report(company_id, branch_id, filters, ["backup", "restore", "BACKUP", "RESTORE"])


def validation_failure_report(company_id, branch_id, filters):
    data, summary = user_activity_report(company_id, branch_id, filters, ["validation_failure", "VALIDATION_FAILURE"])
    if not data:
        return [{"datetime": "", "user": "", "action": "", "module": "", "record_type": "", "record_id": "", "description": "No validation failures logged yet.", "ip": ""}], summary
    return data, summary


def customer_sales_summary(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    if filters.get("customer_id"):
        clauses.append("si.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["c.company_name"])
    data = rows(
        f"""
        SELECT c.company_name AS customer, COUNT(si.id) AS invoice_count,
               SUM(COALESCE(si.grand_total,0)) AS sales_total,
               SUM(COALESCE(si.tax_total,0)) AS tax_total,
               SUM(COALESCE(si.received_amount,0)) AS received,
               SUM(COALESCE(si.balance_amount,0)) AS balance
        FROM sales_invoices si
        JOIN customers c ON c.id=si.customer_id
        WHERE {' AND '.join(clauses)}
        GROUP BY c.id, c.company_name
        ORDER BY c.company_name
        """,
        params,
    )
    return data, totals(data, ["invoice_count", "sales_total", "tax_total", "received", "balance"])


def customer_receipts_summary(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["cr.company_id=%s", "cr.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "cr.receipt_date", params))
    if filters.get("customer_id"):
        clauses.append("cr.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["c.company_name", "cr.receipt_no"])
    data = rows(
        f"""
        SELECT c.company_name AS customer, COUNT(cr.id) AS receipt_count,
               SUM(COALESCE(cr.amount,0)) AS total_received
        FROM customer_receipts cr
        JOIN customers c ON c.id=cr.customer_id
        WHERE {' AND '.join(clauses)}
        GROUP BY c.id, c.company_name
        ORDER BY c.company_name
        """,
        params,
    )
    return data, totals(data, ["receipt_count", "total_received"])


def supplier_purchase_summary(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s", "sp.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "sp.purchase_date", params))
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["s.supplier_name"])
    data = rows(
        f"""
        SELECT s.supplier_name AS supplier, COUNT(sp.id) AS purchase_count,
               SUM(COALESCE(sp.grand_total,0)) AS purchase_total,
               SUM(COALESCE(sp.tax_total,0)) AS tax_total,
               SUM(COALESCE(sp.paid_amount,0)) AS paid,
               SUM(COALESCE(sp.balance_amount,0)) AS balance
        FROM supplier_purchases sp
        JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(clauses)}
        GROUP BY s.id, s.supplier_name
        ORDER BY s.supplier_name
        """,
        params,
    )
    return data, totals(data, ["purchase_count", "purchase_total", "tax_total", "paid", "balance"])


def supplier_payment_summary(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sp.company_id=%s", "sp.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sp.payment_date", params))
    if filters.get("supplier_id"):
        clauses.append("sp.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["s.supplier_name", "sp.payment_no"])
    data = rows(
        f"""
        SELECT s.supplier_name AS supplier, COUNT(sp.id) AS payment_count,
               SUM(COALESCE(sp.amount,0)) AS total_paid
        FROM supplier_payments sp
        JOIN suppliers s ON s.id=sp.supplier_id
        WHERE {' AND '.join(clauses)}
        GROUP BY s.id, s.supplier_name
        ORDER BY s.supplier_name
        """,
        params,
    )
    return data, totals(data, ["payment_count", "total_paid"])


def quotation_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["q.company_id=%s", "q.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "q.quotation_date", params))
    if filters.get("status"):
        clauses.append("q.status=%s")
        params.append(filters["status"])
    if filters.get("customer_id"):
        clauses.append("q.customer_id=%s")
        params.append(filters["customer_id"])
    party = quotation_party_expr()
    apply_search(clauses, params, filters.get("q"), ["q.quotation_no", party, "q.subject"])
    data = rows(
        f"""
        SELECT q.quotation_no, q.quotation_date AS date, {party} AS customer_party,
               q.subject, q.valid_till, q.grand_total, q.status
        FROM quotations q
        LEFT JOIN customers c ON c.id=q.customer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY q.quotation_date DESC, q.id DESC
        """,
        params,
    )
    return data, totals(data, ["grand_total"])


def confirmation_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["cc.company_id=%s", "cc.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "cc.confirmation_date", params))
    if filters.get("status"):
        clauses.append("cc.status=%s")
        params.append(filters["status"])
    party = "COALESCE(c.company_name, q.customer_name, '')" if column_exists("quotations", "customer_name") else "COALESCE(c.company_name, '')"
    apply_search(clauses, params, filters.get("q"), ["cc.confirmation_no", party, "cc.po_number", "cc.confirmation_note"])
    data = rows(
        f"""
        SELECT cc.confirmation_no, cc.confirmation_date AS date, {party} AS customer_party,
               cc.confirmation_type AS type, cc.po_number, cc.total_amount AS total, cc.status
        FROM customer_confirmations cc
        LEFT JOIN customers c ON c.id=cc.customer_id
        LEFT JOIN quotations q ON q.id=cc.quotation_id
        WHERE {' AND '.join(clauses)}
        ORDER BY cc.confirmation_date DESC, cc.id DESC
        """,
        params,
    )
    return data, totals(data, ["total"])


def delivery_challan_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["dc.company_id=%s", "dc.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "dc.dc_date", params))
    if filters.get("status"):
        clauses.append("dc.status=%s")
        params.append(filters["status"])
    party = "COALESCE(c.company_name, q.customer_name, '')" if column_exists("quotations", "customer_name") else "COALESCE(c.company_name, '')"
    apply_search(clauses, params, filters.get("q"), ["dc.dc_no", party, "dc.po_number", "dc.delivered_by", "dc.received_by"])
    data = rows(
        f"""
        SELECT dc.dc_no, dc.dc_date AS date, {party} AS customer_party, dc.po_number,
               dc.delivered_by, dc.received_by, dc.signed_copy_path AS signed_copy, dc.status
        FROM delivery_challans dc
        LEFT JOIN customers c ON c.id=dc.customer_id
        LEFT JOIN quotations q ON q.id=dc.quotation_id
        WHERE {' AND '.join(clauses)}
        ORDER BY dc.dc_date DESC, dc.id DESC
        """,
        params,
    )
    return data, {"Rows": len(data)}


def sales_return_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["sr.company_id=%s", "sr.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sr.return_date", params))
    if filters.get("status"):
        clauses.append("sr.status=%s")
        params.append(filters["status"])
    if filters.get("customer_id"):
        clauses.append("sr.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["sr.sales_return_no", "c.company_name", "si.invoice_no", "sr.return_reason"])
    data = rows(
        f"""
        SELECT sr.sales_return_no AS return_no, sr.return_date AS date, c.company_name AS customer,
               si.invoice_no, sr.grand_total, sr.refund_amount, sr.status
        FROM sales_returns sr
        JOIN customers c ON c.id=sr.customer_id
        LEFT JOIN sales_invoices si ON si.id=sr.sales_invoice_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sr.return_date DESC, sr.id DESC
        """,
        params,
    )
    return data, totals(data, ["grand_total", "refund_amount"])


def sales_tax_report(company_id, branch_id, filters):
    date_clause_i, params_i = bounded_date_clause(filters, "invoice_date")
    date_clause_r, params_r = bounded_date_clause(filters, "return_date")
    data = rows(
        f"""
        SELECT si.invoice_date AS date, 'Invoice' AS type, si.invoice_no AS ref_no,
               c.company_name AS customer, (COALESCE(si.subtotal,0)-COALESCE(si.discount_total,0)) AS taxable_amount,
               si.tax_total AS output_tax, si.status
        FROM sales_invoices si
        JOIN customers c ON c.id=si.customer_id
        WHERE si.company_id=%s AND si.branch_id=%s AND si.status <> 'Cancelled' {date_clause_i}
        UNION ALL
        SELECT sr.return_date AS date, 'Sales Return' AS type, sr.sales_return_no AS ref_no,
               c.company_name AS customer, (COALESCE(sr.subtotal,0)-COALESCE(sr.discount_total,0)) * -1 AS taxable_amount,
               COALESCE(sr.tax_total,0) * -1 AS output_tax, sr.status
        FROM sales_returns sr
        JOIN customers c ON c.id=sr.customer_id
        WHERE sr.company_id=%s AND sr.branch_id=%s AND sr.status <> 'Cancelled' {date_clause_r}
        ORDER BY date DESC, ref_no DESC
        """,
        [company_id, branch_id] + params_i + [company_id, branch_id] + params_r,
    )
    return data, totals(data, ["taxable_amount", "output_tax"])


def purchase_return_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["pr.company_id=%s", "pr.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "pr.return_date", params))
    if filters.get("status"):
        clauses.append("pr.status=%s")
        params.append(filters["status"])
    if filters.get("supplier_id"):
        clauses.append("pr.supplier_id=%s")
        params.append(filters["supplier_id"])
    apply_search(clauses, params, filters.get("q"), ["pr.purchase_return_no", "s.supplier_name", "sp.purchase_no", "sp.supplier_bill_no", "pr.return_reason"])
    data = rows(
        f"""
        SELECT pr.purchase_return_no AS return_no, pr.return_date AS date, s.supplier_name AS supplier,
               sp.purchase_no, sp.supplier_bill_no, pr.grand_total, pr.refund_amount, pr.status
        FROM purchase_returns pr
        JOIN suppliers s ON s.id=pr.supplier_id
        LEFT JOIN supplier_purchases sp ON sp.id=pr.supplier_purchase_id
        WHERE {' AND '.join(clauses)}
        ORDER BY pr.return_date DESC, pr.id DESC
        """,
        params,
    )
    return data, totals(data, ["grand_total", "refund_amount"])


def purchase_tax_report(company_id, branch_id, filters):
    date_clause_p, params_p = bounded_date_clause(filters, "purchase_date")
    date_clause_r, params_r = bounded_date_clause(filters, "return_date")
    data = rows(
        f"""
        SELECT sp.purchase_date AS date, 'Purchase' AS type, sp.purchase_no AS ref_no,
               s.supplier_name AS supplier, sp.subtotal AS taxable_amount,
               sp.tax_total AS input_tax, sp.status
        FROM supplier_purchases sp
        JOIN suppliers s ON s.id=sp.supplier_id
        WHERE sp.company_id=%s AND sp.branch_id=%s AND sp.status <> 'Cancelled' {date_clause_p}
        UNION ALL
        SELECT pr.return_date AS date, 'Purchase Return' AS type, pr.purchase_return_no AS ref_no,
               s.supplier_name AS supplier, COALESCE(pr.subtotal,0) * -1 AS taxable_amount,
               COALESCE(pr.tax_total,0) * -1 AS input_tax, pr.status
        FROM purchase_returns pr
        JOIN suppliers s ON s.id=pr.supplier_id
        WHERE pr.company_id=%s AND pr.branch_id=%s AND pr.status <> 'Cancelled' {date_clause_r}
        ORDER BY date DESC, ref_no DESC
        """,
        [company_id, branch_id] + params_p + [company_id, branch_id] + params_r,
    )
    return data, totals(data, ["taxable_amount", "input_tax"])


def profit_by_invoice_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["si.company_id=%s", "si.branch_id=%s", "si.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    data = rows(
        f"""
        SELECT si.invoice_no, si.invoice_date AS date, c.company_name AS customer,
               COALESCE(si.grand_total,0) AS sales_total,
               COALESCE((SELECT SUM(grand_total) FROM supplier_purchases sp WHERE sp.confirmation_id=si.confirmation_id AND sp.status <> 'Cancelled'),0) AS purchase_cost,
               COALESCE(si.grand_total,0) - COALESCE((SELECT SUM(grand_total) FROM supplier_purchases sp WHERE sp.confirmation_id=si.confirmation_id AND sp.status <> 'Cancelled'),0) AS gross_profit,
               0 AS profit_percent
        FROM sales_invoices si
        JOIN customers c ON c.id=si.customer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY si.invoice_date DESC, si.id DESC
        """,
        params,
    )
    for item in data:
        item["profit_percent"] = percent(item.get("gross_profit"), item.get("sales_total"))
    return data, totals(data, ["sales_total", "purchase_cost", "gross_profit"])


def profit_by_confirmation_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["cc.company_id=%s", "cc.branch_id=%s", "cc.status <> 'Cancelled'"]
    clauses.extend(date_filters_from_values(filters, "cc.confirmation_date", params))
    party = "COALESCE(c.company_name, q.customer_name, '')" if column_exists("quotations", "customer_name") else "COALESCE(c.company_name, '')"
    data = rows(
        f"""
        SELECT cc.confirmation_no, {party} AS customer_party, cc.po_number,
               COALESCE((SELECT SUM(grand_total) FROM sales_invoices si WHERE si.confirmation_id=cc.id AND si.status <> 'Cancelled'),0) AS sales_total,
               COALESCE((SELECT SUM(grand_total) FROM supplier_purchases sp WHERE sp.confirmation_id=cc.id AND sp.status <> 'Cancelled'),0) AS purchase_cost,
               0 AS gross_profit, 0 AS profit_percent
        FROM customer_confirmations cc
        LEFT JOIN customers c ON c.id=cc.customer_id
        LEFT JOIN quotations q ON q.id=cc.quotation_id
        WHERE {' AND '.join(clauses)}
        ORDER BY cc.confirmation_date DESC, cc.id DESC
        """,
        params,
    )
    for item in data:
        item["gross_profit"] = money(item.get("sales_total")) - money(item.get("purchase_cost"))
        item["profit_percent"] = percent(item.get("gross_profit"), item.get("sales_total"))
    return data, totals(data, ["sales_total", "purchase_cost", "gross_profit"])


def service_contract_report(company_id, branch_id, filters):
    if not table_exists("service_contracts"):
        return [], {"Note": "Service contracts table is not available."}
    params = [company_id, branch_id]
    clauses = ["sc.company_id=%s", "sc.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sc.start_date", params))
    if filters.get("status"):
        clauses.append("sc.status=%s")
        params.append(filters["status"])
    if filters.get("customer_id"):
        clauses.append("sc.customer_id=%s")
        params.append(filters["customer_id"])
    apply_search(clauses, params, filters.get("q"), ["sc.contract_no", "c.company_name", "sc.service_type"])
    data = rows(
        f"""
        SELECT sc.contract_no, c.company_name AS customer, sc.service_type,
               sc.start_date AS start, sc.end_date AS end, sc.billing_cycle AS cycle,
               sc.contract_amount AS amount, sc.next_billing_date AS next_billing, sc.status
        FROM service_contracts sc
        JOIN customers c ON c.id=sc.customer_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sc.start_date DESC, sc.id DESC
        """,
        params,
    )
    return data, totals(data, ["amount"])


def service_expiring_report(company_id, branch_id, filters):
    data, summary = service_contract_report(company_id, branch_id, {**filters, "status": filters.get("status") or "Active"})
    today = date.today()
    limit = parse_date(filters.get("date_to")) or date.fromordinal(today.toordinal() + 30)
    data = [item for item in data if parse_date(item.get("end")) and today <= parse_date(item.get("end")) <= limit]
    return data, {**summary, "Rows": len(data)}


def service_billing_due_report(company_id, branch_id, filters):
    data, summary = service_contract_report(company_id, branch_id, {**filters, "status": filters.get("status") or "Active"})
    limit = parse_date(filters.get("date_to")) or date.today()
    data = [item for item in data if parse_date(item.get("next_billing")) and parse_date(item.get("next_billing")) <= limit]
    return data, {**summary, "Rows": len(data)}


def service_invoice_history_report(company_id, branch_id, filters):
    if not table_exists("service_contracts"):
        return [], {"Note": "Service contracts table is not available."}
    params = [company_id, branch_id]
    clauses = ["sc.company_id=%s", "sc.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "si.invoice_date", params))
    data = rows(
        f"""
        SELECT sc.contract_no, c.company_name AS customer, si.invoice_no,
               si.invoice_date, si.grand_total AS amount, si.status
        FROM service_contracts sc
        JOIN customers c ON c.id=sc.customer_id
        LEFT JOIN sales_invoices si ON si.customer_id=sc.customer_id
             AND (si.remarks LIKE '%' || sc.contract_no || '%' OR si.remarks LIKE '%' || sc.service_type || '%')
        WHERE {' AND '.join(clauses)}
        ORDER BY si.invoice_date DESC, sc.contract_no
        """,
        params,
    )
    return data, totals(data, ["amount"])


def journal_report(company_id, branch_id, filters):
    params = [company_id, branch_id]
    clauses = ["je.company_id=%s", "je.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "je.entry_date", params))
    apply_search(clauses, params, filters.get("q"), ["je.entry_no", "je.reference_type", "je.description"])
    data = rows(
        f"""
        SELECT je.entry_date AS date, je.entry_no, je.reference_type, je.description,
               SUM(COALESCE(jel.debit,0)) AS debit, SUM(COALESCE(jel.credit,0)) AS credit
        FROM journal_entries je
        JOIN journal_entry_lines jel ON jel.journal_entry_id=je.id
        WHERE {' AND '.join(clauses)}
        GROUP BY je.id, je.entry_date, je.entry_no, je.reference_type, je.description
        ORDER BY je.entry_date DESC, je.id DESC
        """,
        params,
    )
    return data, totals(data, ["debit", "credit"])


def inventory_stock_balance_report(company_id, branch_id, filters):
    if not table_exists("stock_movements"):
        return [], {"Note": "Inventory tables are not available."}
    params = [company_id, branch_id]
    clauses = ["sm.company_id=%s", "sm.branch_id=%s"]
    if filters.get("item_service_id"):
        clauses.append("sm.item_service_id=%s")
        params.append(filters["item_service_id"])
    data = rows(
        f"""
        SELECT i.item_code, i.item_name, COALESCE(i.unit,'') AS unit,
               SUM(COALESCE(sm.quantity_in,0)) AS qty_in,
               SUM(COALESCE(sm.quantity_out,0)) AS qty_out,
               SUM(COALESCE(sm.quantity_in,0) - COALESCE(sm.quantity_out,0)) AS available_qty,
               COALESCE(NULLIF(i.default_purchase_rate,0), i.opening_cost, 0) AS average_cost,
               SUM(COALESCE(sm.quantity_in,0) - COALESCE(sm.quantity_out,0)) * COALESCE(NULLIF(i.default_purchase_rate,0), i.opening_cost, 0) AS stock_value,
               COALESCE(i.minimum_stock_level,0) AS minimum_level,
               CASE WHEN SUM(COALESCE(sm.quantity_in,0) - COALESCE(sm.quantity_out,0)) <= COALESCE(i.minimum_stock_level,0) THEN 'Low' ELSE 'OK' END AS status
        FROM stock_movements sm
        JOIN item_services i ON i.id=sm.item_service_id
        WHERE {' AND '.join(clauses)}
        GROUP BY i.id, i.item_code, i.item_name, i.unit, i.default_purchase_rate, i.opening_cost, i.minimum_stock_level
        ORDER BY i.item_name
        """,
        params,
    )
    if filters.get("status") == "low":
        data = [item for item in data if item.get("status") == "Low"]
    return data, totals(data, ["qty_in", "qty_out", "available_qty", "stock_value"])


def inventory_item_ledger_report(company_id, branch_id, filters):
    if not table_exists("stock_movements"):
        return [], {"Note": "Inventory tables are not available."}
    params = [company_id, branch_id]
    clauses = ["sm.company_id=%s", "sm.branch_id=%s"]
    clauses.extend(date_filters_from_values(filters, "sm.movement_date", params))
    if filters.get("item_service_id"):
        clauses.append("sm.item_service_id=%s")
        params.append(filters["item_service_id"])
    data = rows(
        f"""
        SELECT sm.movement_date AS date, sm.movement_type AS type, sm.source_no,
               '' AS party, sm.quantity_in AS qty_in, sm.quantity_out AS qty_out,
               0 AS balance, sm.unit_cost, sm.remarks
        FROM stock_movements sm
        WHERE {' AND '.join(clauses)}
        ORDER BY sm.movement_date, sm.id
        """,
        params,
    )
    running = Decimal("0.00")
    for item in data:
        running += money(item.get("qty_in")) - money(item.get("qty_out"))
        item["balance"] = running
    return data, {"Closing Balance": running}


def inventory_stock_flow_report(company_id, branch_id, filters, direction):
    if not table_exists("stock_movements"):
        return [], {"Note": "Inventory tables are not available."}
    field = "quantity_in" if direction == "in" else "quantity_out"
    params = [company_id, branch_id]
    clauses = ["sm.company_id=%s", "sm.branch_id=%s", f"COALESCE(sm.{field},0) > 0"]
    clauses.extend(date_filters_from_values(filters, "sm.movement_date", params))
    data = rows(
        f"""
        SELECT sm.movement_date AS date, sm.movement_type AS type, sm.source_no,
               i.item_code, i.item_name, sm.quantity_in AS qty_in, sm.quantity_out AS qty_out,
               sm.unit_cost, sm.remarks
        FROM stock_movements sm
        JOIN item_services i ON i.id=sm.item_service_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sm.movement_date DESC, sm.id DESC
        """,
        params,
    )
    return data, totals(data, ["qty_in", "qty_out"])


def tax_scalar(table, date_column, amount_column, company_id, branch_id, filters, extra_clause):
    if not table_exists(table):
        return Decimal("0.00")
    params = [company_id, branch_id]
    clauses = ["company_id=%s", "branch_id=%s", extra_clause]
    clauses.extend(date_filters_from_values(filters, date_column, params))
    return money(scalar(f"SELECT COALESCE(SUM({amount_column}),0) FROM {table} WHERE {' AND '.join(clauses)}", params))


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
