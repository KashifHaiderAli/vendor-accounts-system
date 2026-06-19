from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import redirect, render

from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from core.classic_print_settings import get_classic_print_settings, set_classic_print_settings
from core.logo_utils import get_company_logo_url, save_company_logo
from core import validators as form_validators
from core.audit_utils import log_activity
from core.edition_utils import can_change_tax_enabled, env_tax_enabled, is_tax_enabled, set_tax_enabled
from core.inventory_utils import is_inventory_enabled, set_inventory_enabled, set_stock_reduce_on, stock_reduce_on

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
from . import user_role_services


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
    classic_print_settings = get_classic_print_settings(company_id, branch_id)
    form_data = {**company, **settings, **classic_print_settings}
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
        classic_settings_data = {
            "classic_header_color": request.POST.get("classic_header_color", "").strip(),
            "classic_header_alignment": request.POST.get("classic_header_alignment", "").strip(),
            "classic_company_name_font_size": request.POST.get("classic_company_name_font_size", "").strip(),
            "classic_company_address_font_size": request.POST.get("classic_company_address_font_size", "").strip(),
        }
        errors.update(validate_company_form(company_data, settings_data))
        form_data = {**company_data, **settings_data, **classic_settings_data}

        if not errors:
            try:
                settings_id = save_company_and_settings(
                    company_id,
                    branch_id,
                    company_data,
                    settings_data,
                )
                saved_classic_settings = set_classic_print_settings(
                    company_id,
                    branch_id,
                    classic_settings_data.get("classic_header_color"),
                    classic_settings_data.get("classic_header_alignment"),
                    classic_settings_data.get("classic_company_name_font_size"),
                    classic_settings_data.get("classic_company_address_font_size"),
                )
                form_data.update(saved_classic_settings)
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


