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
        self.username_placeholder = "ad..."
        self.password_placeholder = "inf..."

        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="DB App Login").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(frame, text="Username").grid(row=1, column=0, sticky="w", pady=6)
        self.username_entry = ttk.Entry(frame, textvariable=self.username_var)
        self.username_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(frame, text="Password").grid(row=2, column=0, sticky="w", pady=6)
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var)
        self.password_entry.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(frame, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="Login", command=self.try_login).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="left")

        self.bind("<Return>", lambda _event: self.try_login())
        self.username_entry.bind("<FocusIn>", lambda _event: self._clear_placeholder("username"))
        self.username_entry.bind("<FocusOut>", lambda _event: self._restore_placeholder("username"))
        self.password_entry.bind("<FocusIn>", lambda _event: self._clear_placeholder("password"))
        self.password_entry.bind("<FocusOut>", lambda _event: self._restore_placeholder("password"))
        self._restore_placeholder("username")
        self._restore_placeholder("password")
        self.username_entry.focus_set()

    def try_login(self) -> None:
        username = "" if self._is_placeholder("username") else self.username_var.get().strip()
        password = "" if self._is_placeholder("password") else self.password_var.get()
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
        self._restore_placeholder("password")
        self.status_var.set(f"Invalid login. {remaining} attempt(s) remaining.")
        messagebox.showerror("Login Failed", "Invalid DB App username or password.")

    def _is_placeholder(self, field: str) -> bool:
        if field == "username":
            return self.username_var.get() == self.username_placeholder
        return self.password_var.get() == self.password_placeholder and self.password_entry.cget("show") == ""

    def _clear_placeholder(self, field: str) -> None:
        if field == "username" and self.username_var.get() == self.username_placeholder:
            self.username_var.set("")
            return
        if field == "password" and self._is_placeholder("password"):
            self.password_var.set("")
            self.password_entry.configure(show="*")

    def _restore_placeholder(self, field: str) -> None:
        if field == "username" and not self.username_var.get():
            self.username_var.set(self.username_placeholder)
            return
        if field == "password" and not self.password_var.get():
            self.password_entry.configure(show="")
            self.password_var.set(self.password_placeholder)
