from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.test import RequestFactory
from django.urls import resolve, reverse

from authentication.auth_utils import dictfetchall, dictfetchone


class Command(BaseCommand):
    help = "Verify Users & Roles and Role Management pages, seed data, permissions, and sidebar links."

    def handle(self, *args, **options):
        context = self.get_login_context()
        if not context:
            self.stdout.write(self.style.ERROR("FAIL: active company, branch, and user are required."))
            return
        failures = 0
        failures += self.check_page("settings_module:users_roles", "Users & Roles", context)
        failures += self.check_page("settings_module:role_management", "Role Management", context)
        call_command("seed_generic_users_roles", verbosity=0)
        failures += self.check_generic_data(context["company_id"])
        failures += self.check_role_permissions()
        failures += self.check_sidebar_links(context)
        failures += self.check_self_deactivation_blocked(context)
        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} users/roles check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: users and roles pages ready."))

    def check_page(self, route_name, label, context):
        response = self.call_url(reverse(route_name), context)
        if response.status_code >= 400:
            self.stdout.write(self.style.ERROR(f"FAIL {label}: status {response.status_code}"))
            return 1
        content = response.content.decode("utf-8", errors="ignore").lower()
        if "under development" in content:
            self.stdout.write(self.style.ERROR(f"FAIL {label}: still shows under development."))
            return 1
        self.stdout.write(f"PASS {label}: page renders and is not placeholder.")
        return 0

    def check_generic_data(self, company_id):
        failures = 0
        with connection.cursor() as cursor:
            cursor.execute("SELECT role_name FROM user_roles WHERE company_id=%s AND role_name IN ('Admin','Accountant','Sales User','Purchase User','Viewer / Auditor')", [company_id])
            roles = {row[0] for row in cursor.fetchall()}
            cursor.execute("SELECT username, password_hash, role_id FROM users WHERE company_id=%s AND username IN ('admin2','accountant','sales','purchase','auditor')", [company_id])
            users = dictfetchall(cursor)
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM users u
                JOIN user_branches ub ON ub.user_id=u.id
                WHERE u.company_id=%s AND u.username IN ('admin2','accountant','sales','purchase','auditor')
                """,
                [company_id],
            )
            branch_count = int(cursor.fetchone()[0] or 0)
        if len(roles) != 5:
            failures += 1
            self.stdout.write(self.style.ERROR(f"FAIL generic roles: expected 5, got {len(roles)}"))
        else:
            self.stdout.write("PASS generic roles: created/skipped correctly.")
        if len(users) != 5:
            failures += 1
            self.stdout.write(self.style.ERROR(f"FAIL generic users: expected 5, got {len(users)}"))
        elif any(not user.get("password_hash") for user in users):
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL generic users: blank password hash found."))
        elif any(not user.get("role_id") for user in users):
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL generic users: user without role found."))
        else:
            self.stdout.write("PASS generic users: role and password hash present.")
        if branch_count < 5:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL generic users: missing branch access."))
        else:
            self.stdout.write("PASS generic users: branch access assigned.")
        return failures

    def check_role_permissions(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rp.*
                FROM user_roles r
                JOIN role_permissions rp ON rp.role_id=r.id
                WHERE r.role_name='Admin'
                LIMIT 1
                """
            )
            row = dictfetchone(cursor)
        if row:
            self.stdout.write("PASS role permissions: saved/read successfully.")
            return 0
        self.stdout.write(self.style.ERROR("FAIL role permissions: no Admin role permission mapping found."))
        return 1

    def check_sidebar_links(self, context):
        response = self.call_url("/", context)
        content = response.content.decode("utf-8", errors="ignore")
        users_url = reverse("settings_module:users_roles")
        roles_url = reverse("settings_module:role_management")
        failures = 0
        if users_url == "/masters/" or roles_url == "/masters/" or users_url == roles_url:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL sidebar: settings user/role links are wrong."))
        elif f'href="{users_url}"' not in content or f'href="{roles_url}"' not in content:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL sidebar: settings user/role links not rendered."))
        else:
            self.stdout.write("PASS sidebar: user and role links are correct and different.")
        return failures

    def check_self_deactivation_blocked(self, context):
        user_id = context["user_id"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM users WHERE id=%s", [user_id])
            before = int(cursor.fetchone()[0])
        response = self.call_url(reverse("settings_module:user_toggle_active", args=[user_id]), context)
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM users WHERE id=%s", [user_id])
            after = int(cursor.fetchone()[0])
        if before == after and response.status_code in {302, 200}:
            self.stdout.write("PASS safety: current admin cannot deactivate self.")
            return 0
        self.stdout.write(self.style.ERROR("FAIL safety: current admin self-deactivation was not blocked."))
        return 1

    def call_url(self, url, session_context):
        request = RequestFactory(HTTP_HOST="127.0.0.1").get(url)
        request.session = dict(session_context)
        request._messages = FallbackStorage(request)
        match = resolve(request.path_info)
        return match.func(request, *match.args, **match.kwargs)

    def get_login_context(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.*, r.role_name, c.company_name
                FROM users u
                JOIN user_roles r ON r.id=u.role_id
                JOIN companies c ON c.id=u.company_id
                WHERE u.is_active=1
                ORDER BY u.is_master_user DESC, u.id
                LIMIT 1
                """
            )
            user = dictfetchone(cursor)
            if not user:
                return None
            cursor.execute("SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, id LIMIT 1", [user["company_id"]])
            branch = dictfetchone(cursor)
            if not branch:
                return None
        return {
            "user_id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role_id": user["role_id"],
            "role_name": user["role_name"],
            "company_id": user["company_id"],
            "company_name": user["company_name"],
            "current_branch_id": branch["id"],
            "current_branch_name": branch["branch_name"],
            "is_master_user": int(user.get("is_master_user") or 0),
        }
