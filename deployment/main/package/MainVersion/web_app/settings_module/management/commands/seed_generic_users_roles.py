from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection

from authentication.auth_utils import dictfetchall, dictfetchone
from settings_module import user_role_services


GENERIC_ROLES = {
    "Admin": {
        "description": "Broad application access without Master Admin flag.",
        "allow": "admin",
    },
    "Accountant": {
        "description": "Accounting, sales, purchases, payments, and reports.",
        "allow": "accountant",
    },
    "Sales User": {
        "description": "Sales workflow and sales reports.",
        "allow": "sales",
    },
    "Purchase User": {
        "description": "Purchase workflow and purchase reports.",
        "allow": "purchase",
    },
    "Viewer / Auditor": {
        "description": "Read-only audit and report access.",
        "allow": "viewer",
    },
}

GENERIC_USERS = [
    ("admin2", "Admin User", "admin2@example.com", "Admin"),
    ("accountant", "Accountant", "accountant@example.com", "Accountant"),
    ("sales", "Sales User", "sales@example.com", "Sales User"),
    ("purchase", "Purchase User", "purchase@example.com", "Purchase User"),
    ("auditor", "Viewer Auditor", "auditor@example.com", "Viewer / Auditor"),
]


class Command(BaseCommand):
    help = "Create generic roles and users for client testing."

    def handle(self, *args, **options):
        scope = self.get_scope()
        if not scope:
            self.stdout.write(self.style.ERROR("FAIL: active company and branch are required."))
            return
        company_id, branch_id = scope["company_id"], scope["branch_id"]
        now = user_role_services.now_text()
        created_roles = skipped_roles = created_users = skipped_users = 0

        role_ids = {}
        try:
            with connection.cursor() as cursor:
                for role_name, info in GENERIC_ROLES.items():
                    cursor.execute("SELECT id FROM user_roles WHERE company_id=%s AND role_name=%s", [company_id, role_name])
                    row = cursor.fetchone()
                    if row:
                        role_ids[role_name] = row[0]
                        skipped_roles += 1
                    else:
                        cursor.execute(
                            """
                            INSERT INTO user_roles (company_id, role_name, description, is_system_role, is_active, created_at, updated_at)
                            VALUES (%s,%s,%s,0,1,%s,%s)
                            """,
                            [company_id, role_name, info["description"], now, now],
                        )
                        role_ids[role_name] = cursor.lastrowid
                        created_roles += 1
                    self.apply_role_permissions(role_ids[role_name], info["allow"], now)

                for username, full_name, email, role_name in GENERIC_USERS:
                    cursor.execute("SELECT id FROM users WHERE company_id=%s AND lower(username)=lower(%s)", [company_id, username])
                    row = cursor.fetchone()
                    if row:
                        skipped_users += 1
                        self.ensure_branch(row[0], branch_id, now)
                        continue
                    password_hash, password_salt = user_role_services.make_password(user_role_services.TEMP_PASSWORD)
                    cursor.execute(
                        """
                        INSERT INTO users (
                            company_id, username, password_hash, password_salt, full_name, email, mobile,
                            role_id, default_branch_id, is_master_user, is_active, must_change_password,
                            created_at, updated_at, last_login
                        ) VALUES (%s,%s,%s,%s,%s,%s,'',%s,%s,0,1,1,%s,%s,NULL)
                        """,
                        [company_id, username, password_hash, password_salt, full_name, email, role_ids[role_name], branch_id, now, now],
                    )
                    self.ensure_branch(cursor.lastrowid, branch_id, now)
                    created_users += 1
        except DatabaseError as exc:
            self.stdout.write(self.style.ERROR(f"FAIL: unable to seed generic users and roles: {exc}"))
            return

        self.stdout.write(f"roles created: {created_roles}")
        self.stdout.write(f"roles skipped: {skipped_roles}")
        self.stdout.write(f"users created: {created_users}")
        self.stdout.write(f"users skipped: {skipped_users}")
        self.stdout.write(f"Temporary password for generic users: {user_role_services.TEMP_PASSWORD}")
        self.stdout.write(self.style.SUCCESS("PASS: generic users and roles ready."))

    def apply_role_permissions(self, role_id, policy, now):
        permissions = self.permissions()
        for permission in permissions:
            flags = self.flags_for(policy, permission["permission_code"])
            self.upsert_permission(role_id, permission["id"], flags, now)

    def permissions(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM permissions ORDER BY permission_code")
            return dictfetchall(cursor)

    def flags_for(self, policy, code):
        flags = {"view": 0, "add": 0, "edit": 0, "delete": 0, "print": 0, "export": 0}
        reports = {"customer_reports", "supplier_reports", "sales_reports", "purchase_reports", "service_reports", "accounting_reports"}
        sales = {"customers", "quotations", "customer_confirmations", "delivery_challans", "sales_invoices", "customer_receipts", "sales_returns", "sales_reports"}
        purchases = {"suppliers", "supplier_purchases", "supplier_payments", "purchase_returns", "purchase_reports"}
        accounting = {"accounts", "accounting_reports", "cash_bank_accounts", "expense_heads", "supplier_payments", "customer_receipts", "sales_invoices", "supplier_purchases", "sales_returns", "purchase_returns"}
        if policy == "admin":
            if code not in {"backup_restore", "licensing"}:
                flags = {key: 1 for key in flags}
        elif policy == "accountant":
            if code in accounting or code in reports or code in {"dashboard", "customers", "suppliers", "item_services"}:
                flags = {key: 1 for key in flags}
            if code in reports:
                flags.update({"add": 0, "edit": 0, "delete": 0})
        elif policy == "sales":
            if code in sales or code == "dashboard":
                flags.update({"view": 1, "add": 1, "edit": 1, "print": 1, "export": 1})
            if code in {"sales_reports"}:
                flags.update({"add": 0, "edit": 0, "delete": 0})
        elif policy == "purchase":
            if code in purchases or code == "dashboard":
                flags.update({"view": 1, "add": 1, "edit": 1, "print": 1, "export": 1})
            if code in {"purchase_reports"}:
                flags.update({"add": 0, "edit": 0, "delete": 0})
        elif policy == "viewer":
            if code in reports or code in {"dashboard", "customers", "suppliers", "item_services", "sales_invoices", "supplier_purchases", "quotations", "delivery_challans", "customer_receipts", "supplier_payments"}:
                flags.update({"view": 1, "print": 1, "export": 1})
        return flags

    def upsert_permission(self, role_id, permission_id, flags, now):
        values = [flags[action] for action in user_role_services.ACTIONS]
        with connection.cursor() as cursor:
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

    def ensure_branch(self, user_id, branch_id, now):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM user_branches WHERE user_id=%s AND branch_id=%s", [user_id, branch_id])
            if cursor.fetchone():
                return
            cursor.execute(
                "INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at) VALUES (%s,%s,1,%s,%s)",
                [user_id, branch_id, now, now],
            )

    def get_scope(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM companies WHERE is_active=1 ORDER BY id LIMIT 1")
            company = dictfetchone(cursor)
            if not company:
                return None
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, id LIMIT 1", [company["id"]])
            branch = dictfetchone(cursor)
            if not branch:
                return None
        return {"company_id": company["id"], "branch_id": branch["id"]}
