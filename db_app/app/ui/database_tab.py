from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class DatabaseTab(ttk.Frame):
    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=12)
        self.controller = controller
        self.logger = logger
        self.folder_var = tk.StringVar(value=str(controller.database_folder))
        self.status_var = tk.StringVar(value="No status checked yet.")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Database folder path").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(self, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse", command=self.browse).grid(row=0, column=2, sticky="ew")

        actions = ttk.Frame(self)
        actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Button(actions, text="Create Database", command=self.create_database).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Reset Database", command=self.reset_database).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Check Database", command=self.check_database).pack(side="left")

        ttk.Label(self, text="Database status").grid(row=2, column=0, sticky="nw", pady=6)
        status = ttk.Label(self, textvariable=self.status_var, justify="left")
        status.grid(row=2, column=1, columnspan=2, sticky="ew", padx=8, pady=6)

    def _sync_folder(self) -> Path:
        folder = Path(self.folder_var.get()).expanduser()
        return self.controller.set_database_folder(folder)

    def browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if folder:
            self.folder_var.set(folder)
            self._sync_folder()

    def create_database(self) -> None:
        try:
            path = self._sync_folder()
            if path.exists():
                if not messagebox.askyesno(
                    "Database exists",
                    f"{path} already exists. Overwrite and recreate it?",
                ):
                    self.logger.info("Create database cancelled.")
                    return
                self.controller.reset_database()
            else:
                self.controller.create_database()
            self.check_database()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Create Database", str(exc))

    def reset_database(self) -> None:
        try:
            path = self._sync_folder()
            if not messagebox.askyesno(
                "Reset Database",
                f"This will delete and recreate all tables in:\n{path}\n\nContinue?",
            ):
                self.logger.info("Reset database cancelled.")
                return
            self.controller.reset_database()
            self.check_database()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Reset Database", str(exc))

    def check_database(self) -> None:
        try:
            self._sync_folder()
            status = self.controller.check_status()
            self.status_var.set(
                "\n".join(
                    [
                        f"Path: {status['path']}",
                        f"Exists: {status['exists']}",
                        f"Tables: {status['tables']}",
                        f"Size: {status['size_bytes']} bytes",
                    ]
                )
            )
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Check Database", str(exc))
