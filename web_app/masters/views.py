from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError, connection, transaction
from django.shortcuts import redirect, render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from core import validators as form_validators
from settings_module.services import log_user_activity

from .master_utils import (
    clean_bool,
    clean_text,
    create_linked_account,
    future_reference_exists,
    get_active_payment_terms,
    get_current_branch_id,
    get_current_company_id,
    get_record,
    insert_record,
    linked_account_has_journal_entries,
    list_records,
    payment_term_exists,
    set_record_active,
    update_linked_account_name,
    update_record,
)


MASTER_CARDS = [
    ("Customers", "customers", "masters:customers", "bi-people", "Customer master records and receivables accounts."),
    ("Suppliers", "suppliers", "masters:suppliers", "bi-truck", "Supplier records and payable accounts."),
    ("Items / Services", "item_services", "masters:items", "bi-box-seam", "Products and services without inventory tracking."),
    ("Cash / Bank Accounts", "cash_bank_accounts", "masters:cash_bank", "bi-bank", "Cash and bank ledgers linked to accounts."),
    ("Expense Heads", "expense_heads", "masters:expense_heads", "bi-wallet2", "Expense categories linked to expense accounts."),
    ("Payment Terms", "payment_terms", "masters:payment_terms", "bi-calendar-check", "Reusable customer payment terms."),
]


CONFIGS = {
    "customers": {
        "permission": "customers",
        "title": "Customers",
        "singular": "Customer",
        "table": "customers",
        "code_field": "customer_code",
        "name_field": "company_name",
        "fields": [
            "customer_code",
            "company_name",
            "contact_person",
            "phone",
            "mobile",
            "email",
            "address",
            "ntn",
            "strn",
            "payment_terms_id",
            "credit_limit",
            "opening_balance",
            "opening_balance_type",
            "account_id",
            "is_active",
            "remarks",
        ],
        "select_sql": "customers.*, payment_terms.name AS payment_terms_name",
        "joins": "LEFT JOIN payment_terms ON payment_terms.id = customers.payment_terms_id",
        "search_fields": ["customer_code", "company_name", "contact_person", "phone", "email"],
        "order_by": "company_name ASC",
        "list_template": "masters/customers_list.html",
        "form_template": "masters/customer_form.html",
    },
    "suppliers": {
        "permission": "suppliers",
        "title": "Suppliers",
        "singular": "Supplier",
        "table": "suppliers",
        "code_field": "supplier_code",
        "name_field": "supplier_name",
        "fields": [
            "supplier_code",
            "supplier_name",
            "contact_person",
            "phone",
            "mobile",
            "email",
            "address",
            "ntn",
            "strn",
            "opening_balance",
            "opening_balance_type",
            "account_id",
            "is_active",
            "remarks",
        ],
        "select_sql": "suppliers.*",
        "search_fields": ["supplier_code", "supplier_name", "contact_person", "phone", "email"],
        "order_by": "supplier_name ASC",
        "list_template": "masters/suppliers_list.html",
        "form_template": "masters/supplier_form.html",
    },
    "items": {
        "permission": "item_services",
        "title": "Items / Services",
        "singular": "Item / Service",
        "table": "item_services",
        "code_field": "item_code",
        "name_field": "item_name",
        "fields": [
            "item_code",
            "item_name",
            "item_type",
            "category",
            "default_purchase_rate",
            "default_sale_rate",
            "default_tax_rate",
            "track_inventory",
            "unit",
            "minimum_stock_level",
            "opening_stock",
            "opening_cost",
            "warranty_or_service_description",
            "is_active",
            "remarks",
        ],
        "select_sql": "item_services.*",
        "search_fields": ["item_code", "item_name", "item_type", "category"],
        "order_by": "item_name ASC",
        "list_template": "masters/items_list.html",
        "form_template": "masters/item_form.html",
    },
    "cash_bank": {
        "permission": "cash_bank_accounts",
        "title": "Cash / Bank Accounts",
        "singular": "Cash / Bank Account",
        "table": "cash_bank_accounts",
        "name_field": "account_name",
        "fields": [
            "account_name",
            "account_type",
            "bank_name",
            "account_number",
            "branch",
            "iban",
            "opening_balance",
            "account_id",
            "is_active",
            "remarks",
        ],
        "select_sql": "cash_bank_accounts.*",
        "search_fields": ["account_name", "account_type", "bank_name", "account_number"],
        "order_by": "account_name ASC",
        "list_template": "masters/cash_bank_list.html",
        "form_template": "masters/cash_bank_form.html",
    },
    "expense_heads": {
        "permission": "expense_heads",
        "title": "Expense Heads",
        "singular": "Expense Head",
        "table": "expense_heads",
        "code_field": "expense_code",
        "name_field": "expense_name",
        "fields": [
            "expense_code",
            "expense_name",
            "category",
            "account_id",
            "is_active",
            "remarks",
        ],
        "select_sql": "expense_heads.*",
        "search_fields": ["expense_code", "expense_name", "category"],
        "order_by": "expense_name ASC",
        "list_template": "masters/expense_heads_list.html",
        "form_template": "masters/expense_head_form.html",
    },
    "payment_terms": {
        "permission": "payment_terms",
        "title": "Payment Terms",
        "singular": "Payment Term",
        "table": "payment_terms",
        "name_field": "name",
        "fields": ["name", "days", "description", "is_active"],
        "select_sql": "payment_terms.*",
        "search_fields": ["name", "description"],
        "order_by": "name ASC",
        "list_template": "masters/payment_terms_list.html",
        "form_template": "masters/payment_term_form.html",
    },
}


