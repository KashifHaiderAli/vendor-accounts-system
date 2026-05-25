from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from core.edition_utils import database_file_name, env_tax_enabled, get_edition_name, is_tax_enabled


class Command(BaseCommand):
    help = "Verify LocalVersion database, edition, and license page basics."

    def handle(self, *args, **options):
        db_path = os.getenv("VENDOR_ACCOUNTS_DB_PATH", "")
        checks = [
            ("LocalVersion DB path", db_path.endswith(r"LocalVersion\data\vendor_accounts_local.db") or db_path.endswith("/LocalVersion/data/vendor_accounts_local.db")),
            ("ENABLE_TAX=False", not env_tax_enabled()),
            ("tax helper false", not is_tax_enabled()),
            ("edition label", get_edition_name() == "LocalVersion"),
            ("database filename", database_file_name() == "vendor_accounts_local.db"),
        ]
        client = Client()
        response = client.get("/license/")
        checks.append(("license page route responds", response.status_code in {200, 302}))

        failed = [label for label, ok in checks if not ok]
        for label, ok in checks:
            self.stdout.write(f"{'PASS' if ok else 'FAIL'} - {label}")
        if failed:
            raise CommandError("LocalVersion license checks failed: " + ", ".join(failed))
        self.stdout.write(self.style.SUCCESS("PASS local version license checks"))
