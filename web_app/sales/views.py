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
    ("Customer Confirmations / PO", "customer_confirmations", "sales:confirmations", "bi-clipboard-check", "Record customer POs, calls, messages, and direct confirmations."),
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
    return redirect("sales:confirmation_from_quotation", quotation_id=quotation_id)


@permission_required_custom("customer_confirmations", "view")
def confirmations_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    confirmation_type = request.GET.get("confirmation_type", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = services.list_confirmations(company_id, branch_id, search, confirmation_type, status, date_from, date_to, page)
    return render(
        request,
        "sales/confirmations_list.html",
        {
            "page_title": "Customer Confirmations / PO",
            "rows": rows,
            "search": search,
            "confirmation_type": confirmation_type,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "confirmation_types": services.CONFIRMATION_TYPES,
            "statuses": services.CONFIRMATION_STATUSES,
            "can_add": user_has_permission(request, "customer_confirmations", "add"),
            "can_edit": user_has_permission(request, "customer_confirmations", "edit"),
            "can_cancel": can_cancel_confirmation(request),
        },
    )


@login_required_custom
def confirmation_form(request, confirmation_id=None, quotation_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = confirmation_id is not None
    if not user_has_permission(request, "customer_confirmations", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)

    confirmation = services.get_confirmation(company_id, branch_id, confirmation_id) if is_edit else None
    if is_edit and not confirmation:
        messages.error(request, "Confirmation was not found.")
        return redirect("sales:confirmations")
    if is_edit and confirmation.get("status") == "Cancelled":
        messages.error(request, "Cancelled confirmations cannot be edited.")
        return redirect("sales:confirmation_detail", confirmation_id=confirmation_id)

    quotation = None
    if quotation_id:
        quotation = services.get_quotation(company_id, branch_id, quotation_id)
        if not quotation:
            messages.error(request, "Quotation was not found.")
            return redirect("sales:quotations")
        if quotation.get("status") == "Cancelled":
            messages.error(request, "Cancelled quotation cannot be converted to confirmation.")
            return redirect("sales:quotation_detail", quotation_id=quotation_id)
        existing = services.get_active_confirmation_for_quotation(company_id, branch_id, quotation_id)
        if existing:
            messages.warning(request, "This quotation already has an active confirmation.")
            return redirect("sales:confirmation_detail", confirmation_id=existing["id"])

    form_data = confirmation_form_data(confirmation) if is_edit else services.default_confirmation_form_data(company_id, branch_id, quotation)
    errors = {}
    selected_quotation = quotation or (services.get_quotation(company_id, branch_id, form_data.get("quotation_id")) if form_data.get("quotation_id") else None)

    if request.method == "POST":
        form_data = services.parse_confirmation_post(request.POST)
        errors, form_data, selected_quotation = services.validate_confirmation_data(form_data, company_id, branch_id, confirmation_id)
        if not errors:
            try:
                saved_id = services.save_confirmation(
                    company_id,
                    branch_id,
                    request.session.get("user_id"),
                    form_data,
                    confirmation_id=confirmation_id,
                )
                action = "UPDATE" if is_edit else "CREATE"
                description = f"{'Updated' if is_edit else 'Created'} confirmation {form_data['confirmation_no']}."
                if form_data.get("quotation_id") and not is_edit:
                    description = f"Created confirmation {form_data['confirmation_no']} from quotation."
                log_user_activity(request, action, "Customer Confirmations", "customer_confirmations", saved_id, description)
                messages.success(request, f"Confirmation {'updated' if is_edit else 'created'} successfully.")
                return redirect("sales:confirmation_detail", confirmation_id=saved_id)
            except DatabaseError:
                messages.error(request, "Unable to save confirmation. Please retry.")
        else:
            messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "sales/confirmation_form.html",
        {
            "page_title": "Edit Confirmation" if is_edit else "New Confirmation",
            "form_data": form_data,
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "customers": services.get_customers(company_id, branch_id),
            "quotations": services.get_quotations_for_select(company_id, branch_id),
            "selected_quotation": selected_quotation,
            "confirmation_types": services.CONFIRMATION_TYPES,
            "statuses": services.CONFIRMATION_STATUSES,
        },
    )


@permission_required_custom("customer_confirmations", "view")
def confirmation_detail(request, confirmation_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    confirmation = services.get_confirmation(company_id, branch_id, confirmation_id)
    if not confirmation:
        messages.error(request, "Confirmation was not found.")
        return redirect("sales:confirmations")
    return render(
        request,
        "sales/confirmation_detail.html",
        {
            "page_title": confirmation["confirmation_no"],
            "confirmation": confirmation,
            "can_edit": user_has_permission(request, "customer_confirmations", "edit") and confirmation.get("status") != "Cancelled",
            "can_cancel": can_cancel_confirmation(request) and confirmation.get("status") != "Cancelled",
        },
    )


@login_required_custom
def cancel_confirmation(request, confirmation_id):
    if not can_cancel_confirmation(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    confirmation = services.get_confirmation(company_id, branch_id, confirmation_id)
    if not confirmation:
        messages.error(request, "Confirmation was not found.")
        return redirect("sales:confirmations")
    if request.method == "POST":
        try:
            services.cancel_confirmation(request, confirmation)
            messages.success(request, "Confirmation cancelled successfully.")
            return redirect("sales:confirmation_detail", confirmation_id=confirmation_id)
        except (DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel confirmation.")
            return redirect("sales:confirmation_detail", confirmation_id=confirmation_id)
    return render(
        request,
        "sales/confirm_cancel_confirmation.html",
        {"page_title": "Cancel Confirmation", "confirmation": confirmation},
    )


@permission_required_custom("customer_confirmations", "view")
def print_confirmation(request, confirmation_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    confirmation = services.get_confirmation(company_id, branch_id, confirmation_id)
    if not confirmation:
        messages.error(request, "Confirmation was not found.")
        return redirect("sales:confirmations")
    services.mark_confirmation_printed(request, confirmation)
    return render(request, "sales/confirmation_print.html", services.get_confirmation_print_context(company_id, branch_id, confirmation_id))


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


def can_cancel_confirmation(request):
    return user_has_permission(request, "customer_confirmations", "delete") or user_has_permission(request, "customer_confirmations", "edit")


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


def confirmation_form_data(confirmation):
    return {
        "confirmation_no": confirmation.get("confirmation_no") or "",
        "confirmation_date": confirmation.get("confirmation_date") or "",
        "customer_id": confirmation.get("customer_id") or "",
        "quotation_id": confirmation.get("quotation_id") or "",
        "confirmation_type": confirmation.get("confirmation_type") or "PO",
        "po_number": confirmation.get("po_number") or "",
        "po_date": confirmation.get("po_date") or "",
        "po_amount": confirmation.get("po_amount") or "0.00",
        "contact_person": confirmation.get("contact_person") or "",
        "confirmation_note": confirmation.get("confirmation_note") or "",
        "attachment_path": confirmation.get("attachment_path") or "",
        "total_amount": confirmation.get("total_amount") or "0.00",
        "status": confirmation.get("status") or "Open",
        "remarks": confirmation.get("remarks") or "",
    }


def collect_errors(errors):
    summary = []
    for key, value in errors.items():
        if key == "items":
            summary.append(value)
        elif value:
            summary.append(str(value))
    return summary
