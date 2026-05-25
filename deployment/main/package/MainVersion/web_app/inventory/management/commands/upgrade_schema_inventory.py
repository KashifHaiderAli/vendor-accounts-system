from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection

from core.inventory_schema import ITEM_SERVICE_COLUMNS, SALES_RETURN_COLUMNS, STOCK_INDEX_SQL, STOCK_TABLE_SQL


class Command(BaseCommand):
    help = "Safely add inventory fields and stock movement tables using raw SQL."

    def handle(self, *args, **options):
        added_columns = 0
        created_objects = 0
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(item_services)")
            existing = {row[1] for row in cursor.fetchall()}
            for column, definition in ITEM_SERVICE_COLUMNS:
                if column not in existing:
                    cursor.execute(f"ALTER TABLE item_services ADD COLUMN {column} {definition}")
                    added_columns += 1

            cursor.execute("PRAGMA table_info(sales_returns)")
            existing_return = {row[1] for row in cursor.fetchall()}
            for column, definition in SALES_RETURN_COLUMNS:
                if column not in existing_return:
                    cursor.execute(f"ALTER TABLE sales_returns ADD COLUMN {column} {definition}")
                    added_columns += 1

            for sql in STOCK_TABLE_SQL + STOCK_INDEX_SQL:
                cursor.execute(sql)
                created_objects += 1

            if "track_inventory" not in existing:
                cursor.execute("UPDATE item_services SET track_inventory=0 WHERE lower(COALESCE(item_type,''))='service'")
                cursor.execute("UPDATE item_services SET track_inventory=1 WHERE lower(COALESCE(item_type,''))<>'service' OR item_type IS NULL")

        self.stdout.write(f"item_services columns added: {added_columns}")
        self.stdout.write(f"inventory tables/indexes ensured: {created_objects}")
        self.stdout.write(self.style.SUCCESS("PASS: inventory schema ready."))
