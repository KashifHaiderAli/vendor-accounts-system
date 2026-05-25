from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.db import connection
from django.http import FileResponse
from django.shortcuts import redirect, render

from authentication.auth_utils import dictfetchall, dictfetchone, user_has_permission
from authentication.decorators import login_required_custom
from core import backup_utils
from core.audit_utils import log_activity, log_backup, log_export_report, log_permission_denied, log_restore
from reports.export_utils import csv_response


def is_admin(request):
    role_name = str(request.session.get("role_name") or "").lower()
    return int(request.session.get("is_master_user") or 0) == 1 or "admin" in role_name


def is_master_admin(request):
    return int(request.session.get("is_master_user") or 0) == 1


def can_backup(request):
    return user_has_permission(request, "system_backup", "view") or user_has_permission(request, "backup_restore", "view") or is_admin(request)


def can_restore(request):
    return user_has_permission(request, "system_restore", "view") or is_master_admin(request)


def can_audit(request):
    return user_has_permission(request, "audit_log", "view") or is_admin(request)


def require_backup(request):
    if not can_backup(request):
        log_permission_denied(request, "Backup", "Backup permission denied.")
        return False
    return True


def require_restore(request):
    if not can_restore(request):
        log_permission_denied(request, "Restore", "Restore permission denied.")
        return False
    return True