@login_required_custom
def index(request):
    cards = []
    for label, permission, url_name, icon, description in MASTER_CARDS:
        if user_has_permission(request, permission, "view"):
            cards.append(
                {
                    "label": label,
                    "url_name": url_name,
                    "icon": icon,
                    "description": description,
                }
            )
    return render(
        request,
        "masters/index.html",
        {"page_title": "Masters", "master_cards": cards},
    )


def list_view(request, key):
    config = CONFIGS[key]
    if not user_has_permission(request, config["permission"], "view"):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "active").strip()
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    rows, pagination = list_records(config, company_id, branch_id, search, status, page)
    return render(
        request,
        config["list_template"],
        {
            "page_title": config["title"],
            "config": config,
            "rows": rows,
            "search": search,
            "status": status,
            "pagination": pagination,
            "can_add": user_has_permission(request, config["permission"], "add"),
            "can_edit": user_has_permission(request, config["permission"], "edit"),
            "can_toggle": can_toggle(request, config["permission"]),
        },
    )


def form_view(request, key, record_id=None):
    config = CONFIGS[key]
    is_edit = record_id is not None
    action = "edit" if is_edit else "add"
    if not user_has_permission(request, config["permission"], action):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")

    record = get_record(config, company_id, branch_id, record_id) if is_edit else None
    if is_edit and not record:
        messages.error(request, f"{config['singular']} record was not found.")
        return redirect(list_url_name(key))

    form_data = record or default_form_data(key)
    errors = {}
    warnings = []
    payment_terms = get_active_payment_terms(company_id, branch_id) if key == "customers" else []

    if request.method == "POST":
        form_data = parse_form_data(request, key)
        errors, warnings = validate_form_data(config, key, form_data, company_id, branch_id, record_id)
        if not errors:
            try:
                with transaction.atomic():
                    if is_edit:
                        save_existing_record(config, key, company_id, branch_id, request, record_id, form_data, record)
                        log_user_activity(
                            request,
                            "UPDATE",
                            config["title"],
                            config["table"],
                            record_id,
                            f"Updated {config['singular'].lower()}.",
                        )
                        messages.success(request, f"{config['singular']} updated successfully.")
                    else:
                        new_id = save_new_record(config, key, company_id, branch_id, request, form_data)
                        log_user_activity(
                            request,
                            "CREATE",
                            config["title"],
                            config["table"],
                            new_id,
                            f"Created {config['singular'].lower()}.",
                        )
                        messages.success(request, f"{config['singular']} created successfully.")
                for warning in warnings:
                    messages.warning(request, warning)
                return redirect(list_url_name(key))
            except ValueError as exc:
                messages.error(request, str(exc))
            except DatabaseError:
                messages.error(request, f"Unable to save {config['singular'].lower()}. Please try again.")
        else:
            messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        config["form_template"],
        {
            "page_title": f"{'Edit' if is_edit else 'New'} {config['singular']}",
            "config": config,
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "warnings": warnings,
            "is_edit": is_edit,
            "payment_terms": payment_terms,
        },
    )


