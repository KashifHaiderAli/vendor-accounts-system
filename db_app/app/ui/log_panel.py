from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LogPanel(ttk.Frame):
    def __init__(self, master, logger) -> None:
        super().__init__(master)
        self.logger = logger
        self.status_var = tk.StringVar(value="Ready")

        ttk.Label(self, text="Status / Logs").pack(anchor="w", padx=8, pady=(4, 0))
        self.text = tk.Text(self, height=6, wrap="word", state="disabled")
        self.text.pack(fill="both", expand=True, padx=8, pady=4)
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", padx=8, pady=(0, 4))
        self.logger.subscribe(self.append)

    def append(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")
        self.status_var.set(line)

