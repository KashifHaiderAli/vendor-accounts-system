from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.constants import DB_APP_PASSWORD, DB_APP_USERNAME


class LoginWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Vendor Accounts DB App Login")
        self.geometry("420x230")
        self.resizable(False, False)
        self.authenticated = False
        self.failed_attempts = 0
        self.max_attempts = 3

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Enter DB App credentials.")

        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="DB App Login").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(frame, text="Username").grid(row=1, column=0, sticky="w", pady=6)
        username_entry = ttk.Entry(frame, textvariable=self.username_var)
        username_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(frame, text="Password").grid(row=2, column=0, sticky="w", pady=6)
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(frame, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="Login", command=self.try_login).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda _event: self.try_login())
        username_entry.focus_set()

    def try_login(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if username == DB_APP_USERNAME and password == DB_APP_PASSWORD:
            self.authenticated = True
            self.destroy()
            return

        self.failed_attempts += 1
        remaining = self.max_attempts - self.failed_attempts
        if remaining <= 0:
            messagebox.showerror("Login Failed", "Maximum login attempts reached. Closing DB App.")
            self.destroy()
            return

        self.password_var.set("")
        self.status_var.set(f"Invalid login. {remaining} attempt(s) remaining.")
        messagebox.showerror("Login Failed", "Invalid DB App username or password.")

