from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.utils.date_utils import now_iso


class BranchesTab(ttk.Frame):
    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=12)
        self.controller = controller
        self.logger = logger
        self.selected_branch_id: int | None = None
        self.vars = {
            "branch_code": tk.StringVar(),
            "branch_name": tk.StringVar(),
            "address": tk.StringVar(),
            "phone": tk.StringVar(),
            "mobile": tk.StringVar(),
            "email": tk.StringVar(),
            "is_head_office": tk.BooleanVar(value=False),
            "is_active": tk.BooleanVar(value=True),
        }
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        actions = ttk.Frame(self)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Load Branches", command=self.load_branches).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="New Branch", command=self.new_branch).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Branch", command=self.save_branch).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Activate/Deactivate", command=self.toggle_active).pack(side="left")

        columns = ("id", "code", "name", "head_office", "active", "phone", "email")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        for column, heading, width in [
            ("id", "ID", 60),
            ("code", "Code", 100),
            ("name", "Branch Name", 220),
            ("head_office", "Head Office", 100),
            ("active", "Active", 80),
            ("phone", "Phone", 120),
            ("email", "Email", 180),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.LabelFrame(self, text="Branch Form", padding=8)
        form.grid(row=2, column=0, sticky="ew", pady=10)
        for column in (1, 3):
            form.columnconfigure(column, weight=1)
        fields = [
            ("branch_code", "Branch code"),
            ("branch_name", "Branch name"),
            ("address", "Address"),
            ("phone", "Phone"),
            ("mobile", "Mobile"),
            ("email", "Email"),
        ]
        for index, (field, label) in enumerate(fields):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", pady=3)
            ttk.Entry(form, textvariable=self.vars[field]).grid(row=row, column=col + 1, sticky="ew", padx=8, pady=3)
        ttk.Checkbutton(form, text="Head Office", variable=self.vars["is_head_office"]).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(form, text="Active", variable=self.vars["is_active"]).grid(row=3, column=1, sticky="w")

    def load_branches(self) -> None:
        try:
            self.tree.delete(*self.tree.get_children())
            company_id, _ = self.controller.default_company_and_branch()
            with self.controller.connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM branches WHERE company_id = ? ORDER BY is_head_office DESC, branch_name",
                    (company_id,),
                ).fetchall()
            for row in rows:
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        row["id"],
                        row["branch_code"],
                        row["branch_name"],
                        "Yes" if row["is_head_office"] else "No",
                        "Yes" if row["is_active"] else "No",
                        row["phone"] or "",
                        row["email"] or "",
                    ),
                )
            self.logger.info("Branches loaded.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Branches", str(exc))

    def new_branch(self) -> None:
        self.selected_branch_id = None
        for key, variable in self.vars.items():
            variable.set(False if key == "is_head_office" else True if key == "is_active" else "")
        self.logger.info("New branch form ready.")

    def _on_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        branch_id = int(self.tree.item(selected[0], "values")[0])
        try:
            with self.controller.connect() as connection:
                row = connection.execute("SELECT * FROM branches WHERE id = ?", (branch_id,)).fetchone()
            if not row:
                return
            self.selected_branch_id = row["id"]
            for key in ("branch_code", "branch_name", "address", "phone", "mobile", "email"):
                self.vars[key].set(row[key] or "")
            self.vars["is_head_office"].set(bool(row["is_head_office"]))
            self.vars["is_active"].set(bool(row["is_active"]))
        except Exception as exc:
            self.logger.error(str(exc))

    def save_branch(self) -> None:
        try:
            now = now_iso()
            company_id, _ = self.controller.default_company_and_branch()
            code = self.vars["branch_code"].get().strip()
            name = self.vars["branch_name"].get().strip()
            if not code or not name:
                raise ValueError("Branch code and branch name are required.")
            with self.controller.connect() as connection:
                if self.vars["is_head_office"].get():
                    connection.execute(
                        "UPDATE branches SET is_head_office = 0, updated_at = ? WHERE company_id = ? AND id <> ?",
                        (now, company_id, self.selected_branch_id or 0),
                    )
                if self.selected_branch_id:
                    connection.execute(
                        """
                        UPDATE branches
                        SET branch_code = ?, branch_name = ?, address = ?, phone = ?, mobile = ?,
                            email = ?, is_head_office = ?, is_active = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            code,
                            name,
                            self.vars["address"].get().strip(),
                            self.vars["phone"].get().strip(),
                            self.vars["mobile"].get().strip(),
                            self.vars["email"].get().strip(),
                            int(self.vars["is_head_office"].get()),
                            int(self.vars["is_active"].get()),
                            now,
                            self.selected_branch_id,
                        ),
                    )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO branches (
                            company_id, branch_code, branch_name, address, phone, mobile, email,
                            is_head_office, is_active, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            company_id,
                            code,
                            name,
                            self.vars["address"].get().strip(),
                            self.vars["phone"].get().strip(),
                            self.vars["mobile"].get().strip(),
                            self.vars["email"].get().strip(),
                            int(self.vars["is_head_office"].get()),
                            int(self.vars["is_active"].get()),
                            now,
                            now,
                        ),
                    )
                    self.selected_branch_id = int(cursor.lastrowid)
                active_count = connection.execute(
                    "SELECT COUNT(*) FROM branches WHERE company_id = ? AND is_active = 1",
                    (company_id,),
                ).fetchone()[0]
                if active_count < 1:
                    raise ValueError("At least one active branch must remain.")
                connection.commit()
            self.logger.info("Branch saved.")
            self.load_branches()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Branches", str(exc))

    def toggle_active(self) -> None:
        if not self.selected_branch_id:
            messagebox.showwarning("Branches", "Select a branch first.")
            return
        try:
            now = now_iso()
            company_id, _ = self.controller.default_company_and_branch()
            with self.controller.connect() as connection:
                row = connection.execute("SELECT * FROM branches WHERE id = ?", (self.selected_branch_id,)).fetchone()
                if row["is_head_office"] and row["is_active"]:
                    raise ValueError("Head Office branch cannot be deactivated.")
                new_active = 0 if row["is_active"] else 1
                if new_active == 0:
                    active_count = connection.execute(
                        "SELECT COUNT(*) FROM branches WHERE company_id = ? AND is_active = 1",
                        (company_id,),
                    ).fetchone()[0]
                    if active_count <= 1:
                        raise ValueError("At least one active branch must remain.")
                connection.execute(
                    "UPDATE branches SET is_active = ?, updated_at = ? WHERE id = ?",
                    (new_active, now, self.selected_branch_id),
                )
                connection.commit()
            self.logger.info("Branch active status updated.")
            self.load_branches()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Branches", str(exc))

