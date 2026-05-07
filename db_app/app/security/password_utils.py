from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    actual_salt = salt or generate_salt()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt.encode("utf-8"),
        120_000,
    )
    return digest.hex(), actual_salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)

