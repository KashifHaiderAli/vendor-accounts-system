from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from authentication.auth_utils import dictfetchone
from core.context_processors import app_context


class Command(BaseCommand):
    help = "Verify sidebar heading and Settings submenu links point to the intended routes."

    HEADING_LINKS = {
        "Masters": ("masters:index", "/masters/"),
        "Sales": ("sales:index", "/sales/"),
        "Purchases": ("purchases:index", "/purchases/"),
        "Services": ("services:index", "/services/"),
        "Reports": ("reports:index", "/reports/"),
        "System": ("backup:index", "/system/"),
    }

    def handle(self, *args, **options):
        session_context = self.get_login_context()
        if not session_context:
            self.stdout.write(self.style.ERROR("FAIL: active master/admin user, company, and branch are required."))
            return

        request = self.build_request("/", session_context)
        rendered = render_to_string("partials/sidebar.html", app_context(request), request=request)

        failures = 0
        for label, (url_name, expected_path) in self.HEADING_LINKS.items():
            actual_path = reverse(url_name)
            if actual_path != expected_path:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {label}: route {url_name} resolved to {actual_path}, expected {expected_path}"))
                continue
            expected_link = f'href="{expected_path}"'
            if expected_link not in rendered:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {label}: heading link {expected_path} not found in sidebar."))
            else:
                self.stdout.write(f"PASS {label}: heading links to {expected_path}")

        users_roles_url = reverse("settings_module:users_roles")
        role_management_url = reverse("settings_module:role_management")
        if users_roles_url == "/masters/":
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL Users & Roles: still points to /masters/."))
        else:
            self.stdout.write(f"PASS Users & Roles: links to {users_roles_url}")
        if role_management_url == "/masters/":
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL Role Management: still points to /masters/."))
        else:
            self.stdout.write(f"PASS Role Management: links to {role_management_url}")
        if users_roles_url == role_management_url:
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL Settings: Users & Roles and Role Management have the same href."))
        else:
            self.stdout.write("PASS Settings: Users & Roles and Role Management have different hrefs.")

        for label, url in [("Users & Roles", users_roles_url), ("Role Management", role_management_url)]:
            if f'href="{url}"' not in rendered:
                failures += 1
                self.stdout.write(self.style.ERROR(f"FAIL {label}: submenu link {url} not found in sidebar."))

        users_request = self.build_request(users_roles_url, session_context)
        users_rendered = render_to_string("partials/sidebar.html", app_context(users_request), request=users_request)
        roles_request = self.build_request(role_management_url, session_context)
        roles_rendered = render_to_string("partials/sidebar.html", app_context(roles_request), request=roles_request)
        if self.link_is_active(users_rendered, role_management_url):
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL Users & Roles: Role Management is active on Users & Roles page."))
        else:
            self.stdout.write("PASS Users & Roles: Role Management is not active.")
        if self.link_is_active(roles_rendered, users_roles_url):
            failures += 1
            self.stdout.write(self.style.ERROR("FAIL Role Management: Users & Roles is active on Role Management page."))
        else:
            self.stdout.write("PASS Role Management: Users & Roles is not active.")

        if failures:
            self.stdout.write(self.style.ERROR(f"FAIL: {failures} sidebar link check(s) failed."))
            return
        self.stdout.write(self.style.SUCCESS("PASS: sidebar links ready."))

    def build_request(self, path, session_context):
        request = RequestFactory().get(path)
        request.session = dict(session_context)
        return request

    def link_is_active(self, html, href):
        active_fragment = f'class="active" href="{href}"'
        return active_fragment in html

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
            cursor.execute(
                "SELECT * FROM branches WHERE company_id=%s AND is_active=1 ORDER BY is_head_office DESC, id LIMIT 1",
                [user["company_id"]],
            )
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
