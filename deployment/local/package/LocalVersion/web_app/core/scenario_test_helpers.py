from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import connection

from authentication.auth_utils import dictfetchall, dictfetchone


@dataclass
class FakeRequest:
    session: dict
    META: dict | None = None
    GET: dict | None = None

    def __post_init__(self):
        if self.META is None:
            self.META = {"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "scenario-test"}
        if self.GET is None:
            self.GET = {}


def money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def row(sql: str, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchone(cursor)


def rows(sql: str, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return dictfetchall(cursor)


def scalar(sql: str, params=None, default=0):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        result = cursor.fetchone()
    return result[0] if result and result[0] is not None else default


def table_exists(table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=%s", [table_name])
        return cursor.fetchone() is not None


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    with connection.cursor() as cursor:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return any(item[1] == column_name for item in cursor.fetchall())


def journal_totals(journal_entry_id):
    result = row(
        """
        SELECT COALESCE(SUM(debit),0) AS debit, COALESCE(SUM(credit),0) AS credit
        FROM journal_entry_lines
        WHERE journal_entry_id=%s
        """,
        [journal_entry_id],
    ) or {"debit": 0, "credit": 0}
    return money(result.get("debit")), money(result.get("credit"))


def journal_balanced(journal_entry_id) -> bool:
    debit, credit = journal_totals(journal_entry_id)
    return debit == credit and debit > 0
