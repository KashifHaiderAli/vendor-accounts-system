from datetime import date

from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect, render

from authentication.auth_utils import dictfetchall, dictfetchone, user_has_permission
from authentication.decorators import login_required_custom
from core.audit_utils import log_activity, log_permission_denied
from settings_module.services import now_text

from .hardware_fingerprint import get_hardware_fingerprint
from .middleware import has_valid_license
from .license_utils import evaluate_license_record, expiry_for_license, generate_license_key, parse_license_date


LICENSE_TYPES = ["Trial", "Annual", "Lifetime"]


def is_admin(request):
    role_name = str(request.session.get("role_name") or "").lower()
    return int(request.session.get("is_master_user") or 0) == 1 or "admin" in role_name


def can_manage_license(request):
    return is_admin(request) or user_has_permission(request, "licensing", "view") or user_has_permission(request, "license", "view") or user_has_permission(request, "settings", "view")


@login_required_custom
def index(request):
    if not can_manage_license(request):
        log_permission_denied(request, "Licensing", "License status access denied.")
        return render(request, "errors/403.html", status=403)

    company_id = request.session.get("company_id")
    branch_id = request.session.get("current_branch_id")
    fingerprint = get_hardware_fingerprint()
    company = get_company(company_id)
    branch = get_branch(branch_id, company_id)

    if request.method == "POST":
        action = request.POST.get("action", "activate")
        if action == "activate":
            handle_activation(request, company_id, branch_id, fingerprint)
        elif action == "deactivate":
            handle_deactivate(request, company_id)
        elif action == "reactivate":
            handle_reactivate(request, company_id, fingerprint)
        return redirect("licensing:index")

    licenses = license_history(company_id, fingerprint)
    active_license = next((row for row in licenses if int(row.get("is_active") or 0) == 1), None)
    status = current_status(active_license, licenses, fingerprint)
    is_valid = has_valid_license(company_id) if company_id else False
    return render(
        request,
        "licensing/license_status.html",
        {
            "page_title": "License Status",
            "license_is_valid": is_valid,
            "license_types": LICENSE_TYPES,
            "hardware_fingerprint": fingerprint,
            "company": company,
            "branch": branch,
            "status": status,
            "active_license": active_license,
            "licenses": licenses,
            "today": date.today().isoformat(),
        },
    )


def expired(request):
    return render(
        request,
        "licensing/license_expired.html",
        {"hardware_fingerprint": get_hardware_fingerprint()},
    )


def get_company(company_id):
    if not company_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE id=%s LIMIT 1", [company_id])
        return dictfetchone(cursor)


def get_branch(branch_id, company_id):
    if not branch_id:
        return None
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM branches WHERE id=%s AND company_id=%s LIMIT 1", [branch_id, company_id])
        return dictfetchone(cursor)


