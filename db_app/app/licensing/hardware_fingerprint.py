from __future__ import annotations

import hashlib
import platform
import socket
import uuid


def fingerprint_source() -> str:
    parts = [
        platform.system(),
        platform.release(),
        platform.machine(),
        platform.processor(),
        socket.gethostname(),
        str(uuid.getnode()),
    ]
    return "|".join(part or "unknown" for part in parts)


def get_hardware_fingerprint() -> str:
    return hashlib.sha256(fingerprint_source().encode("utf-8")).hexdigest()

