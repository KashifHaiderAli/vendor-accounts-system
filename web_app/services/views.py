from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render

from accounts_module.accounting_engine import AccountingError
from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from settings_module.services import log_user_activity

from . import contract_services


@login_required_custom
def index(request):
    cards = []
    if user_has_permission(request, "service_contracts", "view"):
        cards.append({"label": "Service Contracts", "url_name": "services:contracts", "icon": "bi-briefcase", "description": "Manage recurring and one-time customer service agreements."})
    return render(request, "services/index.html", {"page_title": "Services", "service_cards": cards})


@permission_required_custom("service_contracts", "view")
def contracts_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    billing_cycle = request.GET.get("billing_cycle", "").strip()
    expiring_soon = request.GET.get("expiring_soon") == "1"
    billing_due = request.GET.get("billing_due") == "1"
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = contract_services.list_contracts(company_id, branch_id, search, status, billing_cycle, expiring_soon, billing_due, date_from, date_to, page)
    return render(request, "services/contracts_list.html", {"page_title": "Service Contracts", "rows": rows, "pagination": pagination, "search": search, "status": status, "billing_cycle": billing_cycle, "expiring_soon": expiring_soon, "billing_due": billing_due, "date_from": date_from, "date_to": date_to, "statuses": contract_services.STATUSES, "billing_cycles": contract_services.BILLING_CYCLES, "can_add": user_has_permission(request, "service_contracts", "add"), "can_edit": user_has_permission(request, "service_contracts", "edit")})


@login_required_custom
def contract_form(request, contract_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = contract_id is not None
    if not user_has_permission(request, "service_contracts", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    contract = contract_services.get_contract(company_id, branch_id, contract_id) if is_edit else None
    if is_edit and not contract:
        messages.error(request, "Service contract was not found.")
        return redirect("services:contracts")
    form_data = contract_form_data(contract) if is_edit else contract_services.default_form_data(company_id, branch_id)
    errors = {}
    if request.method == "POST":
        form_data = contract_services.parse_post(request.POST)
        errors, form_data = contract_services.validate_contract(form_data, company_id, branch_id, contract_id)
        if not errors:
            try:
                saved_id = contract_services.save_contract(company_id, branch_id, request.session.get("user_id"), form_data, contract_id)
                log_user_activity(request, "UPDATE" if is_edit else "CREATE", "Service Contracts", "service_contracts", saved_id, f"{'Updated' if is_edit else 'Created'} service contract {form_data['contract_no']}.")
                messages.success(request, f"Service contract {'updated' if is_edit else 'created'} successfully.")
                return redirect("services:contract_detail", contract_id=saved_id)
            except DatabaseError:
                messages.error(request, "Unable to save service contract. Please retry.")
        else:
            messages.error(request, "Please correct the highlighted errors.")
    return render(request, "services/contract_form.html", {"page_title": "Edit Service Contract" if is_edit else "New Service Contract", "form_data": form_data, "errors": errors, "error_summary": collect_errors(errors), "is_edit": is_edit, "customers": contract_services.get_customers(company_id, branch_id), "statuses": contract_services.STATUSES, "billing_cycles": contract_services.BILLING_CYCLES})


@permission_required_custom("service_contracts", "view")
def contract_detail(request, contract_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    contract = contract_services.get_contract(company_id, branch_id, contract_id)
    if not contract:
        messages.error(request, "Service contract was not found.")
        return redirect("services:contracts")
    return render(request, "services/contract_detail.html", {"page_title": contract["contract_no"], "contract": contract, "can_edit": user_has_permission(request, "service_contracts", "edit") and contract.get("status") != "Closed", "can_close": user_has_permission(request, "service_contracts", "edit") and contract.get("status") != "Closed", "can_invoice": user_has_permission(request, "sales_invoices", "add") and contract.get("status") == "Active"})


@login_required_custom
def close_contract(request, contract_id):
    if not user_has_permission(request, "service_contracts", "edit"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    contract = contract_services.get_contract(company_id, branch_id, contract_id)
    if not contract:
        messages.error(request, "Service contract was not found.")
        return redirect("services:contracts")
    if request.method == "POST":
        contract_services.close_contract(request, contract)
        messages.success(request, "Service contract closed successfully.")
        return redirect("services:contract_detail", contract_id=contract_id)
    return render(request, "services/confirm_close_contract.html", {"page_title": "Close Service Contract", "contract": contract})


@permission_required_custom("service_contracts", "view")
def print_contract(request, contract_id):
    company_id, branch_id = require_scope(request)
    contract = contract_services.get_contract(company_id, branch_id, contract_id)
    if not contract:
        messages.error(request, "Service contract was not found.")
        return redirect("services:contracts")
    contract_services.mark_printed(request, contract)
    return render(request, "services/contract_print.html", contract_services.get_print_context(company_id, branch_id, contract_id))


@login_required_custom
def generate_contract_invoice(request, contract_id):
    if not (user_has_permission(request, "service_contracts", "edit") and user_has_permission(request, "sales_invoices", "add")):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    contract = contract_services.get_contract(company_id, branch_id, contract_id)
    if not contract:
        messages.error(request, "Service contract was not found.")
        return redirect("services:contracts")
    if request.method == "POST":
        try:
            invoice_id = contract_services.generate_invoice_from_contract(request, contract)
            messages.success(request, "Invoice generated from service contract successfully.")
            return redirect("sales:invoice_detail", invoice_id=invoice_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to generate invoice.")
            return redirect("services:contract_detail", contract_id=contract_id)
    return render(request, "services/confirm_generate_contract_invoice.html", {"page_title": "Generate Contract Invoice", "contract": contract})


def require_scope(request):
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


def contract_form_data(contract):
    data = dict(contract)
    for key in ["customer_id", "service_type", "start_date", "end_date", "billing_cycle", "next_billing_date", "renewal_reminder_date", "contract_details", "status", "remarks"]:
        data[key] = data.get(key) or ""
    return data


def collect_errors(errors):
    return [str(value) for value in errors.values() if value]
