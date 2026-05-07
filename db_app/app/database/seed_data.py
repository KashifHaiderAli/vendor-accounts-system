from __future__ import annotations

from pathlib import Path

from app.config import DATABASE_PASSWORD_HINT
from app.constants import (
    BUSINESS_MODULES,
    DEFAULT_ACCOUNT_GROUPS,
    DEFAULT_ROLES,
    PERMISSION_MODULES,
    REPORT_MODULES,
    ROLE_ACCOUNTANT,
    ROLE_ASSISTANT_ACCOUNTANT,
    ROLE_MASTER_ADMIN,
    ROLE_VIEWER,
    ROUTINE_TRANSACTION_MODULES,
    VIEWER_MODULES,
)
from app.security.password_utils import hash_password
from app.utils.date_utils import now_iso


def seed_defaults(connection, database_path: str | Path) -> None:
    now = now_iso()
    company_id = _seed_company(connection, now)
    branch_id = _seed_branch(connection, company_id, now)
    _seed_settings(connection, company_id, branch_id, Path(database_path), now)
    role_ids = _seed_roles(connection, company_id, now)
    permission_ids = _seed_permissions(connection, now)
    _seed_role_permissions(connection, role_ids, permission_ids, now)
    admin_user_id = _seed_admin_user(connection, company_id, branch_id, role_ids[ROLE_MASTER_ADMIN], now)
    _seed_user_branch(connection, admin_user_id, branch_id, now)
    _seed_accounts(connection, company_id, branch_id, now)
    connection.commit()


def _seed_company(connection, now: str) -> int:
    row = connection.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
    if row:
        return row["id"]
    cursor = connection.execute(
        """
        INSERT INTO companies (
            company_name, legal_name, is_active, created_at, updated_at
        ) VALUES (?, ?, 1, ?, ?)
        """,
        ("Your Company Name", "Your Company Legal Name", now, now),
    )
    return int(cursor.lastrowid)


def _seed_branch(connection, company_id: int, now: str) -> int:
    row = connection.execute(
        "SELECT id FROM branches WHERE company_id = ? AND branch_code = ?",
        (company_id, "HO"),
    ).fetchone()
    if row:
        return row["id"]
    cursor = connection.execute(
        """
        INSERT INTO branches (
            company_id, branch_code, branch_name, is_head_office, is_active, created_at, updated_at
        ) VALUES (?, 'HO', 'Head Office', 1, 1, ?, ?)
        """,
        (company_id, now, now),
    )
    return int(cursor.lastrowid)


def _seed_settings(connection, company_id: int, branch_id: int, database_path: Path, now: str) -> None:
    if not connection.execute("SELECT id FROM company_settings WHERE company_id = ?", (company_id,)).fetchone():
        connection.execute(
            """
            INSERT INTO company_settings (
                company_id, branch_id, quotation_footer, invoice_footer, bank_details,
                authorized_person_name, created_at, updated_at
            ) VALUES (?, ?, '', '', '', '', ?, ?)
            """,
            (company_id, branch_id, now, now),
        )

    if not connection.execute("SELECT id FROM numbering_settings WHERE company_id = ?", (company_id,)).fetchone():
        connection.execute(
            """
            INSERT INTO numbering_settings (
                company_id, branch_id, customer_prefix, supplier_prefix, item_prefix,
                quotation_prefix, confirmation_prefix, delivery_challan_prefix, invoice_prefix,
                sales_return_prefix, cash_memo_prefix, receipt_prefix, purchase_prefix,
                purchase_return_prefix, supplier_payment_prefix, service_contract_prefix,
                expense_voucher_prefix, use_year_in_number, number_padding, created_at, updated_at
            ) VALUES (?, ?, 'CUS', 'SUP', 'ITM', 'QTN', 'CONF', 'DC', 'INV', 'SR',
                      'CM', 'RCV', 'PUR', 'PR', 'SPV', 'SC', 'EXP', 1, 4, ?, ?)
            """,
            (company_id, branch_id, now, now),
        )
    else:
        connection.execute(
            """
            UPDATE numbering_settings
            SET sales_return_prefix = COALESCE(sales_return_prefix, 'SR'),
                purchase_return_prefix = COALESCE(purchase_return_prefix, 'PR'),
                updated_at = ?
            WHERE company_id = ?
            """,
            (now, company_id),
        )

    if not connection.execute("SELECT id FROM tax_settings WHERE company_id = ?", (company_id,)).fetchone():
        connection.execute(
            """
            INSERT INTO tax_settings (
                company_id, branch_id, default_sales_tax_percent, default_input_tax_percent,
                default_tax_applicable, tax_invoice_label, show_ntn_on_invoice,
                show_strn_on_invoice, created_at, updated_at
            ) VALUES (?, ?, 0, 0, 0, 'Tax Invoice', 1, 1, ?, ?)
            """,
            (company_id, branch_id, now, now),
        )

    row = connection.execute("SELECT id FROM app_settings WHERE company_id = ?", (company_id,)).fetchone()
    if row:
        connection.execute(
            "UPDATE app_settings SET database_path = ?, updated_at = ? WHERE id = ?",
            (str(database_path), now, row["id"]),
        )
    else:
        # Standard SQLite is not encrypted by this value. It is stored only as an
        # application-level hint; SQLCipher can be introduced later for real encryption.
        connection.execute(
            """
            INSERT INTO app_settings (
                company_id, database_path, database_password_hint, backup_folder_path,
                auto_backup_on_close, auto_backup_daily, keep_last_backups, created_at, updated_at
            ) VALUES (?, ?, ?, '', 0, 0, 30, ?, ?)
            """,
            (company_id, str(database_path), DATABASE_PASSWORD_HINT, now, now),
        )