def toggle_active_view(request, key, record_id):
    config = CONFIGS[key]
    if not can_toggle(request, config["permission"]):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    record = get_record(config, company_id, branch_id, record_id)
    if not record:
        messages.error(request, f"{config['singular']} record was not found.")
        return redirect(list_url_name(key))
    new_state = 0 if int(record.get("is_active") or 0) == 1 else 1
    if new_state == 0:
        block_reason = deactivation_block_reason(key, record)
        if block_reason:
            messages.error(request, block_reason)
            return redirect(list_url_name(key))
    try:
        set_record_active(config, company_id, branch_id, request.session.get("user_id"), record_id, new_state)
        log_user_activity(
            request,
            "ACTIVATE" if new_state else "DEACTIVATE",
            config["title"],
            config["table"],
            record_id,
            f"{'Activated' if new_state else 'Deactivated'} {config['singular'].lower()}.",
        )
        messages.success(request, f"{config['singular']} {'activated' if new_state else 'deactivated'} successfully.")
    except DatabaseError:
        messages.error(request, f"Unable to update {config['singular'].lower()} status.")
    return redirect(list_url_name(key))


@permission_required_custom("customers", "view")
def customers(request):
    return list_view(request, "customers")


def customer_form(request, record_id=None):
    return form_view(request, "customers", record_id)


def customer_toggle(request, record_id):
    return toggle_active_view(request, "customers", record_id)


@permission_required_custom("suppliers", "view")
def suppliers(request):
    return list_view(request, "suppliers")


def supplier_form(request, record_id=None):
    return form_view(request, "suppliers", record_id)


def supplier_toggle(request, record_id):
    return toggle_active_view(request, "suppliers", record_id)


@permission_required_custom("item_services", "view")
def items(request):
    return list_view(request, "items")


def item_form(request, record_id=None):
    return form_view(request, "items", record_id)


def item_toggle(request, record_id):
    return toggle_active_view(request, "items", record_id)


@permission_required_custom("cash_bank_accounts", "view")
def cash_bank(request):
    return list_view(request, "cash_bank")


def cash_bank_form(request, record_id=None):
    return form_view(request, "cash_bank", record_id)


def cash_bank_toggle(request, record_id):
    return toggle_active_view(request, "cash_bank", record_id)


@permission_required_custom("expense_heads", "view")
def expense_heads(request):
    return list_view(request, "expense_heads")


def expense_head_form(request, record_id=None):
    return form_view(request, "expense_heads", record_id)


def expense_head_toggle(request, record_id):
    return toggle_active_view(request, "expense_heads", record_id)


@permission_required_custom("payment_terms", "view")
def payment_terms(request):
    return list_view(request, "payment_terms")


def payment_term_form(request, record_id=None):
    return form_view(request, "payment_terms", record_id)


def payment_term_toggle(request, record_id):
    return toggle_active_view(request, "payment_terms", record_id)


def require_scope(request):
    company_id = get_current_company_id(request)
    branch_id = get_current_branch_id(request)
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


def can_toggle(request, permission):
    return user_has_permission(request, permission, "delete") or user_has_permission(request, permission, "edit")


def list_url_name(key):
    mapping = {
        "customers": "masters:customers",
        "suppliers": "masters:suppliers",
        "items": "masters:items",
        "cash_bank": "masters:cash_bank",
        "expense_heads": "masters:expense_heads",
        "payment_terms": "masters:payment_terms",
    }
    return mapping[key]


