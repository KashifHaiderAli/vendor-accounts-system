from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from core.logo_utils import get_company_logo_url, save_company_logo
from core import validators as form_validators

from .services import (
    COMPANY_FIELDS,
    COMPANY_SETTINGS_FIELDS,
    NUMBERING_FIELDS,
    branch_code_exists,
    count_active_branches,
    get_branch,
    get_company,
    get_company_settings,
    get_numbering_settings,
    get_tax_settings,
    list_branches,
    log_user_activity,
    make_head_office,
    save_branch,
    save_company_and_settings,
    save_numbering_settings,
    save_tax_settings,
    set_branch_active,
)


def require_scope(request):
    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


@permission_required_custom("company_settings", "view")
def company_settings_view(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    company = get_company(company_id)
    if not company:
        messages.error(request, "Company record was not found.")
        return redirect("dashboard")

    settings = get_company_settings(company_id, branch_id) or {}
    form_data = {**company, **settings}
    errors = {}

    if request.method == "POST":
        if not _can(request, "company_settings", "edit"):
            return render(request, "errors/403.html", status=403)

        company_data = {
            field: request.POST.get(field, "").strip()
            for field in COMPANY_FIELDS
            if field != "is_active"
        }
        if request.POST.get("remove_logo") == "on":
            company_data["logo_path"] = ""
        elif request.FILES.get("logo_file"):
            try:
                company_data["logo_path"] = save_company_logo(request.FILES["logo_file"])
            except Exception as exc:
                errors["logo_file"] = str(exc)
        else:
            company_data["logo_path"] = company.get("logo_path") or company_data.get("logo_path", "")
        company_data["is_active"] = 1 if request.POST.get("is_active") == "on" else 0
        settings_data = {
            field: request.POST.get(field, "").strip()
            for field in COMPANY_SETTINGS_FIELDS
        }
        errors.update(validate_company_form(company_data, settings_data))
        form_data = {**company_data, **settings_data}

        if not errors:
            try:
                settings_id = save_company_and_settings(
                    company_id,
                    branch_id,
                    company_data,
                    settings_data,
                )
                request.session["company_name"] = company_data["company_name"]
                log_user_activity(
                    request,
                    "UPDATE",
                    "Company Settings",
                    "company_settings",
                    settings_id,
                    "Updated company settings from web app.",
                )
                messages.success(request, "Company settings saved successfully.")
                return redirect("settings_module:company")
            except DatabaseError:
                messages.error(request, "Unable to save company settings. Please try again.")

    return render(
        request,
        "settings/company_settings.html",
        {
            "page_title": "Company Settings",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "logo_url": get_company_logo_url(company_id),
        },
    )


@permission_required_custom("branches", "view")
def branches_list_view(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    branches = list_branches(company_id, search, status)
    return render(
        request,
        "settings/branches_list.html",
        {
            "page_title": "Branches",
            "branches": branches,
            "search": search,
            "status": status,
        },
    )


@login_required_custom
def branch_form_view(request, branch_id=None):
    company_id, current_branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    is_edit = branch_id is not None
    required_action = "edit" if is_edit else "add"
    if not _can(request, "branches", required_action):
        return render(request, "errors/403.html", status=403)

    branch = get_branch(company_id, branch_id) if is_edit else None
    if is_edit and not branch:
        messages.error(request, "Branch record was not found.")
        return redirect("settings_module:branches")

    form_data = branch or {
        "branch_code": "",
        "branch_name": "",
        "address": "",
        "phone": "",
        "mobile": "",
        "email": "",
        "is_head_office": 0,
        "is_active": 1,
    }
    errors = {}

    if request.method == "POST":
        form_data = {
            "branch_code": request.POST.get("branch_code", "").strip().upper(),
            "branch_name": request.POST.get("branch_name", "").strip(),
            "address": request.POST.get("address", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "mobile": request.POST.get("mobile", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "is_head_office": 1 if request.POST.get("is_head_office") == "on" else 0,
            "is_active": 1 if request.POST.get("is_active") == "on" else 0,
        }
        errors = validate_branch_form(company_id, form_data, branch_id)
        if is_edit and branch and int(branch.get("is_head_office") or 0) == 1 and not form_data["is_active"]:
            errors["is_active"] = "Head Office branch cannot be deactivated."
        if is_edit and branch and int(branch.get("is_active") or 0) == 1 and not form_data["is_active"]:
            if count_active_branches(company_id) <= 1:
                errors["is_active"] = "At least one active branch must remain."

        if not errors:
            try:
                saved_id = save_branch(
                    company_id,
                    form_data,
                    branch_id=branch_id,
                    current_user_id=request.session.get("user_id"),
                    is_master_user=int(request.session.get("is_master_user") or 0) == 1,
                )
                log_user_activity(
                    request,
                    "UPDATE" if is_edit else "CREATE",
                    "Branches",
                    "branches",
                    saved_id,
                    f"{'Updated' if is_edit else 'Created'} branch {form_data['branch_code']}.",
                )
                messages.success(request, "Branch saved successfully.")
                return redirect("settings_module:branches")
            except DatabaseError:
                messages.error(request, "Unable to save branch. Please try again.")

    return render(
        request,
        "settings/branch_form.html",
        {
            "page_title": "Edit Branch" if is_edit else "New Branch",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "is_edit": is_edit,
        },
    )


@permission_required_custom("branches", "edit")
def branch_toggle_active_view(request, branch_id):
    company_id, current_branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    branch = get_branch(company_id, branch_id)
    if not branch:
        messages.error(request, "Branch record was not found.")
        return redirect("settings_module:branches")

    new_state = 0 if int(branch.get("is_active") or 0) == 1 else 1
    if new_state == 0:
        if int(branch.get("is_head_office") or 0) == 1:
            messages.error(request, "Head Office branch cannot be deactivated.")
            return redirect("settings_module:branches")
        if count_active_branches(company_id) <= 1:
            messages.error(request, "At least one active branch must remain.")
            return redirect("settings_module:branches")

    try:
        set_branch_active(company_id, branch_id, new_state)
        log_user_activity(
            request,
            "ACTIVATE" if new_state else "DEACTIVATE",
            "Branches",
            "branches",
            branch_id,
            f"{'Activated' if new_state else 'Deactivated'} branch {branch['branch_code']}.",
        )
        messages.success(request, "Branch status updated.")
    except DatabaseError:
        messages.error(request, "Unable to update branch status.")
    return redirect("settings_module:branches")


@permission_required_custom("branches", "edit")
def branch_make_head_office_view(request, branch_id):
    company_id, current_branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    branch = get_branch(company_id, branch_id)
    if not branch:
        messages.error(request, "Branch record was not found.")
        return redirect("settings_module:branches")

    try:
        make_head_office(company_id, branch_id)
        log_user_activity(
            request,
            "UPDATE",
            "Branches",
            "branches",
            branch_id,
            f"Marked branch {branch['branch_code']} as Head Office.",
        )
        messages.success(request, "Head Office branch updated.")
    except DatabaseError:
        messages.error(request, "Unable to update Head Office branch.")
    return redirect("settings_module:branches")


@permission_required_custom("numbering_settings", "view")
def numbering_settings_view(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    settings = get_numbering_settings(company_id, branch_id)
    form_data = settings.copy()
    errors = {}

    if request.method == "POST":
        if not _can(request, "numbering_settings", "edit"):
            return render(request, "errors/403.html", status=403)
        form_data = {
            field: request.POST.get(field, "").strip()
            for field in NUMBERING_FIELDS
            if field not in {"use_year_in_number", "number_padding"}
        }
        form_data["use_year_in_number"] = 1 if request.POST.get("use_year_in_number") == "on" else 0
        form_data["number_padding"] = request.POST.get("number_padding", "").strip()
        errors = validate_numbering_form(form_data)
        if not errors:
            form_data["number_padding"] = int(form_data["number_padding"])
            try:
                row_id = save_numbering_settings(company_id, branch_id, form_data)
                log_user_activity(
                    request,
                    "UPDATE",
                    "Numbering Settings",
                    "numbering_settings",
                    row_id,
                    "Updated numbering settings from web app.",
                )
                messages.success(request, "Numbering settings saved successfully.")
                return redirect("settings_module:numbering")
            except DatabaseError:
                messages.error(request, "Unable to save numbering settings.")

    return render(
        request,
        "settings/numbering_settings.html",
        {
            "page_title": "Numbering Settings",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "numbering_sections": NUMBERING_SECTIONS,
        },
    )


@permission_required_custom("tax_settings", "view")
def tax_settings_view(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    settings = get_tax_settings(company_id, branch_id)
    form_data = settings.copy()
    errors = {}

    if request.method == "POST":
        if not _can(request, "tax_settings", "edit"):
            return render(request, "errors/403.html", status=403)
        form_data = {
            "default_sales_tax_percent": request.POST.get("default_sales_tax_percent", "").strip(),
            "default_input_tax_percent": request.POST.get("default_input_tax_percent", "").strip(),
            "default_tax_applicable": 1 if request.POST.get("default_tax_applicable") == "on" else 0,
            "tax_invoice_label": request.POST.get("tax_invoice_label", "").strip(),
            "show_ntn_on_invoice": 1 if request.POST.get("show_ntn_on_invoice") == "on" else 0,
            "show_strn_on_invoice": 1 if request.POST.get("show_strn_on_invoice") == "on" else 0,
        }
        errors = validate_tax_form(form_data)
        if not errors:
            form_data["default_sales_tax_percent"] = str(form_data["default_sales_tax_percent"])
            form_data["default_input_tax_percent"] = str(form_data["default_input_tax_percent"])
            try:
                row_id = save_tax_settings(company_id, branch_id, form_data)
                log_user_activity(
                    request,
                    "UPDATE",
                    "Tax Settings",
                    "tax_settings",
                    row_id,
                    "Updated tax settings from web app.",
                )
                messages.success(request, "Tax settings saved successfully.")
                return redirect("settings_module:tax")
            except DatabaseError:
                messages.error(request, "Unable to save tax settings.")

    return render(
        request,
        "settings/tax_settings.html",
        {
            "page_title": "Tax Settings",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
        },
    )


def _can(request, permission_code, action):
    return user_has_permission(request, permission_code, action)


def validate_company_form(data, settings_data):
    errors = {}
    text_limits = {
        "company_name": 200,
        "legal_name": 200,
        "phone": 30,
        "mobile": 30,
        "email": 254,
        "website": 200,
        "ntn": 100,
        "strn": 100,
        "logo_path": 500,
    }
    for field, max_length in text_limits.items():
        data[field], error = form_validators.clean_text(
            data.get(field),
            max_length=max_length,
            required=field == "company_name",
            field_name=field_label(field),
        )
        if error:
            errors[field] = error
    data["phone"], error = form_validators.validate_phone(data.get("phone"), "Phone")
    if error:
        errors["phone"] = error
    data["mobile"], error = form_validators.validate_mobile(data.get("mobile"), "Mobile")
    if error:
        errors["mobile"] = error
    data["email"], error = form_validators.validate_email(data.get("email"), "Email")
    if error:
        errors["email"] = error
    data["website"], error = form_validators.validate_website(data.get("website"), "Website")
    if error:
        errors["website"] = error
    settings_data["authorized_person_name"], error = form_validators.clean_text(
        settings_data.get("authorized_person_name"),
        max_length=150,
        field_name="Authorized Person Name",
    )
    if error:
        errors["authorized_person_name"] = error
    return errors


def validate_branch_form(company_id, data, branch_id=None):
    errors = {}
    text_limits = {
        "branch_code": 50,
        "branch_name": 150,
        "phone": 30,
        "mobile": 30,
        "email": 254,
    }
    for field, max_length in text_limits.items():
        data[field], error = form_validators.clean_text(
            data.get(field),
            max_length=max_length,
            required=field in {"branch_code", "branch_name"},
            field_name=field_label(field),
        )
        if error:
            errors[field] = error
    if data.get("branch_code") and branch_code_exists(company_id, data["branch_code"], branch_id):
        errors["branch_code"] = "Branch code must be unique within this company."
    data["phone"], error = form_validators.validate_phone(data.get("phone"), "Phone")
    if error:
        errors["phone"] = error
    data["mobile"], error = form_validators.validate_mobile(data.get("mobile"), "Mobile")
    if error:
        errors["mobile"] = error
    data["email"], error = form_validators.validate_email(data.get("email"), "Email")
    if error:
        errors["email"] = error
    return errors


def validate_numbering_form(data):
    errors = {}
    for field in NUMBERING_FIELDS:
        if field in {"use_year_in_number", "number_padding"}:
            continue
        data[field], error = form_validators.clean_text(
            data.get(field),
            max_length=20,
            required=True,
            field_name=field_label(field),
        )
        if error:
            errors[field] = error
    padding, error = form_validators.validate_integer(
        data.get("number_padding"),
        "Number Padding",
        min_value=3,
        max_value=8,
        required=True,
    )
    if error:
        errors["number_padding"] = error
    else:
        data["number_padding"] = padding
    return errors


def validate_tax_form(data):
    errors = {}
    for field in ["default_sales_tax_percent", "default_input_tax_percent"]:
        value, error = form_validators.validate_percentage(data.get(field), field_label(field))
        if error:
            errors[field] = error
        else:
            data[field] = value
    if data.get("default_tax_applicable") and not data.get("tax_invoice_label"):
        errors["tax_invoice_label"] = "Tax invoice label is required when tax is applicable."
    data["tax_invoice_label"], error = form_validators.clean_text(
        data.get("tax_invoice_label"),
        max_length=100,
        required=bool(data.get("default_tax_applicable")),
        field_name="Tax Invoice Label",
    )
    if error:
        errors["tax_invoice_label"] = error
    return errors


def field_label(field_name):
    labels = {
        "company_name": "Company Name",
        "legal_name": "Legal Name",
        "logo_path": "Logo Path",
        "authorized_person_name": "Authorized Person Name",
        "branch_code": "Branch Code",
        "branch_name": "Branch Name",
        "number_padding": "Number Padding",
        "default_sales_tax_percent": "Default Sales Tax Percent",
        "default_input_tax_percent": "Default Input Tax Percent",
        "tax_invoice_label": "Tax Invoice Label",
    }
    if field_name.endswith("_prefix"):
        return field_name.replace("_", " ").title()
    return labels.get(field_name, field_name.replace("_", " ").title())


NUMBERING_SECTIONS = [
    ("Masters", ["customer_prefix", "supplier_prefix", "item_prefix"]),
    (
        "Sales",
        [
            "quotation_prefix",
            "confirmation_prefix",
            "delivery_challan_prefix",
            "invoice_prefix",
            "sales_return_prefix",
            "cash_memo_prefix",
            "receipt_prefix",
        ],
    ),
    (
        "Purchases",
        ["purchase_prefix", "purchase_return_prefix", "supplier_payment_prefix"],
    ),
    ("Services", ["service_contract_prefix"]),
    ("Expenses", ["expense_voucher_prefix"]),
]
