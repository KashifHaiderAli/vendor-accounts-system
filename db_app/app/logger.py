from __future__ import annotations

from datetime import datetime
from typing import Callable, List


class AppLogger:
    """Small UI-friendly logger that fans messages out to subscribed widgets."""

    def __init__(self) -> None:
        self._subscribers: List[Callable[[str], None]] = []
        self.last_action = ""

    def subscribe(self, callback: Callable[[str], None]) -> None:
        self._subscribers.append(callback)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.last_action = message
        for callback in self._subscribers:
            callback(line)

    def info(self, message: str) -> None:
        self.log(f"INFO: {message}")

    def error(self, message: str) -> None:
        self.log(f"ERROR: {message}")