def deactivation_block_reason(key, record):
    if key == "cash_bank" and linked_account_has_journal_entries(record.get("account_id")):
        return "This cash/bank account has journal entries and cannot be deactivated."
    if key in {"customers", "suppliers"} and future_reference_exists(key, record.get("id")):
        return f"This {key[:-1]} has transaction references and cannot be deactivated."
    return None


def default_form_data(key):
    defaults = {"is_active": 1, "opening_balance": "0", "remarks": ""}
    if key == "customers":
        return {**defaults, "credit_limit": "0", "opening_balance_type": "Debit"}
    if key == "suppliers":
        return {**defaults, "opening_balance_type": "Credit"}
    if key == "items":
        return {
            **defaults,
            "item_type": "Product",
            "default_purchase_rate": "0",
            "default_sale_rate": "0",
            "default_tax_rate": "0",
            "track_inventory": 1,
            "unit": "",
            "minimum_stock_level": "0",
            "opening_stock": "0",
            "opening_cost": "0",
        }
    if key == "cash_bank":
        return {**defaults, "account_type": "Cash"}
    if key == "payment_terms":
        return {**defaults, "days": "0"}
    return defaults


def parse_form_data(request, key):
    if key == "customers":
        return {
            "customer_code": clean_text(request, "customer_code").upper(),
            "company_name": clean_text(request, "company_name"),
            "contact_person": clean_text(request, "contact_person"),
            "phone": clean_text(request, "phone"),
            "mobile": clean_text(request, "mobile"),
            "email": clean_text(request, "email"),
            "address": clean_text(request, "address"),
            "ntn": clean_text(request, "ntn"),
            "strn": clean_text(request, "strn"),
            "payment_terms_id": request.POST.get("payment_terms_id") or None,
            "credit_limit": clean_text(request, "credit_limit") or "0",
            "opening_balance": clean_text(request, "opening_balance") or "0",
            "opening_balance_type": clean_text(request, "opening_balance_type") or "Debit",
            "account_id": request.POST.get("account_id") or None,
            "is_active": clean_bool(request, "is_active", True),
            "remarks": clean_text(request, "remarks"),
        }
    if key == "suppliers":
        return {
            "supplier_code": clean_text(request, "supplier_code").upper(),
            "supplier_name": clean_text(request, "supplier_name"),
            "contact_person": clean_text(request, "contact_person"),
            "phone": clean_text(request, "phone"),
            "mobile": clean_text(request, "mobile"),
            "email": clean_text(request, "email"),
            "address": clean_text(request, "address"),
            "ntn": clean_text(request, "ntn"),
            "strn": clean_text(request, "strn"),
            "opening_balance": clean_text(request, "opening_balance") or "0",
            "opening_balance_type": clean_text(request, "opening_balance_type") or "Credit",
            "account_id": request.POST.get("account_id") or None,
            "is_active": clean_bool(request, "is_active", True),
            "remarks": clean_text(request, "remarks"),
        }
    if key == "items":
        return {
            "item_code": clean_text(request, "item_code").upper(),
            "item_name": clean_text(request, "item_name"),
            "item_type": clean_text(request, "item_type") or "Product",
            "category": clean_text(request, "category"),
            "default_purchase_rate": clean_text(request, "default_purchase_rate") or "0",
            "default_sale_rate": clean_text(request, "default_sale_rate") or "0",
            "default_tax_rate": clean_text(request, "default_tax_rate") or "0",
            "track_inventory": clean_bool(request, "track_inventory", True),
            "unit": clean_text(request, "unit"),
            "minimum_stock_level": clean_text(request, "minimum_stock_level") or "0",
            "opening_stock": clean_text(request, "opening_stock") or "0",
            "opening_cost": clean_text(request, "opening_cost") or "0",
            "warranty_or_service_description": clean_text(request, "warranty_or_service_description"),
            "is_active": clean_bool(request, "is_active", True),
            "remarks": clean_text(request, "remarks"),
        }
    if key == "cash_bank":
        return {
            "account_name": clean_text(request, "account_name"),
            "account_type": clean_text(request, "account_type") or "Cash",
            "bank_name": clean_text(request, "bank_name"),
            "account_number": clean_text(request, "account_number"),
            "branch": clean_text(request, "branch"),
            "iban": clean_text(request, "iban"),
            "opening_balance": clean_text(request, "opening_balance") or "0",
            "account_id": request.POST.get("account_id") or None,
            "is_active": clean_bool(request, "is_active", True),
            "remarks": clean_text(request, "remarks"),
        }
    if key == "expense_heads":
        return {
            "expense_code": clean_text(request, "expense_code").upper(),
            "expense_name": clean_text(request, "expense_name"),
            "category": clean_text(request, "category"),
            "account_id": request.POST.get("account_id") or None,
            "is_active": clean_bool(request, "is_active", True),
            "remarks": clean_text(request, "remarks"),
        }
    return {
        "name": clean_text(request, "name"),
        "days": clean_text(request, "days") or "0",
        "description": clean_text(request, "description"),
        "is_active": clean_bool(request, "is_active", True),
    }


