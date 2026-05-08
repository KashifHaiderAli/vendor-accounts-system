from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from settings_module.services import log_user_activity

from . import services


SALES_CARDS = [
    ("Quotations", "quotations", "sales:quotations", "bi-file-earmark-text", "Prepare customer quotations with itemized totals."),
    ("Customer Confirmations / PO", "customer_confirmations", "sales:index", "bi-clipboard-check", "Phase 8 workflow placeholder."),
    ("Delivery Challans", "delivery_challans", "sales:index", "bi-truck", "Future delivery documentation."),
    ("Sales Invoices / Cash Memo", "sales_invoices", "sales:index", "bi-receipt", "Future invoice workflow."),
    ("Sales Returns", "sales_returns", "sales:index", "bi-arrow-counterclockwise", "Future return workflow."),
    ("Customer Receipts", "customer_receipts", "sales:index", "bi-cash-coin", "Future receipt workflow."),
]


@login_required_custom
def index(request):
    cards = []
    for label, permission, url_name, icon, description in SALES_CARDS:
        if user_has_permission(request, permission, "view"):
            cards.append({"label": label, "url_name": url_name, "icon": icon, "description": description})
    return render(request, "sales/index.html", {"page_title": "Sales", "sales_cards": cards})


@permission_required_custom("quotations", "view")
def quotations_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = services.list_quotations(company_id, branch_id, search, status, date_from, date_to, page)
    return render(
        request,
        "sales/quotations_list.html",
        {
            "page_title": "Quotations",
            "rows": rows,
            "search": search,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "statuses": services.STATUSES,
            "can_add": user_has_permission(request, "quotations", "add"),
            "can_edit": user_has_permission(request, "quotations", "edit"),
            "can_cancel": can_cancel(request),
            "can_convert": user_has_permission(request, "customer_confirmations", "add"),
        },
    )


@login_required_custom
def quotation_form(request, quotation_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = quotation_id is not None
    if not user_has_permission(request, "quotations", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)

    quotation = services.get_quotation(company_id, branch_id, quotation_id) if is_edit else None
    if is_edit and not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    if is_edit and quotation.get("status") in {"Converted", "Cancelled"}:
        messages.error(request, "Converted or cancelled quotations cannot be edited.")
        return redirect("sales:quotation_detail", quotation_id=quotation_id)

    form_data = form_data_from_quotation(company_id, branch_id, quotation) if is_edit else services.default_form_data(company_id, branch_id)
    errors = {}

    if request.method == "POST":
        form_data = services.parse_quotation_post(request.POST)
        errors, form_data = services.validate_and_calculate(form_data, company_id, branch_id, quotation_id)
        if not errors:
            try:
                saved_id = services.save_quotation(
                    company_id,
                    branch_id,
                    request.session.get("user_id"),
                    form_data,
                    quotation_id=quotation_id,
                )
                log_user_activity(
                    request,
                    "UPDATE" if is_edit else "CREATE",
                    "Quotations",
                    "quotations",
                    saved_id,
                    f"{'Updated' if is_edit else 'Created'} quotation {form_data['quotation_no']}.",
                )
                messages.success(request, f"Quotation {'updated' if is_edit else 'created'} successfully.")
                if int(form_data.get("is_customer_saved") or 0) == 0:
                    messages.warning(request, "This quotation party is not saved in Customer Master.")
                return redirect("sales:quotation_detail", quotation_id=saved_id)
            except DatabaseError:
                messages.error(request, "Unable to save quotation. Please retry. If the quotation number already exists, generate a new one.")
        else:
            messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "sales/quotation_form.html",
        {
            "page_title": "Edit Quotation" if is_edit else "New Quotation",
            "form_data": form_data,
            "form_items": form_data.get("items", []),
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "customers": services.get_customers(company_id, branch_id),
            "items": services.get_items(company_id, branch_id),
            "payment_terms": services.get_payment_terms(company_id, branch_id),
            "tax_options": services.TAX_OPTIONS,
            "statuses": services.STATUSES,
        },
    )


