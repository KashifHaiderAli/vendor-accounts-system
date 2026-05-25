from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render

from accounts_module.accounting_engine import AccountingError
from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from core import validators
from core.edition_utils import is_tax_enabled
from core.print_utils import build_print_context
from settings_module.services import log_user_activity

from . import delivery_services, invoice_services, receipt_services, return_services, services


SALES_CARDS = [
    ("Quotations", "quotations", "sales:quotations", "bi-file-earmark-text", "Prepare customer quotations with itemized totals."),
    ("Customer Confirmations / PO", "customer_confirmations", "sales:confirmations", "bi-clipboard-check", "Record customer POs, calls, messages, and direct confirmations."),
    ("Delivery Challans", "delivery_challans", "sales:delivery_challans", "bi-truck", "Issue no-amount delivery documents."),
    ("Sales Invoices / Cash Memo", "sales_invoices", "sales:invoices", "bi-receipt", "Issue tax invoices and cash memos."),
    ("Sales Returns", "sales_returns", "sales:returns", "bi-arrow-counterclockwise", "Record sales returns and post credit note journals."),
    ("Customer Receipts", "customer_receipts", "sales:receipts", "bi-cash-coin", "Record customer payments and post receipt journals."),
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
            "can_invoice": user_has_permission(request, "sales_invoices", "add") and quotation.get("status") != "Cancelled",
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


@permission_required_custom("quotations", "view")
def classic_print_quotation(request, quotation_id):
    return render_classic_quotation(request, quotation_id, "Classic printed", pdf=False)


@permission_required_custom("quotations", "view")
def classic_pdf_quotation(request, quotation_id):
    response = render_classic_quotation(request, quotation_id, "Classic PDF viewed", pdf=True)
    response["Content-Disposition"] = 'inline; filename="quotation-classic.html"'
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
            "can_delivery": user_has_permission(request, "delivery_challans", "add"),
            "can_invoice": user_has_permission(request, "sales_invoices", "add"),
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
            "can_delivery": user_has_permission(request, "delivery_challans", "add") and confirmation.get("status") != "Cancelled",
            "can_invoice": user_has_permission(request, "sales_invoices", "add") and confirmation.get("status") != "Cancelled",
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
    context = services.get_confirmation_print_context(company_id, branch_id, confirmation_id)
    context.update(build_print_context(company_id, request, "Customer Confirmation / PO"))
    return render(request, "sales/confirmation_print.html", context)


@permission_required_custom("delivery_challans", "view")
def delivery_challans_list(request):
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
    rows, pagination = delivery_services.list_challans(company_id, branch_id, search, status, date_from, date_to, page)
    return render(
        request,
        "sales/delivery_challans_list.html",
        {
            "page_title": "Delivery Challans",
            "rows": rows,
            "search": search,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "statuses": delivery_services.DC_STATUSES,
            "can_add": user_has_permission(request, "delivery_challans", "add"),
            "can_edit": user_has_permission(request, "delivery_challans", "edit"),
            "can_cancel": can_cancel_delivery(request),
            "can_invoice": user_has_permission(request, "sales_invoices", "add"),
        },
    )


@login_required_custom
def delivery_challan_form(request, challan_id=None, confirmation_id=None, quotation_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = challan_id is not None
    if not user_has_permission(request, "delivery_challans", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)

    challan = delivery_services.get_challan(company_id, branch_id, challan_id) if is_edit else None
    if is_edit and not challan:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    if is_edit and challan.get("status") in {"Cancelled", "Invoiced"}:
        messages.error(request, "Cancelled or invoiced delivery challans cannot be edited.")
        return redirect("sales:delivery_challan_detail", challan_id=challan_id)

    signed_only = bool(challan and challan.get("status") == "Signed Received")
    confirmation = delivery_services.get_confirmation(company_id, branch_id, confirmation_id) if confirmation_id else None
    quotation = delivery_services.get_quotation(company_id, branch_id, quotation_id) if quotation_id else None
    if confirmation_id and not confirmation:
        messages.error(request, "Customer confirmation was not found.")
        return redirect("sales:confirmations")
    if quotation_id and not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")

    form_data = challan_form_data(challan) if is_edit else delivery_services.default_form_data(company_id, branch_id, quotation, confirmation)
    errors = {}

    if request.method == "POST":
        if signed_only:
            form_data.update(
                {
                    "signed_copy_path": request.POST.get("signed_copy_path", ""),
                    "received_by": request.POST.get("received_by", ""),
                    "remarks": request.POST.get("remarks", ""),
                }
            )
            errors, form_data = delivery_services.validate_and_clean(form_data, company_id, branch_id, challan_id, signed_only=True)
            if not errors:
                delivery_services.save_challan(company_id, branch_id, request.session.get("user_id"), form_data, challan_id, signed_only=True)
                log_user_activity(request, "UPDATE", "Delivery Challans", "delivery_challans", challan_id, f"Updated signed copy for challan {challan['dc_no']}.")
                messages.success(request, "Signed copy details updated successfully.")
                return redirect("sales:delivery_challan_detail", challan_id=challan_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = delivery_services.parse_post(request.POST)
            errors, form_data = delivery_services.validate_and_clean(form_data, company_id, branch_id, challan_id)
            if not errors:
                try:
                    saved_id = delivery_services.save_challan(company_id, branch_id, request.session.get("user_id"), form_data, challan_id)
                    log_user_activity(
                        request,
                        "UPDATE" if is_edit else "CREATE",
                        "Delivery Challans",
                        "delivery_challans",
                        saved_id,
                        f"{'Updated' if is_edit else 'Created'} delivery challan {form_data['dc_no']}.",
                    )
                    messages.success(request, f"Delivery challan {'updated' if is_edit else 'created'} successfully.")
                    return redirect("sales:delivery_challan_detail", challan_id=saved_id)
                except ValueError as exc:
                    messages.error(request, str(exc))
                except DatabaseError:
                    messages.error(request, "Unable to save delivery challan. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "sales/delivery_challan_form.html",
        {
            "page_title": "Edit Delivery Challan" if is_edit else "New Delivery Challan",
            "form_data": form_data,
            "form_items": form_data.get("items", []),
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "signed_only": signed_only,
            "customers": delivery_services.get_customers(company_id, branch_id),
            "items": delivery_services.get_items(company_id, branch_id),
            "confirmations": delivery_services.get_confirmations(company_id, branch_id),
            "quotations": delivery_services.get_quotations(company_id, branch_id),
            "statuses": delivery_services.DC_STATUSES,
        },
    )


@permission_required_custom("delivery_challans", "view")
def delivery_challan_detail(request, challan_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    challan = delivery_services.get_challan(company_id, branch_id, challan_id)
    if not challan:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    return render(
        request,
        "sales/delivery_challan_detail.html",
        {
            "page_title": challan["dc_no"],
            "challan": challan,
            "items": delivery_services.get_challan_items(challan_id),
            "can_edit": user_has_permission(request, "delivery_challans", "edit") and challan.get("status") in {"Draft", "Printed", "Signed Received"},
            "can_cancel": can_cancel_delivery(request) and challan.get("status") not in {"Cancelled", "Invoiced"},
            "can_invoice": user_has_permission(request, "sales_invoices", "add") and challan.get("status") not in {"Cancelled", "Invoiced"},
        },
    )


@login_required_custom
def cancel_delivery_challan(request, challan_id):
    if not can_cancel_delivery(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    challan = delivery_services.get_challan(company_id, branch_id, challan_id)
    if not challan:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    if request.method == "POST":
        try:
            delivery_services.cancel_challan(request, challan)
            messages.success(request, "Delivery challan cancelled successfully.")
            return redirect("sales:delivery_challan_detail", challan_id=challan_id)
        except (DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel delivery challan.")
            return redirect("sales:delivery_challan_detail", challan_id=challan_id)
    return render(request, "sales/confirm_cancel_delivery_challan.html", {"page_title": "Cancel Delivery Challan", "challan": challan})


@login_required_custom
def print_delivery_challan(request, challan_id):
    if not (user_has_permission(request, "delivery_challans", "print") or user_has_permission(request, "delivery_challans", "view")):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    challan = delivery_services.get_challan(company_id, branch_id, challan_id)
    if not challan:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    delivery_services.mark_printed(request, challan)
    context = delivery_services.get_print_context(company_id, branch_id, challan_id)
    context.update(build_print_context(company_id, request, "Delivery Challan"))
    return render(request, "sales/delivery_challan_print.html", context)


@login_required_custom
def upload_signed_challan(request, challan_id):
    if not user_has_permission(request, "delivery_challans", "edit"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    challan = delivery_services.get_challan(company_id, branch_id, challan_id)
    if not challan:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    if challan.get("status") in {"Cancelled", "Invoiced"}:
        messages.error(request, "Signed copy cannot be updated for cancelled or invoiced challans.")
        return redirect("sales:delivery_challan_detail", challan_id=challan_id)
    form_data = {
        "signed_copy_path": challan.get("signed_copy_path") or "",
        "received_by": challan.get("received_by") or "",
        "remarks": challan.get("remarks") or "",
    }
    errors = {}
    if request.method == "POST":
        form_data = {
            "signed_copy_path": request.POST.get("signed_copy_path", ""),
            "received_by": request.POST.get("received_by", ""),
            "remarks": request.POST.get("remarks", ""),
        }
        errors, form_data = delivery_services.validate_and_clean(form_data, company_id, branch_id, challan_id, signed_only=True)
        if not errors:
            delivery_services.save_challan(company_id, branch_id, request.session.get("user_id"), form_data, challan_id, signed_only=True)
            log_user_activity(request, "UPDATE", "Delivery Challans", "delivery_challans", challan_id, f"Updated signed copy for challan {challan['dc_no']}.")
            messages.success(request, "Signed copy updated successfully.")
            return redirect("sales:delivery_challan_detail", challan_id=challan_id)
        messages.error(request, "Please correct the highlighted errors.")
    return render(
        request,
        "sales/upload_signed_challan.html",
        {"page_title": "Upload Signed Copy", "challan": challan, "form_data": form_data, "errors": errors},
    )


@permission_required_custom("sales_invoices", "view")
def invoices_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    invoice_type = request.GET.get("invoice_type", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = invoice_services.list_invoices(company_id, branch_id, search, invoice_type, status, date_from, date_to, page)
    return render(
        request,
        "sales/invoices_list.html",
        {
            "page_title": "Sales Invoices / Cash Memo",
            "rows": rows,
            "search": search,
            "invoice_type": invoice_type,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "invoice_types": invoice_services.INVOICE_TYPES,
            "invoice_type_labels": invoice_services.INVOICE_TYPE_LABELS,
            "statuses": invoice_services.INVOICE_STATUSES,
            "can_add": user_has_permission(request, "sales_invoices", "add"),
            "can_edit": user_has_permission(request, "sales_invoices", "edit"),
            "can_cancel": can_cancel_invoice(request),
            "can_receipt": user_has_permission(request, "customer_receipts", "add"),
            "can_return": user_has_permission(request, "sales_returns", "add"),
        },
    )


@login_required_custom
def invoice_form(request, invoice_id=None, dc_id=None, confirmation_id=None, quotation_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = invoice_id is not None
    if not user_has_permission(request, "sales_invoices", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    invoice = invoice_services.get_invoice(company_id, branch_id, invoice_id) if is_edit else None
    if is_edit and not invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    if is_edit and invoice.get("status") == "Cancelled":
        messages.error(request, "Cancelled invoices cannot be edited.")
        return redirect("sales:invoice_detail", invoice_id=invoice_id)
    posted = bool(invoice and invoice.get("journal_entry_id"))

    dc = invoice_services.get_delivery_challan(company_id, branch_id, dc_id) if dc_id else None
    confirmation = invoice_services.get_confirmation(company_id, branch_id, confirmation_id) if confirmation_id else None
    quotation = invoice_services.get_quotation(company_id, branch_id, quotation_id) if quotation_id else None
    if dc_id and not dc:
        messages.error(request, "Delivery challan was not found.")
        return redirect("sales:delivery_challans")
    if confirmation_id and not confirmation:
        messages.error(request, "Customer confirmation was not found.")
        return redirect("sales:confirmations")
    if quotation_id and not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")

    invoice_type = request.GET.get("invoice_type", "tax_invoice")
    form_data = invoice_form_data(invoice) if is_edit else invoice_services.default_form_data(company_id, branch_id, invoice_type, dc, confirmation, quotation)
    errors = {}
    if not form_data.get("customer_id") and (dc or confirmation or quotation):
        messages.warning(request, "This invoice is for an unregistered party. Customer ledger/account posting requires customer master. Please add as customer before posting invoice.")

    if request.method == "POST":
        if posted:
            form_data.update(
                {
                    "po_number": request.POST.get("po_number", ""),
                    "payment_terms_id": request.POST.get("payment_terms_id", ""),
                    "due_date": request.POST.get("due_date", ""),
                    "remarks": request.POST.get("remarks", ""),
                }
            )
            errors, form_data = validate_invoice_nonfinancial(form_data, company_id, branch_id)
            if not errors:
                invoice_services.save_invoice(company_id, branch_id, request.session.get("user_id"), form_data, invoice_id)
                log_user_activity(request, "UPDATE", "Sales Invoices", "sales_invoices", invoice_id, f"Updated non-financial details for invoice {invoice['invoice_no']}.")
                messages.success(request, "Invoice updated successfully.")
                return redirect("sales:invoice_detail", invoice_id=invoice_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = invoice_services.parse_post(request.POST)
            if request.POST.get("received_amount") not in {"", None, "0", "0.00"}:
                messages.warning(request, "Customer Receipt module will handle payments in Phase 12. Received Amount is currently read-only/0.")
            errors, form_data = invoice_services.validate_and_calculate(form_data, company_id, branch_id, invoice_id)
            if not errors:
                try:
                    saved_id = invoice_services.save_invoice(company_id, branch_id, request.session.get("user_id"), form_data, invoice_id)
                    log_user_activity(request, "CREATE" if not is_edit else "UPDATE", "Sales Invoices", "sales_invoices", saved_id, f"{'Created' if not is_edit else 'Updated'} invoice {form_data['invoice_no']}.")
                    messages.success(request, f"Invoice {'created' if not is_edit else 'updated'} successfully.")
                    return redirect("sales:invoice_detail", invoice_id=saved_id)
                except ValueError as exc:
                    messages.error(request, str(exc))
                except ValueError as exc:
                    messages.error(request, str(exc))
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save invoice. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "sales/invoice_form.html",
        {
            "page_title": "Edit Invoice" if is_edit else "New Invoice",
            "form_data": form_data,
            "form_items": form_data.get("items", []),
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "posted": posted,
            "customers": invoice_services.get_customers(company_id, branch_id),
            "items": invoice_services.get_items(company_id, branch_id),
            "payment_terms": invoice_services.get_payment_terms(company_id, branch_id),
            "delivery_challans": invoice_services.get_delivery_challans(company_id, branch_id),
            "confirmations": invoice_services.get_confirmations(company_id, branch_id),
            "quotations": invoice_services.get_quotations(company_id, branch_id),
            "invoice_types": invoice_services.INVOICE_TYPES,
            "invoice_type_labels": invoice_services.INVOICE_TYPE_LABELS,
            "statuses": invoice_services.INVOICE_STATUSES,
        },
    )


@permission_required_custom("sales_invoices", "view")
def invoice_detail(request, invoice_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    invoice = invoice_services.get_invoice(company_id, branch_id, invoice_id)
    if not invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    return render(
        request,
        "sales/invoice_detail.html",
        {
            "page_title": invoice["invoice_no"],
            "invoice": invoice,
            "items": invoice_services.get_invoice_items(invoice_id),
            "can_edit": user_has_permission(request, "sales_invoices", "edit") and invoice.get("status") != "Cancelled",
            "can_cancel": can_cancel_invoice(request) and invoice.get("status") != "Cancelled",
            "can_receipt": user_has_permission(request, "customer_receipts", "add") and invoice.get("status") not in {"Cancelled", "Paid"},
            "can_return": user_has_permission(request, "sales_returns", "add") and invoice.get("status") != "Cancelled",
        },
    )


@login_required_custom
def cancel_invoice(request, invoice_id):
    if not can_cancel_invoice(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    invoice = invoice_services.get_invoice(company_id, branch_id, invoice_id)
    if not invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    if request.method == "POST":
        try:
            invoice_services.cancel_invoice(request, invoice)
            messages.success(request, "Invoice cancelled and reversal journal created successfully.")
            return redirect("sales:invoice_detail", invoice_id=invoice_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel invoice.")
            return redirect("sales:invoice_detail", invoice_id=invoice_id)
    return render(request, "sales/confirm_cancel_invoice.html", {"page_title": "Cancel Invoice", "invoice": invoice})


@permission_required_custom("sales_invoices", "view")
def print_invoice(request, invoice_id):
    return render_invoice_print(request, invoice_id, digital=False)


@permission_required_custom("sales_invoices", "view")
def digital_print_invoice(request, invoice_id):
    return render_invoice_print(request, invoice_id, digital=True)


@permission_required_custom("sales_invoices", "view")
def classic_print_invoice(request, invoice_id):
    return render_classic_invoice(request, invoice_id, pdf=False)


@permission_required_custom("sales_invoices", "view")
def classic_pdf_invoice(request, invoice_id):
    response = render_classic_invoice(request, invoice_id, pdf=True)
    response["Content-Disposition"] = 'inline; filename="invoice-classic.html"'
    return response


def render_invoice_print(request, invoice_id, digital=False):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    invoice = invoice_services.get_invoice(company_id, branch_id, invoice_id)
    if not invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    invoice_services.mark_printed(request, invoice, digital=digital)
    template = "sales/invoice_print_digital.html" if digital else "sales/invoice_print_preprinted.html"
    context = invoice_services.get_print_context(company_id, branch_id, invoice_id)
    context.update(build_print_context(company_id, request, "Digital Invoice" if digital else "Sales Invoice", force_logo=digital, force_pdf=digital))
    return render(request, template, context)


def render_classic_invoice(request, invoice_id, pdf=False):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    invoice = invoice_services.get_invoice(company_id, branch_id, invoice_id)
    if not invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    invoice_services.mark_printed(request, invoice, digital=pdf)
    context = invoice_services.get_print_context(company_id, branch_id, invoice_id)
    context.update(build_print_context(company_id, request, "Classic Invoice", force_logo=pdf, force_pdf=pdf))
    context.update(build_classic_print_context(context, request, company_id, terms_source=None))
    return render(request, "sales/invoice_print_classic.html", context)


@permission_required_custom("customer_receipts", "view")
def receipts_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    payment_mode = request.GET.get("payment_mode", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = receipt_services.list_receipts(company_id, branch_id, search, payment_mode, date_from, date_to, page)
    return render(
        request,
        "sales/receipts_list.html",
        {
            "page_title": "Customer Receipts",
            "rows": rows,
            "search": search,
            "payment_mode": payment_mode,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "payment_modes": receipt_services.PAYMENT_MODES,
            "can_add": user_has_permission(request, "customer_receipts", "add"),
            "can_edit": user_has_permission(request, "customer_receipts", "edit"),
            "can_cancel": can_cancel_receipt(request),
        },
    )


@login_required_custom
def receipt_form(request, receipt_id=None, invoice_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = receipt_id is not None
    if not user_has_permission(request, "customer_receipts", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    receipt = receipt_services.get_receipt(company_id, branch_id, receipt_id) if is_edit else None
    if is_edit and not receipt:
        messages.error(request, "Customer receipt was not found.")
        return redirect("sales:receipts")
    if is_edit and receipt.get("reversal_id"):
        messages.error(request, "Cancelled receipts cannot be edited.")
        return redirect("sales:receipt_detail", receipt_id=receipt_id)
    source_invoice = receipt_services.get_invoice(company_id, branch_id, invoice_id) if invoice_id else None
    if invoice_id and not source_invoice:
        messages.error(request, "Invoice was not found or has no payable balance.")
        return redirect("sales:invoices")

    posted = bool(receipt and receipt.get("journal_entry_id"))
    form_data = receipt_form_data(receipt) if is_edit else receipt_services.default_form_data(company_id, branch_id, source_invoice)
    errors = {}
    if request.method == "POST":
        if posted:
            form_data.update({"cheque_reference_no": request.POST.get("cheque_reference_no", ""), "remarks": request.POST.get("remarks", "")})
            form_data["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(form_data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
            form_data["remarks"], errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {key: value for key, value in errors.items() if value}
            if not errors:
                receipt_services.save_receipt(company_id, branch_id, request.session.get("user_id"), form_data, receipt_id)
                log_user_activity(request, "UPDATE", "Customer Receipts", "customer_receipts", receipt_id, f"Updated non-financial details for receipt {receipt['receipt_no']}.")
                messages.success(request, "Customer receipt updated successfully.")
                return redirect("sales:receipt_detail", receipt_id=receipt_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = receipt_services.parse_post(request.POST)
            errors, form_data = receipt_services.validate_and_clean(form_data, company_id, branch_id, receipt_id)
            if not errors:
                try:
                    saved_id = receipt_services.save_receipt(company_id, branch_id, request.session.get("user_id"), form_data, receipt_id)
                    log_user_activity(request, "CREATE" if not is_edit else "UPDATE", "Customer Receipts", "customer_receipts", saved_id, f"{'Created' if not is_edit else 'Updated'} customer receipt {form_data['receipt_no']}.")
                    messages.success(request, f"Customer receipt {'created' if not is_edit else 'updated'} successfully.")
                    return redirect("sales:receipt_detail", receipt_id=saved_id)
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save customer receipt. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "sales/receipt_form.html",
        {
            "page_title": "Edit Customer Receipt" if is_edit else "New Customer Receipt",
            "form_data": form_data,
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "posted": posted,
            "customers": receipt_services.get_customers(company_id, branch_id),
            "cash_bank_accounts": receipt_services.get_cash_bank_accounts(company_id, branch_id),
            "open_invoices": receipt_services.get_open_invoices(company_id, branch_id, form_data.get("customer_id") or None),
            "payment_modes": receipt_services.PAYMENT_MODES,
        },
    )


@permission_required_custom("customer_receipts", "view")
def receipt_detail(request, receipt_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    receipt = receipt_services.get_receipt(company_id, branch_id, receipt_id)
    if not receipt:
        messages.error(request, "Customer receipt was not found.")
        return redirect("sales:receipts")
    return render(
        request,
        "sales/receipt_detail.html",
        {
            "page_title": receipt["receipt_no"],
            "receipt": receipt,
            "can_edit": user_has_permission(request, "customer_receipts", "edit") and not receipt.get("reversal_id"),
            "can_cancel": can_cancel_receipt(request) and not receipt.get("reversal_id"),
        },
    )


@login_required_custom
def cancel_receipt(request, receipt_id):
    if not can_cancel_receipt(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    receipt = receipt_services.get_receipt(company_id, branch_id, receipt_id)
    if not receipt:
        messages.error(request, "Customer receipt was not found.")
        return redirect("sales:receipts")
    if request.method == "POST":
        try:
            receipt_services.cancel_receipt(request, receipt)
            messages.success(request, "Customer receipt reversed successfully. The historical receipt record remains visible.")
            return redirect("sales:receipt_detail", receipt_id=receipt_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to reverse customer receipt.")
            return redirect("sales:receipt_detail", receipt_id=receipt_id)
    return render(request, "sales/confirm_cancel_receipt.html", {"page_title": "Reverse Customer Receipt", "receipt": receipt})


@permission_required_custom("customer_receipts", "view")
def print_receipt(request, receipt_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    receipt = receipt_services.get_receipt(company_id, branch_id, receipt_id)
    if not receipt:
        messages.error(request, "Customer receipt was not found.")
        return redirect("sales:receipts")
    receipt_services.mark_printed(request, receipt)
    context = receipt_services.get_print_context(company_id, branch_id, receipt_id)
    context.update(build_print_context(company_id, request, "Customer Receipt Voucher"))
    return render(request, "sales/receipt_print.html", context)


@permission_required_custom("sales_returns", "view")
def sales_returns_list(request):
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
    rows, pagination = return_services.list_returns(company_id, branch_id, search, status, date_from, date_to, page)
    return render(request, "sales/sales_returns_list.html", {"page_title": "Sales Returns", "rows": rows, "search": search, "status": status, "date_from": date_from, "date_to": date_to, "pagination": pagination, "statuses": return_services.RETURN_STATUSES, "can_add": user_has_permission(request, "sales_returns", "add"), "can_edit": user_has_permission(request, "sales_returns", "edit"), "can_cancel": can_cancel_sales_return(request)})


@login_required_custom
def sales_return_form(request, return_id=None, invoice_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = return_id is not None
    if not user_has_permission(request, "sales_returns", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    sales_return = return_services.get_return(company_id, branch_id, return_id) if is_edit else None
    if is_edit and not sales_return:
        messages.error(request, "Sales return was not found.")
        return redirect("sales:returns")
    if is_edit and sales_return.get("status") == "Cancelled":
        messages.error(request, "Cancelled sales returns cannot be edited.")
        return redirect("sales:return_detail", return_id=return_id)
    source_invoice = return_services.get_invoice(company_id, branch_id, invoice_id) if invoice_id else None
    if invoice_id and not source_invoice:
        messages.error(request, "Invoice was not found.")
        return redirect("sales:invoices")
    posted = bool(sales_return and sales_return.get("journal_entry_id"))
    form_data = sales_return_form_data(sales_return) if is_edit else return_services.default_form_data(company_id, branch_id, source_invoice)
    errors = {}
    if request.method == "POST":
        if posted:
            form_data.update({"return_reason": request.POST.get("return_reason", ""), "remarks": request.POST.get("remarks", "")})
            form_data["return_reason"], errors["return_reason"] = validators.clean_text(form_data.get("return_reason"), field_name="Return Reason")
            form_data["remarks"], errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {key: value for key, value in errors.items() if value}
            if not errors:
                return_services.save_return(company_id, branch_id, request.session.get("user_id"), form_data, return_id)
                log_user_activity(request, "UPDATE", "Sales Returns", "sales_returns", return_id, f"Updated non-financial details for sales return {sales_return['sales_return_no']}.")
                messages.success(request, "Sales return updated successfully.")
                return redirect("sales:return_detail", return_id=return_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = return_services.parse_post(request.POST)
            errors, form_data = return_services.validate_and_calculate(form_data, company_id, branch_id, return_id)
            if not errors:
                try:
                    saved_id = return_services.save_return(company_id, branch_id, request.session.get("user_id"), form_data, return_id)
                    log_user_activity(request, "CREATE", "Sales Returns", "sales_returns", saved_id, f"Created sales return {form_data['sales_return_no']}.")
                    messages.success(request, "Sales return created and posted successfully.")
                    return redirect("sales:return_detail", return_id=saved_id)
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save sales return. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")
    return render(request, "sales/sales_return_form.html", {"page_title": "Edit Sales Return" if is_edit else "New Sales Return", "form_data": form_data, "form_items": form_data.get("items", []), "errors": errors, "error_summary": collect_errors(errors), "is_edit": is_edit, "posted": posted, "customers": return_services.get_customers(company_id, branch_id), "invoices": return_services.get_invoices(company_id, branch_id, form_data.get("customer_id") or None), "items": return_services.get_items(company_id, branch_id)})


@permission_required_custom("sales_returns", "view")
def sales_return_detail(request, return_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    sales_return = return_services.get_return(company_id, branch_id, return_id)
    if not sales_return:
        messages.error(request, "Sales return was not found.")
        return redirect("sales:returns")
    return render(request, "sales/sales_return_detail.html", {"page_title": sales_return["sales_return_no"], "sales_return": sales_return, "items": return_services.get_return_items(return_id), "can_edit": user_has_permission(request, "sales_returns", "edit") and sales_return.get("status") != "Cancelled", "can_cancel": can_cancel_sales_return(request) and sales_return.get("status") != "Cancelled"})


@login_required_custom
def cancel_sales_return(request, return_id):
    if not can_cancel_sales_return(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    sales_return = return_services.get_return(company_id, branch_id, return_id)
    if not sales_return:
        messages.error(request, "Sales return was not found.")
        return redirect("sales:returns")
    if request.method == "POST":
        try:
            return_services.cancel_return(request, sales_return)
            messages.success(request, "Sales return cancelled and reversal journal created successfully.")
            return redirect("sales:return_detail", return_id=return_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel sales return.")
            return redirect("sales:return_detail", return_id=return_id)
    return render(request, "sales/confirm_cancel_sales_return.html", {"page_title": "Cancel Sales Return", "sales_return": sales_return})


@permission_required_custom("sales_returns", "view")
def print_sales_return(request, return_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    sales_return = return_services.get_return(company_id, branch_id, return_id)
    if not sales_return:
        messages.error(request, "Sales return was not found.")
        return redirect("sales:returns")
    return_services.mark_printed(request, sales_return)
    context = return_services.get_print_context(company_id, branch_id, return_id)
    context.update(build_print_context(company_id, request, "Credit Note / Sales Return"))
    return render(request, "sales/sales_return_print.html", context)


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
    context.update(build_print_context(company_id, request, "Quotation", force_logo=action_label == "Viewed PDF", force_pdf=action_label == "Viewed PDF"))
    return render(request, "sales/quotation_print.html", context)


def render_classic_quotation(request, quotation_id, action_label, pdf=False):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    quotation = services.get_quotation(company_id, branch_id, quotation_id)
    if not quotation:
        messages.error(request, "Quotation was not found.")
        return redirect("sales:quotations")
    services.mark_printed(request, quotation, action_label)
    context = services.get_print_context(company_id, branch_id, quotation_id)
    context.update(build_print_context(company_id, request, "Classic Quotation", force_logo=pdf, force_pdf=pdf))
    context.update(build_classic_print_context(context, request, company_id, terms_source=quotation.get("terms_conditions")))
    return render(request, "sales/quotation_print_classic.html", context)


def first_nonempty(*values):
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def build_classic_print_context(context, request, company_id, terms_source=None):
    company = context.get("company") or {}
    company_settings = context.get("company_settings") or {}
    tax_enabled = is_tax_enabled(request=request, company_id=company_id)
    company_name = first_nonempty(company_settings.get("company_name"), company.get("company_name"), "Company")
    contact_person = first_nonempty(
        company_settings.get("authorized_person_name"),
        company_settings.get("contact_person"),
        company.get("contact_person"),
        company_name,
    )
    phone_or_mobile = first_nonempty(company_settings.get("mobile"), company_settings.get("phone"), company.get("mobile"), company.get("phone"))
    email = first_nonempty(company_settings.get("email"), company.get("email"))
    terms_text = first_nonempty(terms_source)
    if terms_text and (tax_enabled or "tax" not in terms_text.lower()):
        use_saved_terms = True
    else:
        terms_text = ""
        use_saved_terms = False
    return {
        "tax_enabled": tax_enabled,
        "classic_company_name": company_name,
        "classic_company_address": first_nonempty(company_settings.get("address"), company.get("address")),
        "classic_company_phone": phone_or_mobile,
        "classic_company_email": email,
        "classic_company_website": first_nonempty(company_settings.get("website"), company.get("website")),
        "classic_company_ntn": first_nonempty(company_settings.get("ntn"), company.get("ntn")),
        "classic_company_strn": first_nonempty(company_settings.get("strn"), company.get("strn")),
        "classic_contact_person": contact_person,
        "classic_contact_phone": phone_or_mobile,
        "classic_contact_email": email,
        "classic_terms_text": terms_text,
        "classic_use_saved_terms": use_saved_terms,
    }


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


def can_cancel_delivery(request):
    return user_has_permission(request, "delivery_challans", "delete") or user_has_permission(request, "delivery_challans", "edit")


def can_cancel_invoice(request):
    return user_has_permission(request, "sales_invoices", "delete") or user_has_permission(request, "sales_invoices", "edit")


def can_cancel_receipt(request):
    return user_has_permission(request, "customer_receipts", "delete") or user_has_permission(request, "customer_receipts", "edit")


def can_cancel_sales_return(request):
    return user_has_permission(request, "sales_returns", "delete") or user_has_permission(request, "sales_returns", "edit")


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


def receipt_form_data(receipt):
    return {
        "receipt_no": receipt.get("receipt_no") or "",
        "receipt_date": receipt.get("receipt_date") or "",
        "customer_id": receipt.get("customer_id") or "",
        "payment_mode": receipt.get("payment_mode") or "Cash",
        "cash_bank_account_id": receipt.get("cash_bank_account_id") or "",
        "cheque_reference_no": receipt.get("cheque_reference_no") or "",
        "amount": receipt.get("amount") or "0.00",
        "adjusted_invoice_id": receipt.get("adjusted_invoice_id") or "",
        "remarks": receipt.get("remarks") or "",
    }


def sales_return_form_data(sales_return):
    data = dict(sales_return)
    for key in ["return_reason", "remarks"]:
        data[key] = data.get(key) or ""
    data["items"] = [
        {"item_service_id": item.get("item_service_id") or "", "sales_invoice_item_id": item.get("sales_invoice_item_id") or "", "description": item.get("description") or "", "quantity": item.get("quantity") or "0", "rate": item.get("rate") or "0", "discount_percent": item.get("discount_percent") or "0", "discount_amount": item.get("discount_amount") or "0", "tax_percent": item.get("tax_percent") or "0", "tax_amount": item.get("tax_amount") or "0", "line_total": item.get("line_total") or "0", "errors": {}}
        for item in return_services.get_return_items(sales_return["id"])
    ]
    return data


def challan_form_data(challan):
    data = dict(challan)
    for key in ["customer_id", "confirmation_id", "quotation_id", "po_number", "delivered_by", "received_by", "signed_copy_path", "remarks"]:
        data[key] = data.get(key) or ""
    data["items"] = [
        {
            "item_service_id": item.get("item_service_id") or "",
            "description": item.get("description") or "",
            "quantity": item.get("quantity") or "0",
            "errors": {},
        }
        for item in delivery_services.get_challan_items(challan["id"])
    ]
    if not data["items"]:
        data["items"] = [delivery_services.empty_item_row()]
    return data


def invoice_form_data(invoice):
    data = dict(invoice)
    for key in ["customer_id", "delivery_challan_id", "confirmation_id", "po_number", "payment_terms_id", "due_date", "remarks"]:
        data[key] = data.get(key) or ""
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
        for item in invoice_services.get_invoice_items(invoice["id"])
    ]
    if not data["items"]:
        data["items"] = [invoice_services.empty_item_row()]
    return data


def validate_invoice_nonfinancial(data, company_id, branch_id):
    errors = {}
    data["po_number"], errors["po_number"] = services.validators.clean_text(data.get("po_number"), max_length=100, field_name="PO Number")
    if data.get("payment_terms_id") and not invoice_services.payment_terms_exists(company_id, branch_id, data.get("payment_terms_id")):
        errors["payment_terms_id"] = "Selected payment terms were not found."
    due_date, errors["due_date"] = services.validators.validate_date(data.get("due_date"), "Due Date", required=False)
    data["due_date"] = due_date.isoformat() if due_date else None
    data["remarks"], errors["remarks"] = services.validators.clean_text(data.get("remarks"), field_name="Remarks")
    return {key: value for key, value in errors.items() if value}, data


def collect_errors(errors):
    summary = []
    for key, value in errors.items():
        if key == "items":
            summary.append(value)
        elif value:
            summary.append(str(value))
    return summary
