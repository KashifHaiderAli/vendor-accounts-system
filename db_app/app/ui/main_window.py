from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import WINDOW_SIZE, WINDOW_TITLE
from app.db_app import VendorAccountsDBAppController
from app.logger import AppLogger
from app.ui.branches_tab import BranchesTab
from app.ui.company_tab import CompanyTab
from app.ui.database_tab import DatabaseTab
from app.ui.licensing_tab import LicensingTab
from app.ui.log_panel import LogPanel
from app.ui.users_tab import UsersTab


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(1050, 650)

        self.logger = AppLogger()
        self.controller = VendorAccountsDBAppController(self.logger)

        self._build()
        self.logger.info(f"Default database path: {self.controller.database_path}")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        notebook.add(DatabaseTab(notebook, self.controller, self.logger), text="Database")
        notebook.add(CompanyTab(notebook, self.controller, self.logger), text="Company Setup")
        notebook.add(BranchesTab(notebook, self.controller, self.logger), text="Branches")
        notebook.add(UsersTab(notebook, self.controller, self.logger), text="User Management")
        notebook.add(LicensingTab(notebook, self.controller, self.logger), text="Licensing")

        LogPanel(self, self.logger).grid(row=1, column=0, sticky="ew")