@permission_required_custom("quotations", "view")
def quotation_detail(request, quotation_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    return render(
        request,
        "sales/quotation_detail.html",
        {
            "page_title": quotation["quotation_no"],
            "quotation": quotation,
            "items": services.get_quotation_items(quotation_id),
            "can_edit": user_has_permission(request, "quotations", "edit") and quotation.get("status") not in {"Converted", "Cancelled"},
            "can_cancel": can_cancel(request) and quotation.get("status") != "Converted" and quotation.get("status") != "Cancelled",
            "can_duplicate": user_has_permission(request, "quotations", "add"),
            "can_convert": user_has_permission(request, "customer_confirmations", "add") and quotation.get("status") in {"Draft", "Printed"},
            "can_add_customer": user_has_permission(request, "customers", "add")
            and (not quotation.get("customer_id") or int(quotation.get("is_customer_saved") or 0) == 0),
        },
    )


@permission_required_custom("quotations", "add")
def duplicate_quotation(request, quotation_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    try:
        new_id = services.duplicate_quotation(request, quotation)
        messages.success(request, "Quotation duplicated successfully.")
        return redirect("sales:quotation_detail", quotation_id=new_id)
    except (DatabaseError, ValueError) as exc:
        messages.error(request, str(exc) or "Unable to duplicate quotation.")
        return redirect("sales:quotation_detail", quotation_id=quotation_id)


@login_required_custom
def add_as_customer(request, quotation_id):
    if not user_has_permission(request, "customers", "add") or not (
        user_has_permission(request, "quotations", "edit") or user_has_permission(request, "quotations", "view")
    ):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    try:
        customer_id = services.add_quotation_party_as_customer(request, quotation)
        messages.success(request, "Quotation party added to Customer Master successfully.")
        return redirect("masters:customer_edit", record_id=customer_id)
    except ValueError as exc:
        messages.warning(request, str(exc))
    except DatabaseError:
        messages.error(request, "Unable to add quotation party as customer.")
    return redirect("sales:quotation_detail", quotation_id=quotation_id)


@login_required_custom
def cancel_quotation(request, quotation_id):
    if not can_cancel(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    if request.method == "POST":
        try:
            services.cancel_quotation(request, quotation)
            messages.success(request, "Quotation cancelled successfully.")
            return redirect("sales:quotation_detail", quotation_id=quotation_id)
        except (DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel quotation.")
            return redirect("sales:quotation_detail", quotation_id=quotation_id)
    return render(request, "sales/confirm_cancel_quotation.html", {"page_title": "Cancel Quotation", "quotation": quotation})


@permission_required_custom("quotations", "view")
def print_quotation(request, quotation_id):
    return render_print_response(request, quotation_id, "Printed")


@permission_required_custom("quotations", "view")
def pdf_quotation(request, quotation_id):
    response = render_print_response(request, quotation_id, "Viewed PDF")
    response["Content-Disposition"] = 'inline; filename="quotation.html"'
    return response


@permission_required_custom("customer_confirmations", "add")
def convert_to_confirmation(request, quotation_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    return render(
        request,
        "sales/quotation_convert_placeholder.html",
        {"page_title": "Convert Quotation", "quotation": quotation},
    )


def render_print_response(request, quotation_id, action_label):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    services.mark_printed(request, quotation, action_label)
    context = services.get_print_context(company_id, branch_id, quotation_id)
    return render(request, "sales/quotation_print.html", context)


def require_scope(request):
    company_id, branch_id = services.get_scope(request)
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


def can_cancel(request):
    return user_has_permission(request, "quotations", "delete") or user_has_permission(request, "quotations", "edit")


def form_data_from_quotation(company_id, branch_id, quotation):
    data = dict(quotation)
    data["customer_mode"] = "existing" if quotation.get("customer_id") else "new"
    data["items"] = [
        {
            "item_service_id": item.get("item_service_id") or "",
            "description": item.get("description") or "",
            "quantity": item.get("quantity") or "0",
            "rate": item.get("rate") or "0",
            "discount_percent": item.get("discount_percent") or "0",
            "discount_amount": item.get("discount_amount") or "0",
            "tax_percent": item.get("tax_percent") or "0",
            "tax_amount": item.get("tax_amount") or "0",
            "line_total": item.get("line_total") or "0",
            "errors": {},
        }
        for item in services.get_quotation_items(quotation["id"])
    ]
    if not data["items"]:
        data["items"] = services.default_form_data(company_id, branch_id)["items"]
    return data


def collect_errors(errors):
    summary = []
    for key, value in errors.items():
        if key == "items":
            summary.append(value)
        elif value:
            summary.append(str(value))
    return summary
