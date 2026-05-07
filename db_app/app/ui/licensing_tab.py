from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.licensing.hardware_fingerprint import get_hardware_fingerprint
from app.licensing.license_generator import expiry_for_license, generate_license_key
from app.utils.date_utils import today_iso, now_iso


class LicensingTab(ttk.Frame):
    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=12)
        self.controller = controller
        self.logger = logger
        self.vars = {
            "hardware_fingerprint": tk.StringVar(),
            "license_type": tk.StringVar(value="Trial"),
            "issue_date": tk.StringVar(value=today_iso()),
            "start_date": tk.StringVar(value=today_iso()),
            "expiry_date": tk.StringVar(),
            "license_key": tk.StringVar(),
        }
        self._build()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        fields = [
            ("hardware_fingerprint", "Hardware Fingerprint"),
            ("license_type", "License Type"),
            ("issue_date", "Issue Date"),
            ("start_date", "Start Date"),
            ("expiry_date", "Expiry Date"),
            ("license_key", "Generated License Key"),
        ]
        for row, (field, label) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=5)
            if field == "license_type":
                ttk.Combobox(
                    self,
                    textvariable=self.vars[field],
                    values=["Trial", "Annual", "Lifetime"],
                    state="readonly",
                ).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
            else:
                ttk.Entry(self, textvariable=self.vars[field]).grid(row=row, column=1, sticky="ew", padx=8, pady=5)

        actions = ttk.Frame(self)
        actions.grid(row=6, column=0, columnspan=2, sticky="w", pady=12)
        ttk.Button(actions, text="Get Hardware Fingerprint", command=self.get_fingerprint).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generate Trial Key", command=lambda: self.generate_key("Trial")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generate Annual Key", command=lambda: self.generate_key("Annual")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generate Lifetime Key", command=lambda: self.generate_key("Lifetime")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save License Record", command=self.save_license).pack(side="left")

    def get_fingerprint(self) -> None:
        fingerprint = get_hardware_fingerprint()
        self.vars["hardware_fingerprint"].set(fingerprint)
        self.logger.info("Hardware fingerprint generated.")

    def generate_key(self, license_type: str | None = None) -> None:
        try:
            selected_type = license_type or self.vars["license_type"].get()
            self.vars["license_type"].set(selected_type)
            if not self.vars["hardware_fingerprint"].get():
                self.get_fingerprint()
            start_date = self.vars["start_date"].get().strip() or today_iso()
            expiry_date, _ = expiry_for_license(selected_type, start_date)
            license_key = generate_license_key(
                selected_type,
                self.vars["hardware_fingerprint"].get().strip(),
                start_date,
            )
            self.vars["start_date"].set(start_date)
            self.vars["expiry_date"].set(expiry_date or "")
            self.vars["license_key"].set(license_key)
            self.logger.info(f"{selected_type} license key generated.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Licensing", str(exc))

    def save_license(self) -> None:
        try:
            if not self.vars["license_key"].get().strip():
                self.generate_key()
            company_id, branch_id = self.controller.default_company_and_branch()
            license_type = self.vars["license_type"].get().strip()
            _, is_lifetime = expiry_for_license(license_type, self.vars["start_date"].get().strip())
            now = now_iso()
            with self.controller.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO license_records (
                        company_id, branch_id, license_type, hardware_fingerprint, license_key,
                        issue_date, start_date, expiry_date, is_lifetime, is_active, remarks,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        company_id,
                        branch_id,
                        license_type,
                        self.vars["hardware_fingerprint"].get().strip(),
                        self.vars["license_key"].get().strip(),
                        self.vars["issue_date"].get().strip(),
                        self.vars["start_date"].get().strip(),
                        self.vars["expiry_date"].get().strip() or None,
                        is_lifetime,
                        "Placeholder local license generated by DB App.",
                        now,
                        now,
                    ),
                )
                connection.commit()
            self.logger.info("License record saved.")
            messagebox.showinfo("Licensing", "License record saved.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Licensing", str(exc))