@login_required_custom
def backup_dashboard(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    folder = backup_utils.get_backup_folder()
    live_db = backup_utils.live_db_path()
    history = backup_utils.load_history()[:10]
    context = {
        "page_title": "Backup / Restore",
        "live_db_path": str(live_db),
        "live_db_synced_warning": backup_utils.is_synced_path(live_db),
        "backup_folder": str(folder),
        "backup_folder_same_warning": backup_utils.same_folder_warning(folder),
        "last_backup": history[0] if history else None,
        "history": history,
        "can_restore": can_restore(request),
    }
    return render(request, "system/backup_dashboard.html", context)


@login_required_custom
def backup_settings(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    folder = backup_utils.get_backup_folder()
    if request.method == "POST":
        folder_value = request.POST.get("backup_folder", "").strip()
        try:
            folder = backup_utils.set_backup_folder(folder_value)
            log_activity(action="UPDATE", module="System Backup", record_type="system_settings", description=f"Backup folder set to {folder}.", request=request)
            messages.success(request, "Backup folder saved.")
            return redirect("backup:dashboard")
        except Exception as exc:
            messages.error(request, f"Unable to save backup folder: {exc}")
    return render(
        request,
        "system/backup_settings.html",
        {
            "page_title": "Backup Settings",
            "backup_folder": str(folder),
            "live_db_folder": str(backup_utils.live_db_path().parent),
            "backup_folder_same_warning": backup_utils.same_folder_warning(folder),
        },
    )


@login_required_custom
def backup_now(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    if request.method != "POST":
        return redirect("backup:dashboard")
    try:
        metadata = backup_utils.create_backup(request)
        log_backup(request, metadata["backup_path"])
        messages.success(request, f"Backup created: {Path(metadata['backup_path']).name}")
    except Exception as exc:
        log_backup(request, str(exc), status="FAIL")
        messages.error(request, f"Backup failed: {exc}")
    return redirect("backup:dashboard")


@login_required_custom
def backup_history(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    return render(
        request,
        "system/backup_history.html",
        {
            "page_title": "Backup History",
            "history": backup_utils.load_history(),
            "can_restore": can_restore(request),
        },
    )


@login_required_custom
def download_backup(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    path = Path(request.GET.get("path", "")).expanduser().resolve()
    if not path.exists() or not path.name.startswith("vendor_accounts_backup_"):
        messages.error(request, "Backup file was not found.")
        return redirect("backup:history")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@login_required_custom
def verify_backup(request):
    if not require_backup(request):
        return render(request, "errors/403.html", status=403)
    try:
        info = backup_utils.validate_backup_file(request.GET.get("path", ""))
        messages.success(request, f"Backup verified. Tables found: {len(info['tables'])}.")
    except Exception as exc:
        messages.error(request, f"Backup verification failed: {exc}")
    return redirect("backup:history")


@login_required_custom
def restore_backup(request):
    if not require_restore(request):
        return render(request, "errors/403.html", status=403)
    return render(request, "system/restore_backup.html", {"page_title": "Restore Backup"})


@login_required_custom
def restore_preview(request):
    if not require_restore(request):
        return render(request, "errors/403.html", status=403)
    if request.method != "POST":
        return redirect("backup:restore")
    selected_path = request.POST.get("backup_path", "").strip()
    try:
        info = backup_utils.validate_backup_file(selected_path)
        request.session["restore_backup_path"] = info["path"]
        return render(
            request,
            "system/confirm_restore.html",
            {
                "page_title": "Confirm Restore",
                "backup_info": info,
                "live_db_path": str(backup_utils.live_db_path()),
            },
        )
    except Exception as exc:
        messages.error(request, f"Restore preview failed: {exc}")
        return redirect("backup:restore")


@login_required_custom
def restore_confirm(request):
    if not require_restore(request):
        return render(request, "errors/403.html", status=403)
    if request.method != "POST":
        return redirect("backup:restore")
    path = request.session.get("restore_backup_path")
    try:
        result = backup_utils.restore_backup(path)
        log_restore(request, result["restored_from"])
        request.session.flush()
        messages.success(request, "Database restored. Please login again.")
        return redirect("authentication:login")
    except Exception as exc:
        log_restore(request, str(exc), status="FAIL")
        messages.error(request, f"Restore failed: {exc}")
        return redirect("backup:restore")


@login_required_custom
def audit_log(request):
    if not can_audit(request):
        log_permission_denied(request, "Audit Log", "Audit log permission denied.")
        return render(request, "errors/403.html", status=403)
    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "user_id": request.GET.get("user_id", "").strip(),
        "action": request.GET.get("action", "").strip(),
        "module": request.GET.get("module", "").strip(),
        "record_type": request.GET.get("record_type", "").strip(),
        "q": request.GET.get("q", "").strip(),
    }
    rows = query_audit(filters, request.session.get("company_id"))
    if request.GET.get("export") == "csv":
        log_export_report(request, "Audit Log", "CSV")
        return csv_response(
            "audit_log.csv",
            [
                {"key": "activity_datetime", "label": "Date/Time"},
                {"key": "username", "label": "User"},
                {"key": "action_type", "label": "Action"},
                {"key": "module_name", "label": "Module"},
                {"key": "table_name", "label": "Record Type"},
                {"key": "record_id", "label": "Record ID"},
                {"key": "description", "label": "Description"},
            ],
            rows,
        )
    return render(
        request,
        "system/audit_log.html",
        {
            "page_title": "Audit Log",
            "rows": rows[:50],
            "filters": filters,
            "users": list_users(request.session.get("company_id")),
        },
    )


@login_required_custom
def audit_log_detail(request, log_id):
    if not can_audit(request):
        log_permission_denied(request, "Audit Log", "Audit log detail permission denied.")
        return render(request, "errors/403.html", status=403)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT l.*, u.username, u.full_name
            FROM user_activity_log l
            LEFT JOIN users u ON u.id=l.user_id
            WHERE l.id=%s AND (l.company_id=%s OR l.company_id IS NULL)
            LIMIT 1
            """,
            [log_id, request.session.get("company_id")],
        )
        row = dictfetchone(cursor)
    if not row:
        messages.error(request, "Audit record was not found.")
        return redirect("backup:audit_log")
    return render(request, "system/audit_log_detail.html", {"page_title": "Audit Detail", "row": row})


def query_audit(filters, company_id):
    clauses = ["(l.company_id = %s OR l.company_id IS NULL)"]
    params = [company_id]
    if filters["date_from"]:
        clauses.append("l.activity_datetime >= %s")
        params.append(filters["date_from"])
    if filters["date_to"]:
        clauses.append("l.activity_datetime <= %s")
        params.append(filters["date_to"] + " 23:59:59")
    if filters["user_id"]:
        clauses.append("l.user_id = %s")
        params.append(filters["user_id"])
    if filters["action"]:
        clauses.append("l.action_type LIKE %s")
        params.append(f"%{filters['action']}%")
    if filters["module"]:
        clauses.append("l.module_name LIKE %s")
        params.append(f"%{filters['module']}%")
    if filters["record_type"]:
        clauses.append("l.table_name LIKE %s")
        params.append(f"%{filters['record_type']}%")
    if filters["q"]:
        like = f"%{filters['q']}%"
        clauses.append("(l.description LIKE %s OR l.module_name LIKE %s OR l.action_type LIKE %s)")
        params.extend([like, like, like])
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT l.*, u.username, u.full_name
            FROM user_activity_log l
            LEFT JOIN users u ON u.id=l.user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY l.activity_datetime DESC, l.id DESC
            LIMIT 500
            """,
            params,
        )
        return dictfetchall(cursor)


def list_users(company_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, username, full_name FROM users WHERE company_id=%s ORDER BY username", [company_id])
        return dictfetchall(cursor)
