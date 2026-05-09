from __future__ import annotations

from django.db import connection

from settings_module.services import now_text


def request_meta(request):
    if not request:
        return "", ""
    ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.META.get("REMOTE_ADDR", "")
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip_address, user_agent[:240]


def log_activity(
    user_id=None,
    company_id=None,
    branch_id=None,
    action="INFO",
    module="System",
    record_type=None,
    record_id=None,
    description=None,
    request=None,
):
    timestamp = now_text()
    if request is not None:
        user_id = user_id if user_id is not None else request.session.get("user_id")
        company_id = company_id if company_id is not None else request.session.get("company_id")
        branch_id = branch_id if branch_id is not None else request.session.get("current_branch_id")
        username = request.session.get("username", "")
        ip_address, user_agent = request_meta(request)
        extra = f" | user={username or '-'} ip={ip_address or '-'} ua={user_agent or '-'}"
        description = f"{description or ''}{extra}"[:2000]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_activity_log (
                    company_id, branch_id, user_id, action_type, module_name,
                    table_name, record_id, description, activity_datetime, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    company_id,
                    branch_id,
                    user_id,
                    action,
                    module,
                    record_type,
                    record_id,
                    description,
                    timestamp,
                    timestamp,
                ],
            )
    except Exception:
        # Audit logging must never break the business action.
        return


def log_login(request, user_id, company_id, branch_id):
    log_activity(user_id, company_id, branch_id, "LOGIN", "Authentication", "users", user_id, "User logged in.", request)


def log_logout(request):
    log_activity(action="LOGOUT", module="Authentication", record_type="users", record_id=request.session.get("user_id"), description="User logged out.", request=request)


def log_permission_denied(request, module="Security", description="Permission denied."):
    log_activity(action="PERMISSION_DENIED", module=module, description=f"{description} path={getattr(request, 'path', '')}", request=request)


def log_license_failure(request, description="License check failed."):
    log_activity(action="LICENSE_FAILURE", module="Licensing", description=description, request=request)


def log_export_report(request, report_name, export_type):
    log_activity(action="EXPORT", module="Reports", record_type="report", description=f"Exported {report_name} as {export_type}.", request=request)


def log_backup(request, backup_path, status="SUCCESS"):
    log_activity(action="BACKUP", module="System Backup", record_type="backup", description=f"{status}: {backup_path}", request=request)


def log_restore(request, backup_path, status="SUCCESS"):
    log_activity(action="RESTORE", module="System Restore", record_type="restore", description=f"{status}: {backup_path}", request=request)