def validate_form_data(config, key, data, company_id, branch_id, record_id=None):
    errors = {}
    warnings = []
    for field, max_length in field_limits(key).items():
        if field in data:
            cleaned, error = form_validators.clean_text(data.get(field), max_length=max_length, field_name=field_label(field))
            data[field] = cleaned
            if error:
                errors[field] = error

    code_field = config.get("code_field")
    name_field = config.get("name_field")
    if code_field:
        error = form_validators.validate_required(data.get(code_field), field_label(code_field))
        if error:
            errors[code_field] = error
    if name_field:
        error = form_validators.validate_required(data.get(name_field), field_label(name_field))
        if error:
            errors[name_field] = error
    unique_field = code_field or name_field
    if unique_field and data.get(unique_field):
        duplicate_error = form_validators.validate_unique_code(
            connection,
            config["table"],
            unique_field,
            data[unique_field],
            company_id,
            branch_id,
            record_id,
        )
        if duplicate_error:
            errors[unique_field] = duplicate_error

    if "phone" in data:
        data["phone"], phone_error = form_validators.validate_phone(data.get("phone"), "Phone")
        if phone_error:
            errors["phone"] = phone_error
    if "mobile" in data:
        data["mobile"], mobile_error = form_validators.validate_mobile(data.get("mobile"), "Mobile")
        if mobile_error:
            errors["mobile"] = mobile_error
    if "email" in data:
        data["email"], email_error = form_validators.validate_email(data.get("email"), "Email")
        if email_error:
            errors["email"] = email_error

    for field in ["credit_limit", "opening_balance", "default_purchase_rate", "default_sale_rate", "minimum_stock_level", "opening_stock", "opening_cost"]:
        if field in data:
            amount, error = form_validators.validate_money(data[field], field_label(field), allow_negative=False)
            if error:
                errors[field] = error
            else:
                data[field] = str(amount)

    if "default_tax_rate" in data:
        amount, error = form_validators.validate_percentage(data["default_tax_rate"], "Tax Rate")
        if error:
            errors["default_tax_rate"] = error
        else:
            data["default_tax_rate"] = str(amount)

    if key in {"customers", "suppliers"}:
        choice_error = form_validators.validate_choice(data.get("opening_balance_type"), ["Debit", "Credit"], "Opening Balance Type")
        if choice_error:
            errors["opening_balance_type"] = choice_error

    if key == "customers" and data.get("payment_terms_id") and not payment_term_exists(company_id, branch_id, data["payment_terms_id"]):
        errors["payment_terms_id"] = "Selected payment terms were not found."

    if key == "items":
        choice_error = form_validators.validate_choice(data.get("item_type"), ["Product", "Service"], "Item Type")
        if choice_error:
            errors["item_type"] = choice_error
        else:
            data["item_type"] = data["item_type"].title()
            if data["item_type"] == "Service":
                data["track_inventory"] = 0

    if key == "cash_bank":
        choice_error = form_validators.validate_choice(data.get("account_type"), ["Cash", "Bank"], "Account Type")
        if choice_error:
            errors["account_type"] = choice_error
        else:
            data["account_type"] = data["account_type"].title()
        if str(data.get("account_type", "")).lower() == "bank" and not data.get("bank_name"):
            warnings.append("Bank name is recommended for bank accounts.")

    if key == "payment_terms":
        days, error = form_validators.validate_integer(data.get("days"), "Days", min_value=0)
        if error:
            errors["days"] = error
        else:
            data["days"] = days
    return errors, warnings


