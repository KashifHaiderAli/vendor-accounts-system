from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError, connection
from django.shortcuts import redirect, render

from authentication.auth_utils import dictfetchall, dictfetchone, user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from masters.master_utils import paginate
from settings_module.services import log_user_activity

from . import expense_services
from .accounting_engine import AccountingError
from .accounting_utils import (
    account_types,
    get_current_branch_id,
    get_current_company_id,
    list_chart_accounts,
)


@permission_required_custom("accounting_reports", "view")
def index(request):
    return redirect("accounts_module:chart")


@login_required_custom
def chart_of_accounts(request):
    if not can_view_accounting(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    search = request.GET.get("q", "").strip()
    account_type = request.GET.get("account_type", "").strip()
    status = request.GET.get("status", "active").strip()
    page = safe_page(request.GET.get("page"))
    per_page = 20
    rows, total = list_chart_accounts(
        company_id,
        branch_id,
        search,
        account_type,
        status,
        per_page,
        (max(page, 1) - 1) * per_page,
    )
    page_data = paginate(total, page)
    if page_data["offset"] != (max(page, 1) - 1) * per_page:
        rows, total = list_chart_accounts(
            company_id,
            branch_id,
            search,
            account_type,
            status,
            page_data["per_page"],
            page_data["offset"],
        )
    return render(
        request,
        "accounts_module/chart_of_accounts.html",
        {
            "page_title": "Chart of Accounts",
            "rows": rows,
            "search": search,
            "account_type": account_type,
            "status": status,
            "account_types": account_types(company_id, branch_id),
            "pagination": page_data,
        },
    )


@login_required_custom
def journal_list(request):
    if not can_view_accounting(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    filters = {
        "q": request.GET.get("q", "").strip(),
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "reference_type": request.GET.get("reference_type", "").strip(),
    }
    page = safe_page(request.GET.get("page"))
    rows, total = list_journals(company_id, branch_id, filters, page)
    return render(
        request,
        "accounts_module/journal_list.html",
        {
            "page_title": "Journal Entries",
            "rows": rows,
            "filters": filters,
            "pagination": paginate(total, page),
        },
    )


@login_required_custom
def journal_detail(request, journal_id):
    if not can_view_accounting(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    journal = get_journal(company_id, branch_id, journal_id)
    if not journal:
        messages.error(request, "Journal entry was not found.")
        return redirect("accounts_module:journals")
    lines = get_journal_lines(journal_id)
    total_debit = sum(line["debit"] or 0 for line in lines)
    total_credit = sum(line["credit"] or 0 for line in lines)
    return render(
        request,
        "accounts_module/journal_detail.html",
        {
            "page_title": journal["entry_no"],
            "journal": journal,
            "lines": lines,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "is_balanced": total_debit == total_credit,
        },
    )


@login_required_custom
def expense_vouchers_list(request):
    if not can_manage_expenses(request, "view"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    if not expense_services.table_exists():
        messages.warning(request, "Expense voucher table is missing. Run: python manage.py upgrade_schema_expense_vouchers")
    filters = {
        "q": request.GET.get("q", "").strip(),
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "expense_head": request.GET.get("expense_head", "").strip(),
        "payment_mode": request.GET.get("payment_mode", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }
    page = safe_page(request.GET.get("page"))
    rows, total = expense_services.list_vouchers(company_id, branch_id, filters, page)
    return render(request, "accounts_module/expense_vouchers_list.html", {"page_title": "Expense Vouchers", "rows": rows, "filters": filters, "pagination": paginate(total, page), "expense_heads": expense_services.get_expense_heads(company_id, branch_id), "payment_modes": expense_services.PAYMENT_MODES, "statuses": expense_services.STATUSES, "can_add": can_manage_expenses(request, "add"), "can_edit": can_manage_expenses(request, "edit"), "can_cancel": can_cancel_expense(request), "table_exists": expense_services.table_exists()})


@login_required_custom
def expense_voucher_form(request, voucher_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = voucher_id is not None
    if not can_manage_expenses(request, "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    if not expense_services.table_exists():
        messages.error(request, "Expense voucher table is missing. Run: python manage.py upgrade_schema_expense_vouchers")
        return redirect("accounts_module:expenses")
    voucher = expense_services.get_voucher(company_id, branch_id, voucher_id) if is_edit else None
    if is_edit and not voucher:
        messages.error(request, "Expense voucher was not found.")
        return redirect("accounts_module:expenses")
    if is_edit and voucher.get("status") == "Cancelled":
        messages.error(request, "Cancelled expense vouchers cannot be edited.")
        return redirect("accounts_module:expense_detail", voucher_id=voucher_id)
    posted = bool(voucher and voucher.get("journal_entry_id"))
    form_data = expense_form_data(voucher) if is_edit else expense_services.default_form_data(company_id, branch_id)
    errors = {}
    if request.method == "POST":
        if posted:
            form_data.update({"cheque_reference_no": request.POST.get("cheque_reference_no", ""), "remarks": request.POST.get("remarks", "")})
            from core import validators
            form_data["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(form_data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
            form_data["remarks"], errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {k: v for k, v in errors.items() if v}
            if not errors:
                expense_services.save_voucher(company_id, branch_id, request.session.get("user_id"), form_data, voucher_id)
                log_user_activity(request, "UPDATE", "Expense Vouchers", "expense_vouchers", voucher_id, f"Updated non-financial details for expense voucher {voucher['voucher_no']}.")
                messages.success(request, "Expense voucher updated successfully.")
                return redirect("accounts_module:expense_detail", voucher_id=voucher_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = expense_services.parse_post(request.POST)
            errors, form_data = expense_services.validate_and_calculate(form_data, company_id, branch_id, voucher_id)
            if not errors:
                try:
                    saved_id = expense_services.save_voucher(company_id, branch_id, request.session.get("user_id"), form_data, voucher_id)
                    log_user_activity(request, "CREATE", "Expense Vouchers", "expense_vouchers", saved_id, f"Created expense voucher {form_data['voucher_no']}.")
                    messages.success(request, "Expense voucher created and posted successfully.")
                    return redirect("accounts_module:expense_detail", voucher_id=saved_id)
                except (AccountingError, ValueError) as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save expense voucher. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")
    return render(request, "accounts_module/expense_voucher_form.html", {"page_title": "Edit Expense Voucher" if is_edit else "New Expense Voucher", "form_data": form_data, "errors": errors, "error_summary": [str(v) for v in errors.values() if v], "is_edit": is_edit, "posted": posted, "expense_heads": expense_services.get_expense_heads(company_id, branch_id), "cash_bank_accounts": expense_services.get_cash_bank_accounts(company_id, branch_id), "payment_modes": expense_services.PAYMENT_MODES})


@login_required_custom
def expense_voucher_detail(request, voucher_id):
    if not can_manage_expenses(request, "view"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    voucher = expense_services.get_voucher(company_id, branch_id, voucher_id)
    if not voucher:
        messages.error(request, "Expense voucher was not found.")
        return redirect("accounts_module:expenses")
    return render(request, "accounts_module/expense_voucher_detail.html", {"page_title": voucher["voucher_no"], "voucher": voucher, "can_edit": can_manage_expenses(request, "edit") and voucher.get("status") != "Cancelled", "can_cancel": can_cancel_expense(request) and voucher.get("status") != "Cancelled"})


@login_required_custom
def cancel_expense_voucher(request, voucher_id):
    if not can_cancel_expense(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    voucher = expense_services.get_voucher(company_id, branch_id, voucher_id)
    if not voucher:
        messages.error(request, "Expense voucher was not found.")
        return redirect("accounts_module:expenses")
    if request.method == "POST":
        try:
            expense_services.cancel_voucher(request, voucher)
            messages.success(request, "Expense voucher cancelled and reversal journal created successfully.")
            return redirect("accounts_module:expense_detail", voucher_id=voucher_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel expense voucher.")
            return redirect("accounts_module:expense_detail", voucher_id=voucher_id)
    return render(request, "accounts_module/confirm_cancel_expense_voucher.html", {"page_title": "Cancel Expense Voucher", "voucher": voucher})


@login_required_custom
def print_expense_voucher(request, voucher_id):
    if not can_manage_expenses(request, "view"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    voucher = expense_services.get_voucher(company_id, branch_id, voucher_id)
    if not voucher:
        messages.error(request, "Expense voucher was not found.")
        return redirect("accounts_module:expenses")
    expense_services.mark_printed(request, voucher)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        company = dictfetchone(cursor)
        cursor.execute("SELECT * FROM branches WHERE id=%s LIMIT 1", [branch_id])
        branch = dictfetchone(cursor)
    return render(request, "accounts_module/expense_voucher_print.html", {"voucher": voucher, "company": company, "branch": branch})


def can_view_accounting(request):
    return int(request.session.get("is_master_user") or 0) == 1 or user_has_permission(
        request,
        "accounting_reports",
        "view",
    )


def expense_permission_code(request):
    if user_has_permission(request, "expense_vouchers", "view"):
        return "expense_vouchers"
    return "expense_heads"


def can_manage_expenses(request, action):
    if int(request.session.get("is_master_user") or 0) == 1:
        return True
    code = expense_permission_code(request)
    return user_has_permission(request, code, action)


def can_cancel_expense(request):
    return can_manage_expenses(request, "delete") or can_manage_expenses(request, "edit")


def require_scope(request):
    company_id = get_current_company_id(request)
    branch_id = get_current_branch_id(request)
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


def safe_page(value):
    try:
        return int(value or 1)
    except ValueError:
        return 1


def list_journals(company_id, branch_id, filters, page):
    page_data = paginate(0, page)
    params = [company_id, branch_id]
    clauses = ["je.company_id = %s", "je.branch_id = %s"]
    if filters["q"]:
        like = f"%{filters['q']}%"
        clauses.append("(je.entry_no LIKE %s OR je.description LIKE %s)")
        params.extend([like, like])
    if filters["date_from"]:
        clauses.append("je.entry_date >= %s")
        params.append(filters["date_from"])
    if filters["date_to"]:
        clauses.append("je.entry_date <= %s")
        params.append(filters["date_to"])
    if filters["reference_type"]:
        clauses.append("je.reference_type = %s")
        params.append(filters["reference_type"])
    where_sql = " AND ".join(clauses)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM journal_entries je WHERE {where_sql}", params)
        total = int(cursor.fetchone()[0] or 0)
        page_data = paginate(total, page)
        cursor.execute(
            f"""
            SELECT
                je.*,
                u.full_name AS created_by_name,
                COALESCE(SUM(jel.debit), 0) AS total_debit,
                COALESCE(SUM(jel.credit), 0) AS total_credit
            FROM journal_entries je
            LEFT JOIN users u ON u.id = je.created_by_id
            LEFT JOIN journal_entry_lines jel ON jel.journal_entry_id = je.id
            WHERE {where_sql}
            GROUP BY je.id
            ORDER BY je.entry_date DESC, je.entry_no DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_data["per_page"], page_data["offset"]],
        )
        rows = dictfetchall(cursor)
    return rows, total


def get_journal(company_id, branch_id, journal_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT je.*, u.full_name AS created_by_name
            FROM journal_entries je
            LEFT JOIN users u ON u.id = je.created_by_id
            WHERE je.company_id = %s AND je.branch_id = %s AND je.id = %s
            LIMIT 1
            """,
            [company_id, branch_id, journal_id],
        )
        return dictfetchone(cursor)


def get_journal_lines(journal_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                jel.*,
                a.account_code,
                a.account_name
            FROM journal_entry_lines jel
            JOIN accounts a ON a.id = jel.account_id
            WHERE jel.journal_entry_id = %s
            ORDER BY jel.id
            """,
            [journal_id],
        )
        return dictfetchall(cursor)


def expense_form_data(voucher):
    return {key: voucher.get(key) or "" for key in ["voucher_no", "voucher_date", "expense_head_id", "cash_bank_account_id", "payment_mode", "cheque_reference_no", "amount", "tax_percent", "tax_amount", "total_amount", "remarks", "status"]}
