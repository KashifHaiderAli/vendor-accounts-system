from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.utils.date_utils import now_iso


class CompanyTab(ttk.Frame):
    COMPANY_FIELDS = [
        ("company_name", "Company name"),
        ("legal_name", "Legal name"),
        ("address", "Address"),
        ("phone", "Phone"),
        ("mobile", "Mobile"),
        ("email", "Email"),
        ("website", "Website"),
        ("ntn", "NTN"),
        ("strn", "STRN"),
        ("logo_path", "Logo path"),
    ]
    SETTINGS_FIELDS = [
        ("quotation_footer", "Quotation footer"),
        ("invoice_footer", "Invoice footer"),
        ("bank_details", "Bank details"),
        ("authorized_person_name", "Authorized person name"),
    ]

    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=12)
        self.controller = controller
        self.logger = logger
        self.vars = {field: tk.StringVar() for field, _ in self.COMPANY_FIELDS + self.SETTINGS_FIELDS}
        self.company_id: int | None = None
        self.settings_id: int | None = None
        self._build()

    def _build(self) -> None:
        for column in (1, 3):
            self.columnconfigure(column, weight=1)

        all_fields = self.COMPANY_FIELDS + self.SETTINGS_FIELDS
        for index, (field, label) in enumerate(all_fields):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(self, text=label).grid(row=row, column=col, sticky="w", pady=4)
            ttk.Entry(self, textvariable=self.vars[field]).grid(row=row, column=col + 1, sticky="ew", padx=8, pady=4)

        actions = ttk.Frame(self)
        actions.grid(row=8, column=0, columnspan=4, sticky="w", pady=12)
        ttk.Button(actions, text="Load Company Setup", command=self.load_company).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Company Setup", command=self.save_company).pack(side="left")

    def load_company(self) -> None:
        try:
            with self.controller.connect() as connection:
                company = connection.execute("SELECT * FROM companies ORDER BY id LIMIT 1").fetchone()
                if not company:
                    raise RuntimeError("No company record found.")
                self.company_id = company["id"]
                settings = connection.execute(
                    "SELECT * FROM company_settings WHERE company_id = ? ORDER BY id LIMIT 1",
                    (self.company_id,),
                ).fetchone()
                self.settings_id = settings["id"] if settings else None
                for field, _ in self.COMPANY_FIELDS:
                    self.vars[field].set(company[field] or "")
                for field, _ in self.SETTINGS_FIELDS:
                    self.vars[field].set(settings[field] if settings and settings[field] else "")
            self.logger.info("Company setup loaded.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Company Setup", str(exc))

    def save_company(self) -> None:
        try:
            now = now_iso()
            with self.controller.connect() as connection:
                company = connection.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
                if not company:
                    raise RuntimeError("No company record found.")
                self.company_id = company["id"]
                connection.execute(
                    """
                    UPDATE companies
                    SET company_name = ?, legal_name = ?, address = ?, phone = ?, mobile = ?,
                        email = ?, website = ?, ntn = ?, strn = ?, logo_path = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        self.vars["company_name"].get().strip() or "Your Company Name",
                        self.vars["legal_name"].get().strip(),
                        self.vars["address"].get().strip(),
                        self.vars["phone"].get().strip(),
                        self.vars["mobile"].get().strip(),
                        self.vars["email"].get().strip(),
                        self.vars["website"].get().strip(),
                        self.vars["ntn"].get().strip(),
                        self.vars["strn"].get().strip(),
                        self.vars["logo_path"].get().strip(),
                        now,
                        self.company_id,
                    ),
                )
                settings = connection.execute(
                    "SELECT id FROM company_settings WHERE company_id = ? ORDER BY id LIMIT 1",
                    (self.company_id,),
                ).fetchone()
                if settings:
                    connection.execute(
                        """
                        UPDATE company_settings
                        SET quotation_footer = ?, invoice_footer = ?, bank_details = ?,
                            authorized_person_name = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            self.vars["quotation_footer"].get().strip(),
                            self.vars["invoice_footer"].get().strip(),
                            self.vars["bank_details"].get().strip(),
                            self.vars["authorized_person_name"].get().strip(),
                            now,
                            settings["id"],
                        ),
                    )
                else:
                    _, branch_id = self.controller.default_company_and_branch()
                    connection.execute(
                        """
                        INSERT INTO company_settings (
                            company_id, branch_id, quotation_footer, invoice_footer, bank_details,
                            authorized_person_name, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.company_id,
                            branch_id,
                            self.vars["quotation_footer"].get().strip(),
                            self.vars["invoice_footer"].get().strip(),
                            self.vars["bank_details"].get().strip(),
                            self.vars["authorized_person_name"].get().strip(),
                            now,
                            now,
                        ),
                    )
                connection.commit()
            self.logger.info("Company setup saved.")
            messagebox.showinfo("Company Setup", "Company setup saved.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Company Setup", str(exc))