def field_label(field_name):
    labels = {
        "customer_code": "Customer Code",
        "company_name": "Company Name",
        "supplier_code": "Supplier Code",
        "supplier_name": "Supplier Name",
        "item_code": "Item Code",
        "item_name": "Item Name",
        "account_name": "Account Name",
        "expense_code": "Expense Code",
        "expense_name": "Expense Name",
        "name": "Name",
        "credit_limit": "Credit Limit",
        "opening_balance": "Opening Balance",
        "default_purchase_rate": "Default Purchase Rate",
        "default_sale_rate": "Default Sale Rate",
    }
    return labels.get(field_name, field_name.replace("_", " ").title())


def field_limits(key):
    limits = {
        "customers": {
            "customer_code": 50,
            "company_name": 200,
            "contact_person": 150,
            "phone": 30,
            "mobile": 30,
            "email": 254,
            "ntn": 100,
            "strn": 100,
        },
        "suppliers": {
            "supplier_code": 50,
            "supplier_name": 200,
            "contact_person": 150,
            "phone": 30,
            "mobile": 30,
            "email": 254,
            "ntn": 100,
            "strn": 100,
        },
        "items": {
            "item_code": 50,
            "item_name": 200,
            "category": 100,
            "unit": 50,
        },
        "cash_bank": {
            "account_name": 150,
            "bank_name": 150,
            "account_number": 100,
            "branch": 150,
            "iban": 100,
        },
        "expense_heads": {
            "expense_code": 50,
            "expense_name": 150,
            "category": 100,
        },
        "payment_terms": {
            "name": 100,
        },
    }
    return limits.get(key, {})


def save_new_record(config, key, company_id, branch_id, request, data):
    data = data.copy()
    apply_linked_account_for_create(key, company_id, branch_id, data)
    return insert_record(config, company_id, branch_id, request.session.get("user_id"), data)


def save_existing_record(config, key, company_id, branch_id, request, record_id, data, existing):
    data = data.copy()
    if key in {"customers", "suppliers", "cash_bank", "expense_heads"}:
        account_id = existing.get("account_id")
        data["account_id"] = account_id
        account_name = linked_account_name(key, data)
        update_linked_account_name(account_id, company_id, branch_id, account_name)
    update_record(config, company_id, branch_id, request.session.get("user_id"), record_id, data)


def apply_linked_account_for_create(key, company_id, branch_id, data):
    if key == "customers":
        data["account_id"] = create_linked_account(
            company_id,
            branch_id,
            f"AR-{data['customer_code']}",
            data["company_name"],
            "Assets",
            "Accounts Receivable",
        )
    elif key == "suppliers":
        data["account_id"] = create_linked_account(
            company_id,
            branch_id,
            f"AP-{data['supplier_code']}",
            data["supplier_name"],
            "Liabilities",
            "Accounts Payable",
        )
    elif key == "cash_bank":
        account_type = str(data["account_type"]).lower()
        prefix = "CASH" if account_type == "cash" else "BANK"
        parent = "Cash" if account_type == "cash" else "Bank"
        data["account_id"] = create_linked_account(
            company_id,
            branch_id,
            f"{prefix}-{data['account_name'].replace(' ', '-')[:24]}",
            data["account_name"],
            "Assets",
            parent,
        )
    elif key == "expense_heads":
        data["account_id"] = create_linked_account(
            company_id,
            branch_id,
            f"EXP-{data['expense_code']}",
            data["expense_name"],
            "Expenses",
            "Office Expenses",
        )


def linked_account_name(key, data):
    if key == "customers":
        return data["company_name"]
    if key == "suppliers":
        return data["supplier_name"]
    if key == "cash_bank":
        return data["account_name"]
    if key == "expense_heads":
        return data["expense_name"]
    return ""
