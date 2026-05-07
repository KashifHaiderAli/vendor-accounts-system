from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def generate_license_key(license_type: str, hardware_fingerprint: str, start_date: str) -> str:
    source = f"{license_type.upper()}|{hardware_fingerprint}|{start_date}|VendorAccountsDBApp"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    return "-".join([digest[index : index + 5] for index in range(0, 25, 5)])


def expiry_for_license(license_type: str, start_date: str) -> tuple[str | None, int]:
    if license_type.lower() == "lifetime":
        return None, 1
    start = parse_date(start_date)
    days = 30 if license_type.lower() == "trial" else 365
    return (start + timedelta(days=days)).isoformat(), 0

