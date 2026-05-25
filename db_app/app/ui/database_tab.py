from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk


class DatabaseTab(ttk.Frame):
    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=12)
        self.controller = controller
        self.logger = logger
        self.folder_var = tk.StringVar(value=str(controller.database_folder))
        self.database_file_var = tk.StringVar(value=str(controller.database_path))
        self.status_var = tk.StringVar(value="No status checked yet.")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="Database folder path").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(self, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Browse", command=self.browse).grid(row=0, column=2, sticky="ew")

        ttk.Label(self, text="Current Database").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(self, textvariable=self.database_file_var).grid(row=1, column=1, sticky="ew", padx=8)
        file_actions = ttk.Frame(self)
        file_actions.grid(row=1, column=2, sticky="ew")
        ttk.Button(file_actions, text="Browse Database File", command=self.browse_database_file).pack(side="left", padx=(0, 6))
        ttk.Button(file_actions, text="Use MainVersion DB", command=self.use_main_version_db).pack(side="left", padx=(0, 6))
        ttk.Button(file_actions, text="Use LocalVersion DB", command=self.use_local_version_db).pack(side="left")

        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Button(actions, text="Create Database", command=self.create_database).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Reset Database", command=self.reset_database).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Check Database", command=self.check_database).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Prepare Database for New Client", command=self.prepare_for_new_client).pack(side="left")

        ttk.Label(self, text="Database status").grid(row=3, column=0, sticky="nw", pady=6)
        status = ttk.Label(self, textvariable=self.status_var, justify="left")
        status.grid(row=3, column=1, columnspan=2, sticky="ew", padx=8, pady=6)

    def _sync_folder(self) -> Path:
        folder = Path(self.folder_var.get()).expanduser()
        path = self.controller.set_database_folder(folder)
        self.database_file_var.set(str(path))
        return path

    def _sync_database_file(self) -> Path:
        value = self.database_file_var.get().strip()
        if value:
            path = self.controller.set_database_file(Path(value).expanduser())
            self.folder_var.set(str(path.parent))
            self.database_file_var.set(str(path))
            return path
        return self._sync_folder()

    def browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if folder:
            self.folder_var.set(folder)
            self._sync_folder()

    def browse_database_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select SQLite Database File",
            initialdir=self.folder_var.get() or ".",
            filetypes=[
                ("SQLite database files", "*.db *.sqlite *.sqlite3"),
                ("DB files", "*.db"),
                ("SQLite files", "*.sqlite *.sqlite3"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.database_file_var.set(selected)
            self._sync_database_file()

    def use_main_version_db(self) -> None:
        path = Path(r"C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db")
        self.database_file_var.set(str(path))
        self._sync_database_file()

    def use_local_version_db(self) -> None:
        path = Path(r"C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db")
        self.database_file_var.set(str(path))
        self._sync_database_file()

    def create_database(self) -> None:
        try:
            path = self._sync_database_file()
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
            path = self._sync_database_file()
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
            self._sync_database_file()
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

    def prepare_for_new_client(self) -> None:
        try:
            path = self._sync_database_file()
            if not path.exists():
                raise FileNotFoundError(f"Database file not found: {path}")
            warning = (
                "This will remove all testing/demo/business transaction data from the selected database.\n\n"
                f"Database:\n{path}\n\n"
                "It will keep company setup, master admin user, roles, permissions, chart of accounts, "
                "numbering, license, and required settings.\n\n"
                "A backup will be created before reset.\n\n"
                "Continue?"
            )
            if not messagebox.askyesno("Prepare Database for New Client", warning):
                self.logger.info("Pre-client reset cancelled.")
                return
            typed = simpledialog.askstring(
                "Confirm Reset",
                "Type RESET to continue:",
                parent=self,
            )
            if typed != "RESET":
                self.logger.info("Pre-client reset confirmation failed or cancelled.")
                messagebox.showinfo("Prepare Database", "Reset cancelled.")
                return
            result = self.controller.prepare_database_for_new_client()
            deleted_total = sum(result["rows_deleted_by_table"].values())
            messagebox.showinfo(
                "Prepare Database Complete",
                "\n".join(
                    [
                        "Database prepared for new client deployment.",
                        f"Backup: {result['backup_path']}",
                        f"Tables cleaned: {len(result['tables_cleaned'])}",
                        f"Rows deleted: {deleted_total}",
                    ]
                ),
            )
            self.check_database()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("Prepare Database", str(exc))
