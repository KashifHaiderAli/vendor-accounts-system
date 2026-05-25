from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta


VALID_LICENSE_TYPES = {"trial", "annual", "lifetime"}


@dataclass(frozen=True)
class LicenseEvaluation:
    valid: bool
    reason: str


def parse_license_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def generate_license_key(license_type: str, hardware_fingerprint: str, start_date: str) -> str:
    source = f"{str(license_type).upper()}|{hardware_fingerprint}|{start_date}|VendorAccountsDBApp"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest().upper()
    return "-".join([digest[index : index + 5] for index in range(0, 25, 5)])


def expiry_for_license(license_type: str, start_date: str) -> tuple[str | None, int]:
    if str(license_type).lower() == "lifetime":
        return None, 1
    start = parse_license_date(start_date)
    if not start:
        raise ValueError("Invalid license start date.")
    days = 30 if str(license_type).lower() == "trial" else 365
    return (start + timedelta(days=days)).isoformat(), 0


def evaluate_license_record(record, expected_fingerprint: str, today: date | None = None) -> LicenseEvaluation:
    today = today or date.today()
    license_type = str(record.get("license_type") or "").strip()
    license_type_key = license_type.lower()
    if license_type_key not in VALID_LICENSE_TYPES:
        return LicenseEvaluation(False, "unsupported license type")
    if int(record.get("is_active") or 0) != 1:
        return LicenseEvaluation(False, "inactive license")
    if str(record.get("hardware_fingerprint") or "").strip() != expected_fingerprint:
        return LicenseEvaluation(False, "hardware fingerprint mismatch")

    start_date = parse_license_date(record.get("start_date"))
    if not start_date:
        return LicenseEvaluation(False, "missing or invalid start date")

    expected_key = generate_license_key(license_type, expected_fingerprint, start_date.isoformat())
    if str(record.get("license_key") or "").strip().upper() != expected_key:
        return LicenseEvaluation(False, "license key mismatch")

    if int(record.get("is_lifetime") or 0) == 1 or license_type_key == "lifetime":
        return LicenseEvaluation(True, "lifetime license")

    expiry_date = parse_license_date(record.get("expiry_date"))
    if not expiry_date:
        return LicenseEvaluation(False, "missing or invalid expiry date")
    if start_date <= today <= expiry_date:
        return LicenseEvaluation(True, "date-limited license valid")
    return LicenseEvaluation(False, "license expired or not started")