@login_required_custom
def inventory_settings_view(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    if not (user_has_permission(request, "company_settings", "edit") or int(request.session.get("is_master_user") or 0) == 1):
        return render(request, "errors/403.html", status=403)

    if request.method == "POST":
        enabled = request.POST.get("enable_inventory_tracking") == "on"
        reduce_on = request.POST.get("stock_reduce_on") or "delivery_challan"
        set_inventory_enabled(enabled)
        set_stock_reduce_on(reduce_on)
        log_user_activity(request, "UPDATE", "Inventory Settings", "inventory_settings", None, "Updated inventory tracking settings.")
        messages.success(request, "Inventory settings saved successfully.")
        return redirect("settings_module:inventory")

    return render(
        request,
        "settings/inventory_settings.html",
        {
            "page_title": "Inventory Settings",
            "enable_inventory_tracking": is_inventory_enabled(company_id),
            "stock_reduce_on": stock_reduce_on(),
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


@login_required_custom
def users_roles_placeholder_view(request):
    if not can_manage_users(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    search = request.GET.get("q", "").strip()
    users = user_role_services.list_users(company_id, search)
    return render(request, "settings/users_roles_list.html", {"page_title": "Users & Roles", "users": users, "search": search})


@login_required_custom
def role_management_placeholder_view(request):
    if not can_manage_roles(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    roles = user_role_services.list_roles(company_id, include_inactive=True)
    return render(request, "settings/roles_list.html", {"page_title": "Role Management", "roles": roles})


@login_required_custom
def user_form_view(request, user_id=None):
    if not can_manage_users(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_master_session = int(request.session.get("is_master_user") or 0) == 1
    user = user_role_services.get_user(company_id, user_id) if user_id else None
    if user_id and not user:
        messages.error(request, "User was not found.")
        return redirect("settings_module:users_roles")
    if user and int(user.get("is_master_user") or 0) == 1 and not is_master_session:
        return render(request, "errors/403.html", status=403)
    branches = user_role_services.list_branches(company_id)
    roles = user_role_services.list_roles(company_id)
    selected_branches = user_role_services.user_branch_ids(user_id) if user_id else [branch_id]
    form_data = user or {
        "username": "",
        "full_name": "",
        "email": "",
        "mobile": "",
        "role_id": "",
        "default_branch_id": branch_id,
        "is_master_user": 0,
        "is_active": 1,
    }
    errors = {}
    if request.method == "POST":
        selected_branches = request.POST.getlist("branch_ids")
        form_data = {
            "username": request.POST.get("username", "").strip(),
            "full_name": request.POST.get("full_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "mobile": request.POST.get("mobile", "").strip(),
            "role_id": request.POST.get("role_id", "").strip(),
            "default_branch_id": request.POST.get("default_branch_id") or (selected_branches[0] if selected_branches else None),
            "is_master_user": 1 if is_master_session and request.POST.get("is_master_user") == "on" else 0,
            "is_active": 1 if request.POST.get("is_active") == "on" else 0,
            "password": request.POST.get("password", ""),
        }
        errors = validate_user_form(company_id, form_data, selected_branches, user_id, request, user)
        if not errors:
            saved_id = user_role_services.save_user(company_id, form_data, selected_branches, user_id)
            log_activity(action="UPDATE" if user_id else "CREATE", module="Users & Roles", record_type="users", record_id=saved_id, description=f"{'Updated' if user_id else 'Created'} user {form_data['username']}.", request=request)
            if not user_id:
                messages.success(request, f"User created. Temporary password assigned: {user_role_services.TEMP_PASSWORD}")
            else:
                messages.success(request, "User updated successfully.")
            return redirect("settings_module:users_roles")
    return render(
        request,
        "settings/user_form.html",
        {
            "page_title": "Edit User" if user_id else "Add User",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "roles": roles,
            "branches": branches,
            "selected_branches": [str(value) for value in selected_branches],
            "is_master_session": is_master_session,
            "is_edit": bool(user_id),
        },
    )


@login_required_custom
def user_toggle_active_view(request, user_id):
    if not can_manage_users(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    user = user_role_services.get_user(company_id, user_id)
    if not user:
        messages.error(request, "User was not found.")
        return redirect("settings_module:users_roles")
    if int(user_id) == int(request.session.get("user_id") or 0):
        messages.error(request, "You cannot deactivate your own user.")
        return redirect("settings_module:users_roles")
    new_state = 0 if int(user.get("is_active") or 0) == 1 else 1
    user_role_services.toggle_user_active(user_id, new_state)
    log_activity(action="ACTIVATE" if new_state else "DEACTIVATE", module="Users & Roles", record_type="users", record_id=user_id, description=f"{'Activated' if new_state else 'Deactivated'} user {user['username']}.", request=request)
    messages.success(request, "User status updated.")
    return redirect("settings_module:users_roles")


@login_required_custom
def reset_user_password_view(request, user_id):
    if not can_manage_users(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    user = user_role_services.get_user(company_id, user_id)
    if not user:
        messages.error(request, "User was not found.")
        return redirect("settings_module:users_roles")
    user_role_services.reset_user_password(user_id)
    log_activity(action="PASSWORD_RESET", module="Users & Roles", record_type="users", record_id=user_id, description=f"Reset password for user {user['username']}.", request=request)
    messages.success(request, f"Password reset. Temporary password: {user_role_services.TEMP_PASSWORD}")
    return redirect("settings_module:users_roles")


@login_required_custom
def role_form_view(request, role_id=None):
    if not can_manage_roles(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    role = user_role_services.get_role(company_id, role_id) if role_id else None
    if role_id and not role:
        messages.error(request, "Role was not found.")
        return redirect("settings_module:role_management")
    if role and int(role.get("is_system_role") or 0) == 1 and not is_master_admin(request):
        return render(request, "errors/403.html", status=403)
    form_data = role or {"role_name": "", "description": "", "is_active": 1}
    errors = {}
    if request.method == "POST":
        form_data = {
            "role_name": request.POST.get("role_name", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "is_active": 1 if request.POST.get("is_active") == "on" else 0,
        }
        errors = validate_role_form(company_id, form_data, role_id, role)
        if not errors:
            saved_id = user_role_services.save_role(company_id, form_data, role_id)
            log_activity(action="UPDATE" if role_id else "CREATE", module="Role Management", record_type="user_roles", record_id=saved_id, description=f"{'Updated' if role_id else 'Created'} role {form_data['role_name']}.", request=request)
            messages.success(request, "Role saved successfully.")
            return redirect("settings_module:role_management")
    return render(request, "settings/role_form.html", {"page_title": "Edit Role" if role_id else "Add Role", "form_data": form_data, "errors": errors, "error_summary": form_validators.collect_form_errors(errors), "is_edit": bool(role_id)})


@login_required_custom
def role_toggle_active_view(request, role_id):
    if not can_manage_roles(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    role = user_role_services.get_role(company_id, role_id)
    if not role:
        messages.error(request, "Role was not found.")
        return redirect("settings_module:role_management")
    if int(role.get("is_system_role") or 0) == 1:
        messages.error(request, "System roles cannot be deactivated from the web app.")
        return redirect("settings_module:role_management")
    new_state = 0 if int(role.get("is_active") or 0) == 1 else 1
    if new_state == 0 and user_role_services.active_user_count_for_role(role_id) > 0:
        messages.error(request, "Cannot deactivate a role assigned to active users.")
        return redirect("settings_module:role_management")
    user_role_services.toggle_role_active(role_id, new_state)
    log_activity(action="ACTIVATE" if new_state else "DEACTIVATE", module="Role Management", record_type="user_roles", record_id=role_id, description=f"{'Activated' if new_state else 'Deactivated'} role {role['role_name']}.", request=request)
    messages.success(request, "Role status updated.")
    return redirect("settings_module:role_management")


@login_required_custom
def role_permissions_view(request, role_id):
    if not can_manage_roles(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    role = user_role_services.get_role(company_id, role_id)
    if not role:
        messages.error(request, "Role was not found.")
        return redirect("settings_module:role_management")
    rows = user_role_services.list_permissions_for_role(role_id)
    if request.method == "POST":
        selected = {}
        for permission in rows:
            permission_id = str(permission["permission_id"])
            selected[permission_id] = {action: bool(request.POST.get(f"perm_{permission_id}_{action}")) for action in user_role_services.ACTIONS}
        user_role_services.save_role_permissions(role_id, selected)
        log_activity(action="UPDATE", module="Role Management", record_type="role_permissions", record_id=role_id, description=f"Updated permissions for role {role['role_name']}.", request=request)
        messages.success(request, "Role permissions saved.")
        return redirect("settings_module:role_permissions", role_id=role_id)
    return render(request, "settings/role_permissions.html", {"page_title": "Manage Permissions", "role": role, "permission_groups": user_role_services.permissions_grouped(rows), "actions": user_role_services.ACTIONS})


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
    form_data["tax_enabled"] = is_tax_enabled(request=request, company_id=company_id)
    can_change_tax_mode = can_change_tax_enabled(request)
    errors = {}

    if request.method == "POST":
        if not _can(request, "tax_settings", "edit"):
            return render(request, "errors/403.html", status=403)
        if "tax_enabled" in request.POST and not can_change_tax_mode:
            messages.error(request, "Only the admin user can change the edition mode.")
            return redirect("settings_module:tax")
        if can_change_tax_mode:
            requested_tax_enabled = request.POST.get("tax_enabled") == "on"
            set_tax_enabled(requested_tax_enabled)
        if not is_tax_enabled(request=request, company_id=company_id):
            log_user_activity(
                request,
                "UPDATE",
                "Edition Settings",
                "tax_settings",
                settings.get("id"),
                "Updated edition settings from web app.",
            )
            messages.success(request, "Settings saved successfully.")
            return redirect("settings_module:tax")
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
            "page_title": "Tax Settings" if form_data.get("tax_enabled") else "Edition Settings",
            "form_data": form_data,
            "errors": errors,
            "error_summary": form_validators.collect_form_errors(errors),
            "tax_enabled": is_tax_enabled(request=request, company_id=company_id),
            "can_change_tax_mode": can_change_tax_mode,
            "env_tax_enabled": env_tax_enabled(),
        },
    )


def _can(request, permission_code, action):
    return user_has_permission(request, permission_code, action)


def is_master_admin(request):
    return int(request.session.get("is_master_user") or 0) == 1


def is_admin_session(request):
    role_name = str(request.session.get("role_name") or "").lower()
    return is_master_admin(request) or "admin" in role_name


def can_manage_users(request):
    return is_admin_session(request) or user_has_permission(request, "user_management", "view")


def can_manage_roles(request):
    return is_admin_session(request) or user_has_permission(request, "role_management", "view")


def validate_user_form(company_id, data, branch_ids, user_id, request, existing_user=None):
    errors = {}
    data["username"], error = form_validators.clean_text(data.get("username"), max_length=80, required=True, field_name="Username")
    if error:
        errors["username"] = error
    elif user_role_services.username_exists(company_id, data["username"], user_id):
        errors["username"] = "Username already exists for this company."
    data["full_name"], error = form_validators.clean_text(data.get("full_name"), max_length=150, required=True, field_name="Full Name")
    if error:
        errors["full_name"] = error
    data["email"], error = form_validators.validate_email(data.get("email"), "Email")
    if error:
        errors["email"] = error
    data["mobile"], error = form_validators.validate_mobile(data.get("mobile"), "Mobile", required=False)
    if error:
        errors["mobile"] = error
    try:
        data["role_id"] = int(data.get("role_id") or 0)
    except (TypeError, ValueError):
        data["role_id"] = 0
    if not data["role_id"] or not user_role_services.get_role(company_id, data["role_id"]):
        errors["role_id"] = "Role is required."
    if not user_id and not data.get("password"):
        data["password"] = user_role_services.TEMP_PASSWORD
    if data.get("password") == "":
        data.pop("password", None)
    if data.get("password") is not None and len(data.get("password") or "") < 8:
        errors["password"] = "Password must be at least 8 characters."
    clean_branch_ids = [value for value in branch_ids if str(value).strip()]
    if not data.get("is_master_user") and not clean_branch_ids:
        errors["branch_ids"] = "At least one branch is required."
    current_user_id = int(request.session.get("user_id") or 0)
    if user_id and int(user_id) == current_user_id:
        if int(data.get("is_active") or 0) != 1:
            errors["is_active"] = "You cannot deactivate your own user."
        if existing_user and int(existing_user.get("is_master_user") or 0) == 1 and int(data.get("is_master_user") or 0) != 1:
            errors["is_master_user"] = "You cannot remove your own Master Admin access."
        if existing_user and int(existing_user.get("role_id") or 0) != int(data.get("role_id") or 0):
            errors["role_id"] = "You cannot change your own role."
        existing_branch_ids = {str(value) for value in user_role_services.user_branch_ids(user_id)}
        if existing_branch_ids and not existing_branch_ids.intersection({str(value) for value in clean_branch_ids}):
            errors["branch_ids"] = "You cannot remove your own branch access."
    return errors


def validate_role_form(company_id, data, role_id=None, existing_role=None):
    errors = {}
    data["role_name"], error = form_validators.clean_text(data.get("role_name"), max_length=100, required=True, field_name="Role Name")
    if error:
        errors["role_name"] = error
    elif user_role_services.role_name_exists(company_id, data["role_name"], role_id):
        errors["role_name"] = "Role name already exists for this company."
    data["description"], error = form_validators.clean_text(data.get("description"), max_length=500, field_name="Description")
    if error:
        errors["description"] = error
    if existing_role and int(existing_role.get("is_system_role") or 0) == 1 and int(data.get("is_active") or 0) != 1:
        errors["is_active"] = "System roles cannot be deactivated."
    if role_id and int(data.get("is_active") or 0) != 1 and user_role_services.active_user_count_for_role(role_id) > 0:
        errors["is_active"] = "Cannot deactivate a role assigned to active users."
    return errors


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