def _seed_roles(connection, company_id: int, now: str) -> dict[str, int]:
    role_ids: dict[str, int] = {}
    for role_name, description, is_system_role in DEFAULT_ROLES:
        row = connection.execute(
            "SELECT id FROM user_roles WHERE company_id = ? AND role_name = ?",
            (company_id, role_name),
        ).fetchone()
        if row:
            role_ids[role_name] = row["id"]
            continue
        cursor = connection.execute(
            """
            INSERT INTO user_roles (
                company_id, role_name, description, is_system_role, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (company_id, role_name, description, is_system_role, now, now),
        )
        role_ids[role_name] = int(cursor.lastrowid)
    return role_ids


def _seed_permissions(connection, now: str) -> dict[str, int]:
    permission_ids: dict[str, int] = {}
    for module_name in PERMISSION_MODULES:
        permission_code = module_name
        permission_name = module_name.replace("_", " ").title()
        row = connection.execute(
            "SELECT id FROM permissions WHERE permission_code = ?",
            (permission_code,),
        ).fetchone()
        if row:
            permission_ids[module_name] = row["id"]
            continue
        cursor = connection.execute(
            """
            INSERT INTO permissions (
                permission_code, permission_name, module_name, description, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                permission_code,
                permission_name,
                module_name,
                f"Access controls for {permission_name}.",
                now,
                now,
            ),
        )
        permission_ids[module_name] = int(cursor.lastrowid)
    return permission_ids


def _seed_role_permissions(
    connection, role_ids: dict[str, int], permission_ids: dict[str, int], now: str
) -> None:
    for role_name, role_id in role_ids.items():
        for module_name, permission_id in permission_ids.items():
            flags = _permission_flags_for_role(role_name, module_name)
            row = connection.execute(
                "SELECT id FROM role_permissions WHERE role_id = ? AND permission_id = ?",
                (role_id, permission_id),
            ).fetchone()
            values = (
                flags["can_view"],
                flags["can_add"],
                flags["can_edit"],
                flags["can_delete"],
                flags["can_print"],
                flags["can_export"],
            )
            if row:
                connection.execute(
                    """
                    UPDATE role_permissions
                    SET can_view = ?, can_add = ?, can_edit = ?, can_delete = ?,
                        can_print = ?, can_export = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, now, row["id"]),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO role_permissions (
                        role_id, permission_id, can_view, can_add, can_edit, can_delete,
                        can_print, can_export, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (role_id, permission_id, *values, now, now),
                )


def _permission_flags_for_role(role_name: str, module_name: str) -> dict[str, int]:
    flags = {
        "can_view": 0,
        "can_add": 0,
        "can_edit": 0,
        "can_delete": 0,
        "can_print": 0,
        "can_export": 0,
    }
    if role_name == ROLE_MASTER_ADMIN:
        return {key: 1 for key in flags}
    if role_name == ROLE_ACCOUNTANT and module_name in BUSINESS_MODULES:
        return {key: 1 for key in flags}
    if role_name == ROLE_ASSISTANT_ACCOUNTANT:
        if module_name in ROUTINE_TRANSACTION_MODULES:
            flags.update({"can_view": 1, "can_add": 1, "can_edit": 1, "can_print": 1})
        if module_name in REPORT_MODULES:
            flags.update({"can_view": 1, "can_print": 1, "can_export": 1})
    if role_name == ROLE_VIEWER and module_name in VIEWER_MODULES:
        flags["can_view"] = 1
    return flags


def _seed_admin_user(connection, company_id: int, branch_id: int, role_id: int, now: str) -> int:
    row = connection.execute(
        "SELECT id FROM users WHERE company_id = ? AND username = 'admin'",
        (company_id,),
    ).fetchone()
    if row:
        return row["id"]
    password_hash, password_salt = hash_password("mdnuniball")
    cursor = connection.execute(
        """
        INSERT INTO users (
            company_id, username, password_hash, password_salt, full_name, email,
            mobile, role_id, default_branch_id, is_master_user, is_active,
            must_change_password, created_at, updated_at, last_login
        ) VALUES (?, 'admin', ?, ?, 'Master Admin', '', '', ?, ?, 1, 1, 0, ?, ?, NULL)
        """,
        (company_id, password_hash, password_salt, role_id, branch_id, now, now),
    )
    return int(cursor.lastrowid)


def _seed_user_branch(connection, user_id: int, branch_id: int, now: str) -> None:
    if connection.execute(
        "SELECT id FROM user_branches WHERE user_id = ? AND branch_id = ?",
        (user_id, branch_id),
    ).fetchone():
        return
    connection.execute(
        """
        INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (user_id, branch_id, now, now),
    )


def _seed_accounts(connection, company_id: int, branch_id: int, now: str) -> None:
    for code, name, account_type in DEFAULT_ACCOUNT_GROUPS:
        if connection.execute(
            "SELECT id FROM accounts WHERE company_id = ? AND branch_id = ? AND account_code = ?",
            (company_id, branch_id, code),
        ).fetchone():
            continue
        connection.execute(
            """
            INSERT INTO accounts (
                company_id, branch_id, account_code, account_name, account_type,
                parent_id, is_control_account, is_system_account, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, 1, 1, 1, ?, ?)
            """,
            (company_id, branch_id, code, name, account_type, now, now),
        )
