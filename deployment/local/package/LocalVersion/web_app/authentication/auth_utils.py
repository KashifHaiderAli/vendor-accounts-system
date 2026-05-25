from __future__ import annotations

import hashlib
import hmac

from django.db import connection
from django.utils import timezone


ACTION_COLUMN_MAP = {
    "view": "can_view",
    "add": "can_add",
    "edit": "can_edit",
    "delete": "can_delete",
    "print": "can_print",
    "export": "can_export",
}


def dictfetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def dictfetchall(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def hash_password(password: str, salt: str) -> tuple[str, str]:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def fetch_user_for_login(username: str):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                u.*,
                r.role_name,
                r.is_active AS role_is_active,
                c.company_name
            FROM users u
            JOIN user_roles r ON r.id = u.role_id
            JOIN companies c ON c.id = u.company_id
            WHERE lower(u.username) = lower(%s)
            LIMIT 1
            """,
            [username],
        )
        return dictfetchone(cursor)


def update_last_login(user_id: int) -> None:
    timestamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE users SET last_login = %s, updated_at = %s WHERE id = %s",
            [timestamp, timestamp, user_id],
        )


def get_user_allowed_branches(user_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT company_id, is_master_user FROM users WHERE id = %s LIMIT 1",
            [user_id],
        )
        user = dictfetchone(cursor)
        if not user:
            return []
        if int(user.get("is_master_user") or 0) == 1:
            cursor.execute(
                """
                SELECT
                    b.id,
                    b.branch_name,
                    b.branch_code,
                    b.company_id,
                    b.is_head_office AS is_default
                FROM branches b
                WHERE b.company_id = %s
                  AND b.is_active = 1
                ORDER BY b.is_head_office DESC, b.branch_name ASC
                """,
                [user["company_id"]],
            )
            return dictfetchall(cursor)
        cursor.execute(
            """
            SELECT
                b.id,
                b.branch_name,
                b.branch_code,
                b.company_id,
                ub.is_default
            FROM user_branches ub
            JOIN branches b ON b.id = ub.branch_id
            WHERE ub.user_id = %s
              AND b.is_active = 1
            ORDER BY ub.is_default DESC, b.is_head_office DESC, b.branch_name ASC
            """,
            [user_id],
        )
        return dictfetchall(cursor)


def resolve_login_branch(user):
    branches = get_user_allowed_branches(user["id"])
    if not branches:
        return None

    default_branch_id = user.get("default_branch_id")
    if default_branch_id:
        for branch in branches:
            if int(branch["id"]) == int(default_branch_id):
                return branch

    return branches[0]


def store_login_session(request, user, branch) -> None:
    request.session.flush()
    request.session["user_id"] = user["id"]
    request.session["username"] = user["username"]
    request.session["full_name"] = user["full_name"]
    request.session["role_id"] = user["role_id"]
    request.session["role_name"] = user["role_name"]
    request.session["company_id"] = user["company_id"]
    request.session["company_name"] = user["company_name"]
    request.session["default_branch_id"] = user.get("default_branch_id")
    request.session["current_branch_id"] = branch["id"]
    request.session["current_branch_name"] = branch["branch_name"]
    request.session["is_master_user"] = int(user.get("is_master_user") or 0)


def get_logged_in_user(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "username": request.session.get("username", ""),
        "full_name": request.session.get("full_name", ""),
        "role_id": request.session.get("role_id"),
        "role_name": request.session.get("role_name", ""),
        "company_id": request.session.get("company_id"),
        "company_name": request.session.get("company_name", ""),
        "is_master_user": int(request.session.get("is_master_user") or 0),
    }


def get_current_company(request):
    company_id = request.session.get("company_id")
    if not company_id:
        return None
    return {
        "company_id": company_id,
        "company_name": request.session.get("company_name", ""),
    }


def get_current_branch(request):
    branch_id = request.session.get("current_branch_id")
    if not branch_id:
        return None
    return {
        "branch_id": branch_id,
        "branch_name": request.session.get("current_branch_name", ""),
    }


def set_current_branch(request, branch_id):
    user_id = request.session.get("user_id")
    if not user_id:
        return False

    for branch in get_user_allowed_branches(user_id):
        if int(branch["id"]) == int(branch_id):
            request.session["current_branch_id"] = branch["id"]
            request.session["current_branch_name"] = branch["branch_name"]
            return True
    return False


def user_has_permission(request, permission_code, action="view") -> bool:
    if int(request.session.get("is_master_user") or 0) == 1:
        return True

    role_id = request.session.get("role_id")
    if not role_id:
        return False

    column_name = ACTION_COLUMN_MAP.get(action)
    if not column_name:
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT rp.{column_name}
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            JOIN user_roles r ON r.id = rp.role_id
            WHERE rp.role_id = %s
              AND p.permission_code = %s
              AND r.is_active = 1
            LIMIT 1
            """,
            [role_id, permission_code],
        )
        row = cursor.fetchone()

    return bool(row and int(row[0] or 0) == 1)
