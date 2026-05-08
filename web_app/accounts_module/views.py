from __future__ import annotations

from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect, render

from authentication.auth_utils import dictfetchall, dictfetchone, user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from masters.master_utils import paginate

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


def can_view_accounting(request):
    return int(request.session.get("is_master_user") or 0) == 1 or user_has_permission(
        request,
        "accounting_reports",
        "view",
    )


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