def license_history(company_id, fingerprint):
    if not company_id:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM license_records
            WHERE company_id=%s
            ORDER BY is_active DESC, created_at DESC, id DESC
            """,
            [company_id],
        )
        rows = dictfetchall(cursor)
    for row in rows:
        evaluation = evaluate_license_record(row, fingerprint)
        row["computed_status"] = status_label(row, evaluation.reason, evaluation.valid)
        row["hardware_match"] = str(row.get("hardware_fingerprint") or "") == fingerprint
        row["masked_key"] = mask_license_key(row.get("license_key"))
        row["days_remaining"] = days_remaining(row)
        row["validation_message"] = evaluation.reason
        row["can_reactivate"] = (not int(row.get("is_active") or 0)) and evaluation.valid
    return rows


def current_status(active_license, licenses, fingerprint):
    if not licenses:
        return {
            "label": "Missing",
            "tone": "warning",
            "message": "No valid license found. Please enter a valid license key generated from DB App.",
        }
    if not active_license:
        return {"label": "Inactive / Locked", "tone": "danger", "message": "No active license record is available."}
    evaluation = evaluate_license_record(active_license, fingerprint)
    return {
        "label": status_label(active_license, evaluation.reason, evaluation.valid),
        "tone": "success" if evaluation.valid else "danger",
        "message": evaluation.reason,
    }


def status_label(row, reason, valid):
    if valid:
        return "Valid"
    if int(row.get("is_active") or 0) != 1:
        return "Inactive / Locked"
    if "hardware" in reason:
        return "Hardware Mismatch"
    if "expired" in reason or "not started" in reason:
        return "Expired"
    return "Invalid"


def days_remaining(row):
    if int(row.get("is_lifetime") or 0) == 1:
        return None
    expiry = parse_license_date(row.get("expiry_date"))
    if not expiry:
        return None
    return (expiry - date.today()).days


def mask_license_key(value):
    value = str(value or "")
    if len(value) <= 10:
        return value
    return f"{value[:5]}...{value[-5:]}"


def handle_activation(request, company_id, branch_id, fingerprint):
    license_type = request.POST.get("license_type", "").strip()
    start_date = request.POST.get("start_date", "").strip()
    expiry_date = request.POST.get("expiry_date", "").strip() or None
    license_key = request.POST.get("license_key", "").strip().upper()
    remarks = request.POST.get("remarks", "").strip()
    errors = []

    if license_type not in LICENSE_TYPES:
        errors.append("License Type is required.")
    if not parse_license_date(start_date):
        errors.append("Start Date is required and must be valid.")
    if license_type != "Lifetime" and not parse_license_date(expiry_date):
        errors.append("Expiry Date is required for Trial and Annual licenses.")
    if not license_key:
        errors.append("License Key is required.")

    is_lifetime = 1 if license_type == "Lifetime" else 0
    if not errors:
        if license_type == "Lifetime":
            expiry_date = None
        expected_key = generate_license_key(license_type, fingerprint, parse_license_date(start_date).isoformat())
        if license_key != expected_key:
            errors.append("Invalid license key.")

    if errors:
        for error in errors:
            messages.error(request, error)
        log_activity(action="VALIDATION_FAILURE", module="Licensing", description="License activation failed: " + "; ".join(errors), request=request)
        return False

    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE license_records SET is_active=0, updated_at=%s WHERE company_id=%s AND is_active=1", [now, company_id])
        cursor.execute(
            """
            INSERT INTO license_records (
                company_id, branch_id, license_type, hardware_fingerprint, license_key,
                issue_date, start_date, expiry_date, is_lifetime, is_active, remarks,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
            """,
            [company_id, branch_id, license_type, fingerprint, license_key, date.today().isoformat(), start_date, expiry_date, is_lifetime, remarks, now, now],
        )
    log_activity(action="ACTIVATE", module="Licensing", record_type="license_records", description=f"{license_type} license activated.", request=request)
    messages.success(request, "License activated successfully.")
    return True


def handle_deactivate(request, company_id):
    license_id = request.POST.get("license_id")
    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE license_records SET is_active=0, updated_at=%s WHERE id=%s AND company_id=%s", [now, license_id, company_id])
    log_activity(action="DEACTIVATE", module="Licensing", record_type="license_records", record_id=license_id, description="License deactivated.", request=request)
    messages.success(request, "License deactivated.")


def handle_reactivate(request, company_id, fingerprint):
    license_id = request.POST.get("license_id")
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM license_records WHERE id=%s AND company_id=%s LIMIT 1", [license_id, company_id])
        row = dictfetchone(cursor)
    if not row:
        messages.error(request, "License record was not found.")
        return
    evaluation = evaluate_license_record({**row, "is_active": 1}, fingerprint)
    if not evaluation.valid:
        messages.error(request, f"License cannot be reactivated: {evaluation.reason}.")
        return
    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE license_records SET is_active=0, updated_at=%s WHERE company_id=%s AND is_active=1", [now, company_id])
        cursor.execute("UPDATE license_records SET is_active=1, updated_at=%s WHERE id=%s AND company_id=%s", [now, license_id, company_id])
    log_activity(action="REACTIVATE", module="Licensing", record_type="license_records", record_id=license_id, description="License reactivated.", request=request)
    messages.success(request, "License reactivated successfully.")
