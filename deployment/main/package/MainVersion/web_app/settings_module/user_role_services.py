from __future__ import annotations

import secrets
from datetime import datetime

from django.db import connection

from authentication.auth_utils import dictfetchall, dictfetchone, hash_password


TEMP_PASSWORD = "Temp@12345"
ACTIONS = ["view", "add", "edit", "delete", "print", "export"]
ACTION_COLUMNS = {
    "view": "can_view",
    "add": "can_add",
    "edit": "can_edit",
    "delete": "can_delete",
    "print": "can_print",
    "export": "can_export",
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_password(password=TEMP_PASSWORD):
    salt = secrets.token_hex(16)
    password_hash, password_salt = hash_password(password, salt)
    return password_hash, password_salt


def list_users(company_id, search=""):
    params = [company_id]
    where = ["u.company_id=%s"]
    if search:
        where.append("(u.username LIKE %s OR u.full_name LIKE %s OR u.email LIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT u.*, r.role_name,
                   COALESCE(GROUP_CONCAT(b.branch_name, ', '), CASE WHEN u.is_master_user=1 THEN 'All branches' ELSE '' END) AS branch_access
            FROM users u
            JOIN user_roles r ON r.id=u.role_id
            LEFT JOIN user_branches ub ON ub.user_id=u.id
            LEFT JOIN branches b ON b.id=ub.branch_id
            WHERE {' AND '.join(where)}
            GROUP BY u.id
            ORDER BY u.is_master_user DESC, u.username
            """,
            params,
        )
        return dictfetchall(cursor)


def get_user(company_id, user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE company_id=%s AND id=%s LIMIT 1", [company_id, user_id])
        return dictfetchone(cursor)


def username_exists(company_id, username, exclude_user_id=None):
    params = [company_id, username.lower()]
    clause = ""
    if exclude_user_id:
        clause = "AND id <> %s"
        params.append(exclude_user_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id FROM users WHERE company_id=%s AND lower(username)=%s {clause} LIMIT 1",
            params,
        )
        return cursor.fetchone() is not None


def list_roles(company_id, include_inactive=False):
    clause = "" if include_inactive else "AND r.is_active=1"
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT r.*, COUNT(u.id) AS users_count
            FROM user_roles r
            LEFT JOIN users u ON u.role_id=r.id AND u.is_active=1
            WHERE r.company_id=%s {clause}
            GROUP BY r.id
            ORDER BY r.is_system_role DESC, r.role_name
            """,
            [company_id],
        )
        return dictfetchall(cursor)


def get_role(company_id, role_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM user_roles WHERE company_id=%s AND id=%s LIMIT 1", [company_id, role_id])
        return dictfetchone(cursor)


def role_name_exists(company_id, role_name, exclude_role_id=None):
    params = [company_id, role_name.lower()]
    clause = ""
    if exclude_role_id:
        clause = "AND id <> %s"
        params.append(exclude_role_id)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id FROM user_roles WHERE company_id=%s AND lower(role_name)=%s {clause} LIMIT 1",
            params,
        )
        return cursor.fetchone() is not None


def active_user_count_for_role(role_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users WHERE role_id=%s AND is_active=1", [role_id])
        return int(cursor.fetchone()[0] or 0)


def list_branches(company_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, branch_name",
            [company_id],
        )
        return dictfetchall(cursor)


def user_branch_ids(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT branch_id FROM user_branches WHERE user_id=%s ORDER BY is_default DESC, branch_id", [user_id])
        return [int(row[0]) for row in cursor.fetchall()]


def save_user(company_id, data, branch_ids, user_id=None):
    now = now_text()
    with connection.cursor() as cursor:
        if user_id:
            fields = [
                "username=%s",
                "full_name=%s",
                "email=%s",
                "mobile=%s",
                "role_id=%s",
                "default_branch_id=%s",
                "is_master_user=%s",
                "is_active=%s",
                "updated_at=%s",
            ]
            params = [
                data["username"],
                data["full_name"],
                data.get("email", ""),
                data.get("mobile", ""),
                data["role_id"],
                data.get("default_branch_id"),
                data["is_master_user"],
                data["is_active"],
                now,
            ]
            if data.get("password"):
                password_hash, password_salt = make_password(data["password"])
                fields.extend(["password_hash=%s", "password_salt=%s", "must_change_password=1"])
                params.extend([password_hash, password_salt])
            params.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=%s", params)
            saved_id = user_id
        else:
            password_hash, password_salt = make_password(data["password"])
            cursor.execute(
                """
                INSERT INTO users (
                    company_id, username, password_hash, password_salt, full_name, email, mobile,
                    role_id, default_branch_id, is_master_user, is_active, must_change_password,
                    created_at, updated_at, last_login
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,NULL)
                """,
                [
                    company_id,
                    data["username"],
                    password_hash,
                    password_salt,
                    data["full_name"],
                    data.get("email", ""),
                    data.get("mobile", ""),
                    data["role_id"],
                    data.get("default_branch_id"),
                    data["is_master_user"],
                    data["is_active"],
                    now,
                    now,
                ],
            )
            saved_id = cursor.lastrowid
        save_user_branches(saved_id, branch_ids, data.get("default_branch_id"))
        return saved_id


def save_user_branches(user_id, branch_ids, default_branch_id=None):
    now = now_text()
    clean_ids = []
    for value in branch_ids:
        try:
            branch_id = int(value)
        except (TypeError, ValueError):
            continue
        if branch_id not in clean_ids:
            clean_ids.append(branch_id)
    if default_branch_id not in clean_ids and clean_ids:
        default_branch_id = clean_ids[0]
    with connection.cursor() as cursor:
        if clean_ids:
            cursor.execute(
                "DELETE FROM user_branches WHERE user_id=%s AND branch_id NOT IN ({})".format(",".join(["%s"] * len(clean_ids))),
                [user_id, *clean_ids],
            )
        else:
            cursor.execute("DELETE FROM user_branches WHERE user_id=%s", [user_id])
        cursor.execute("UPDATE user_branches SET is_default=0, updated_at=%s WHERE user_id=%s", [now, user_id])
        for branch_id in clean_ids:
            is_default = 1 if int(branch_id) == int(default_branch_id or 0) else 0
            cursor.execute("SELECT id FROM user_branches WHERE user_id=%s AND branch_id=%s", [user_id, branch_id])
            row = cursor.fetchone()
            if row:
                cursor.execute("UPDATE user_branches SET is_default=%s, updated_at=%s WHERE id=%s", [is_default, now, row[0]])
            else:
                cursor.execute(
                    "INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                    [user_id, branch_id, is_default, now, now],
                )


def reset_user_password(user_id, password=TEMP_PASSWORD):
    password_hash, password_salt = make_password(password)
    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE users SET password_hash=%s, password_salt=%s, must_change_password=1, updated_at=%s WHERE id=%s",
            [password_hash, password_salt, now, user_id],
        )


def toggle_user_active(user_id, active):
    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE users SET is_active=%s, updated_at=%s WHERE id=%s", [1 if active else 0, now, user_id])


def save_role(company_id, data, role_id=None):
    now = now_text()
    with connection.cursor() as cursor:
        if role_id:
            cursor.execute(
                "UPDATE user_roles SET role_name=%s, description=%s, is_active=%s, updated_at=%s WHERE id=%s AND company_id=%s",
                [data["role_name"], data.get("description", ""), data["is_active"], now, role_id, company_id],
            )
            return role_id
        cursor.execute(
            """
            INSERT INTO user_roles (company_id, role_name, description, is_system_role, is_active, created_at, updated_at)
            VALUES (%s,%s,%s,0,%s,%s,%s)
            """,
            [company_id, data["role_name"], data.get("description", ""), data["is_active"], now, now],
        )
        return cursor.lastrowid


def toggle_role_active(role_id, active):
    now = now_text()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE user_roles SET is_active=%s, updated_at=%s WHERE id=%s", [1 if active else 0, now, role_id])


def list_permissions_for_role(role_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT p.id AS permission_id, p.permission_code, p.permission_name, p.module_name,
                   COALESCE(rp.can_view,0) AS can_view,
                   COALESCE(rp.can_add,0) AS can_add,
                   COALESCE(rp.can_edit,0) AS can_edit,
                   COALESCE(rp.can_delete,0) AS can_delete,
                   COALESCE(rp.can_print,0) AS can_print,
                   COALESCE(rp.can_export,0) AS can_export
            FROM permissions p
            LEFT JOIN role_permissions rp ON rp.permission_id=p.id AND rp.role_id=%s
            ORDER BY p.module_name, p.permission_name
            """,
            [role_id],
        )
        return dictfetchall(cursor)


def save_role_permissions(role_id, selected_flags):
    now = now_text()
    permissions = list_permissions_for_role(role_id)
    with connection.cursor() as cursor:
        for permission in permissions:
            permission_id = permission["permission_id"]
            flags = selected_flags.get(str(permission_id), {})
            values = [1 if flags.get(action) else 0 for action in ACTIONS]
            cursor.execute("SELECT id FROM role_permissions WHERE role_id=%s AND permission_id=%s", [role_id, permission_id])
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """
                    UPDATE role_permissions
                    SET can_view=%s, can_add=%s, can_edit=%s, can_delete=%s,
                        can_print=%s, can_export=%s, updated_at=%s
                    WHERE id=%s
                    """,
                    [*values, now, row[0]],
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO role_permissions (
                        role_id, permission_id, can_view, can_add, can_edit, can_delete,
                        can_print, can_export, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [role_id, permission_id, *values, now, now],
                )


def permissions_grouped(permission_rows):
    grouped = {}
    for row in permission_rows:
        grouped.setdefault(row["module_name"], []).append(row)
    return grouped.items()
