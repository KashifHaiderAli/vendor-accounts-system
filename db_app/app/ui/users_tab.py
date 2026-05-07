from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.security.password_utils import hash_password
from app.utils.date_utils import now_iso


class UsersTab(ttk.Frame):
    def __init__(self, master, controller, logger) -> None:
        super().__init__(master, padding=8)
        self.controller = controller
        self.logger = logger
        self.selected_user_id: int | None = None
        self.selected_role_id: int | None = None
        self.role_options: dict[str, int] = {}
        self.branch_options: dict[str, int] = {}
        self.branch_vars: dict[int, tk.BooleanVar] = {}
        self.default_branch_var = tk.IntVar(value=0)

        self.user_vars = {
            "username": tk.StringVar(),
            "full_name": tk.StringVar(),
            "email": tk.StringVar(),
            "mobile": tk.StringVar(),
            "role": tk.StringVar(),
            "default_branch": tk.StringVar(),
            "password": tk.StringVar(),
            "confirm_password": tk.StringVar(),
            "is_active": tk.BooleanVar(value=True),
            "must_change_password": tk.BooleanVar(value=False),
        }
        self.role_vars = {
            "role_name": tk.StringVar(),
            "description": tk.StringVar(),
            "is_active": tk.BooleanVar(value=True),
        }
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        self.users_page = ttk.Frame(notebook, padding=8)
        self.roles_page = ttk.Frame(notebook, padding=8)
        self.branch_page = ttk.Frame(notebook, padding=8)
        notebook.add(self.users_page, text="Users")
        notebook.add(self.roles_page, text="Roles & Permissions")
        notebook.add(self.branch_page, text="User Branch Access")

        self._build_users_page()
        self._build_roles_page()
        self._build_branch_page()

    def _build_users_page(self) -> None:
        self.users_page.columnconfigure(0, weight=1)
        self.users_page.rowconfigure(1, weight=1)

        actions = ttk.Frame(self.users_page)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Load Users", command=self.load_users).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="New User", command=self.new_user).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save User", command=self.save_user).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Reset Password", command=self.reset_password).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Activate/Deactivate", command=self.toggle_user_active).pack(side="left")

        columns = ("id", "username", "full_name", "role", "default_branch", "active", "master_user")
        self.users_tree = ttk.Treeview(self.users_page, columns=columns, show="headings", height=9)
        for column, heading, width in [
            ("id", "ID", 55),
            ("username", "Username", 120),
            ("full_name", "Full Name", 180),
            ("role", "Role", 150),
            ("default_branch", "Default Branch", 160),
            ("active", "Active", 80),
            ("master_user", "Master User", 95),
        ]:
            self.users_tree.heading(column, text=heading)
            self.users_tree.column(column, width=width, anchor="w")
        self.users_tree.grid(row=1, column=0, sticky="nsew")
        self.users_tree.bind("<<TreeviewSelect>>", self._on_user_select)

        form = ttk.LabelFrame(self.users_page, text="User Form", padding=8)
        form.grid(row=2, column=0, sticky="ew", pady=8)
        for column in (1, 3):
            form.columnconfigure(column, weight=1)
        fields = [
            ("username", "Username"),
            ("full_name", "Full Name"),
            ("email", "Email"),
            ("mobile", "Mobile"),
            ("role", "Role"),
            ("default_branch", "Default Branch"),
            ("password", "Password"),
            ("confirm_password", "Confirm Password"),
        ]
        for index, (field, label) in enumerate(fields):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", pady=3)
            if field == "role":
                self.role_combo = ttk.Combobox(form, textvariable=self.user_vars[field], state="readonly")
                self.role_combo.grid(row=row, column=col + 1, sticky="ew", padx=8, pady=3)
            elif field == "default_branch":
                self.branch_combo = ttk.Combobox(form, textvariable=self.user_vars[field], state="readonly")
                self.branch_combo.grid(row=row, column=col + 1, sticky="ew", padx=8, pady=3)
            else:
                show = "*" if field in {"password", "confirm_password"} else ""
                ttk.Entry(form, textvariable=self.user_vars[field], show=show).grid(
                    row=row, column=col + 1, sticky="ew", padx=8, pady=3
                )
        ttk.Checkbutton(form, text="Active", variable=self.user_vars["is_active"]).grid(row=4, column=0, sticky="w")
        ttk.Checkbutton(form, text="Must Change Password", variable=self.user_vars["must_change_password"]).grid(
            row=4, column=1, sticky="w"
        )

    def _build_roles_page(self) -> None:
        self.roles_page.columnconfigure(0, weight=1)
        self.roles_page.columnconfigure(1, weight=2)
        self.roles_page.rowconfigure(1, weight=1)

        actions = ttk.Frame(self.roles_page)
        actions.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Load Roles", command=self.load_roles).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Role", command=self.save_role).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Permissions", command=self.save_role_permissions).pack(side="left")

        self.roles_tree = ttk.Treeview(
            self.roles_page,
            columns=("id", "role_name", "description", "active"),
            show="headings",
            height=9,
        )
        for column, heading, width in [
            ("id", "ID", 50),
            ("role_name", "Role Name", 160),
            ("description", "Description", 260),
            ("active", "Active", 70),
        ]:
            self.roles_tree.heading(column, text=heading)
            self.roles_tree.column(column, width=width, anchor="w")
        self.roles_tree.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.roles_tree.bind("<<TreeviewSelect>>", self._on_role_select)

        right = ttk.Frame(self.roles_page)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        form = ttk.LabelFrame(right, text="Role Form", padding=8)
        form.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Role Name").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.role_vars["role_name"]).grid(row=0, column=1, sticky="ew", padx=8, pady=3)
        ttk.Label(form, text="Description").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.role_vars["description"]).grid(row=1, column=1, sticky="ew", padx=8, pady=3)
        ttk.Checkbutton(form, text="Active", variable=self.role_vars["is_active"]).grid(row=2, column=1, sticky="w")

        columns = ("permission_id", "module", "view", "add", "edit", "delete", "print", "export")
        self.permissions_tree = ttk.Treeview(right, columns=columns, show="headings", height=11)
        for column, heading, width in [
            ("permission_id", "ID", 45),
            ("module", "Module", 190),
            ("view", "View", 55),
            ("add", "Add", 55),
            ("edit", "Edit", 55),
            ("delete", "Delete", 60),
            ("print", "Print", 55),
            ("export", "Export", 60),
        ]:
            self.permissions_tree.heading(column, text=heading)
            self.permissions_tree.column(column, width=width, anchor="center" if column != "module" else "w")
        self.permissions_tree.grid(row=1, column=0, sticky="nsew")
        self.permissions_tree.bind("<Double-1>", self._toggle_permission_cell)

    def _build_branch_page(self) -> None:
        self.branch_page.columnconfigure(0, weight=1)
        ttk.Label(self.branch_page, text="Select a user from the Users tab, then load branch access here.").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        actions = ttk.Frame(self.branch_page)
        actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Load Branch Access", command=self.load_user_branch_access).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save Branch Access", command=self.save_user_branch_access).pack(side="left")
        self.branch_access_frame = ttk.LabelFrame(self.branch_page, text="Branches", padding=8)
        self.branch_access_frame.grid(row=2, column=0, sticky="ew")

    def _load_options(self) -> None:
        self.role_options.clear()
        self.branch_options.clear()
        company_id, _ = self.controller.default_company_and_branch()
        with self.controller.connect() as connection:
            roles = connection.execute(
                "SELECT id, role_name FROM user_roles WHERE company_id = ? AND is_active = 1 ORDER BY role_name",
                (company_id,),
            ).fetchall()
            branches = connection.execute(
                "SELECT id, branch_name FROM branches WHERE company_id = ? AND is_active = 1 ORDER BY branch_name",
                (company_id,),
            ).fetchall()
        self.role_options.update({f"{row['id']} - {row['role_name']}": row["id"] for row in roles})
        self.branch_options.update({f"{row['id']} - {row['branch_name']}": row["id"] for row in branches})
        self.role_combo.configure(values=list(self.role_options.keys()))
        self.branch_combo.configure(values=list(self.branch_options.keys()))

    def load_users(self) -> None:
        try:
            self._load_options()
            self.users_tree.delete(*self.users_tree.get_children())
            company_id, _ = self.controller.default_company_and_branch()
            with self.controller.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT u.id, u.username, u.full_name, r.role_name, b.branch_name,
                           u.is_active, u.is_master_user
                    FROM users u
                    JOIN user_roles r ON r.id = u.role_id
                    LEFT JOIN branches b ON b.id = u.default_branch_id
                    WHERE u.company_id = ?
                    ORDER BY u.username
                    """,
                    (company_id,),
                ).fetchall()
            for row in rows:
                self.users_tree.insert(
                    "",
                    "end",
                    values=(
                        row["id"],
                        row["username"],
                        row["full_name"],
                        row["role_name"],
                        row["branch_name"] or "",
                        "Yes" if row["is_active"] else "No",
                        "Yes" if row["is_master_user"] else "No",
                    ),
                )
            self.logger.info("Users loaded.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def new_user(self) -> None:
        self.selected_user_id = None
        for key, variable in self.user_vars.items():
            variable.set(True if key == "is_active" else False if key == "must_change_password" else "")
        self.logger.info("New user form ready.")

    def _on_user_select(self, _event=None) -> None:
        selected = self.users_tree.selection()
        if not selected:
            return
        user_id = int(self.users_tree.item(selected[0], "values")[0])
        try:
            self._load_options()
            with self.controller.connect() as connection:
                row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                role = connection.execute("SELECT role_name FROM user_roles WHERE id = ?", (row["role_id"],)).fetchone()
                branch = (
                    connection.execute("SELECT branch_name FROM branches WHERE id = ?", (row["default_branch_id"],)).fetchone()
                    if row["default_branch_id"]
                    else None
                )
            self.selected_user_id = row["id"]
            self.user_vars["username"].set(row["username"])
            self.user_vars["full_name"].set(row["full_name"])
            self.user_vars["email"].set(row["email"] or "")
            self.user_vars["mobile"].set(row["mobile"] or "")
            self.user_vars["role"].set(f"{row['role_id']} - {role['role_name']}" if role else "")
            self.user_vars["default_branch"].set(
                f"{row['default_branch_id']} - {branch['branch_name']}" if branch else ""
            )
            self.user_vars["password"].set("")
            self.user_vars["confirm_password"].set("")
            self.user_vars["is_active"].set(bool(row["is_active"]))
            self.user_vars["must_change_password"].set(bool(row["must_change_password"]))
            self.load_user_branch_access()
        except Exception as exc:
            self.logger.error(str(exc))

    def save_user(self) -> None:
        try:
            now = now_iso()
            company_id, _ = self.controller.default_company_and_branch()
            username = self.user_vars["username"].get().strip()
            full_name = self.user_vars["full_name"].get().strip()
            role_id = self.role_options.get(self.user_vars["role"].get())
            branch_id = self.branch_options.get(self.user_vars["default_branch"].get())
            password = self.user_vars["password"].get()
            confirm_password = self.user_vars["confirm_password"].get()
            if not username or not full_name or not role_id:
                raise ValueError("Username, full name, and role are required.")
            if password or confirm_password or not self.selected_user_id:
                if password != confirm_password:
                    raise ValueError("Password and confirm password do not match.")
                if not password:
                    raise ValueError("Password is required for a new user.")
                password_hash, password_salt = hash_password(password)
            with self.controller.connect() as connection:
                if not self.user_vars["is_active"].get():
                    self._ensure_not_last_active_master_admin(connection, self.selected_user_id, role_id)
                if self.selected_user_id:
                    if password or confirm_password:
                        connection.execute(
                            """
                            UPDATE users
                            SET username = ?, password_hash = ?, password_salt = ?, full_name = ?,
                                email = ?, mobile = ?, role_id = ?, default_branch_id = ?,
                                is_active = ?, must_change_password = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                username,
                                password_hash,
                                password_salt,
                                full_name,
                                self.user_vars["email"].get().strip(),
                                self.user_vars["mobile"].get().strip(),
                                role_id,
                                branch_id,
                                int(self.user_vars["is_active"].get()),
                                int(self.user_vars["must_change_password"].get()),
                                now,
                                self.selected_user_id,
                            ),
                        )
                    else:
                        connection.execute(
                            """
                            UPDATE users
                            SET username = ?, full_name = ?, email = ?, mobile = ?, role_id = ?,
                                default_branch_id = ?, is_active = ?, must_change_password = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                username,
                                full_name,
                                self.user_vars["email"].get().strip(),
                                self.user_vars["mobile"].get().strip(),
                                role_id,
                                branch_id,
                                int(self.user_vars["is_active"].get()),
                                int(self.user_vars["must_change_password"].get()),
                                now,
                                self.selected_user_id,
                            ),
                        )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO users (
                            company_id, username, password_hash, password_salt, full_name, email,
                            mobile, role_id, default_branch_id, is_master_user, is_active,
                            must_change_password, created_at, updated_at, last_login
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, NULL)
                        """,
                        (
                            company_id,
                            username,
                            password_hash,
                            password_salt,
                            full_name,
                            self.user_vars["email"].get().strip(),
                            self.user_vars["mobile"].get().strip(),
                            role_id,
                            branch_id,
                            int(self.user_vars["is_active"].get()),
                            int(self.user_vars["must_change_password"].get()),
                            now,
                            now,
                        ),
                    )
                    self.selected_user_id = int(cursor.lastrowid)
                if branch_id:
                    self._upsert_user_default_branch(connection, self.selected_user_id, branch_id, now)
                connection.commit()
            self.logger.info("User saved.")
            self.load_users()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def reset_password(self) -> None:
        if not self.selected_user_id:
            messagebox.showwarning("User Management", "Select a user first.")
            return
        password = self.user_vars["password"].get()
        confirm_password = self.user_vars["confirm_password"].get()
        try:
            if not password or password != confirm_password:
                raise ValueError("Enter matching password and confirm password values.")
            password_hash, password_salt = hash_password(password)
            with self.controller.connect() as connection:
                connection.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, password_salt = ?, must_change_password = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        password_hash,
                        password_salt,
                        int(self.user_vars["must_change_password"].get()),
                        now_iso(),
                        self.selected_user_id,
                    ),
                )
                connection.commit()
            self.logger.info("User password reset.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def toggle_user_active(self) -> None:
        if not self.selected_user_id:
            messagebox.showwarning("User Management", "Select a user first.")
            return
        try:
            with self.controller.connect() as connection:
                row = connection.execute("SELECT role_id, is_active FROM users WHERE id = ?", (self.selected_user_id,)).fetchone()
                new_active = 0 if row["is_active"] else 1
                if new_active == 0:
                    self._ensure_not_last_active_master_admin(connection, self.selected_user_id, row["role_id"])
                connection.execute(
                    "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                    (new_active, now_iso(), self.selected_user_id),
                )
                connection.commit()
            self.logger.info("User active status updated.")
            self.load_users()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def _ensure_not_last_active_master_admin(self, connection, user_id: int | None, role_id: int) -> None:
        role = connection.execute("SELECT role_name FROM user_roles WHERE id = ?", (role_id,)).fetchone()
        if not role or role["role_name"] != "Master Admin":
            return
        active_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM users u
            JOIN user_roles r ON r.id = u.role_id
            WHERE r.role_name = 'Master Admin' AND u.is_active = 1 AND u.id <> ?
            """,
            (user_id or 0,),
        ).fetchone()[0]
        if active_count < 1:
            raise ValueError("Cannot deactivate the last active Master Admin.")

    def _upsert_user_default_branch(self, connection, user_id: int, branch_id: int, now: str) -> None:
        connection.execute("UPDATE user_branches SET is_default = 0, updated_at = ? WHERE user_id = ?", (now, user_id))
        row = connection.execute(
            "SELECT id FROM user_branches WHERE user_id = ? AND branch_id = ?",
            (user_id, branch_id),
        ).fetchone()
        if row:
            connection.execute(
                "UPDATE user_branches SET is_default = 1, updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (user_id, branch_id, now, now),
            )

    def load_roles(self) -> None:
        try:
            self.roles_tree.delete(*self.roles_tree.get_children())
            company_id, _ = self.controller.default_company_and_branch()
            with self.controller.connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM user_roles WHERE company_id = ? ORDER BY role_name",
                    (company_id,),
                ).fetchall()
            for row in rows:
                self.roles_tree.insert(
                    "",
                    "end",
                    values=(row["id"], row["role_name"], row["description"] or "", "Yes" if row["is_active"] else "No"),
                )
            self.logger.info("Roles loaded.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def _on_role_select(self, _event=None) -> None:
        selected = self.roles_tree.selection()
        if not selected:
            return
        role_id = int(self.roles_tree.item(selected[0], "values")[0])
        try:
            with self.controller.connect() as connection:
                row = connection.execute("SELECT * FROM user_roles WHERE id = ?", (role_id,)).fetchone()
            self.selected_role_id = row["id"]
            self.role_vars["role_name"].set(row["role_name"])
            self.role_vars["description"].set(row["description"] or "")
            self.role_vars["is_active"].set(bool(row["is_active"]))
            self.load_role_permissions()
        except Exception as exc:
            self.logger.error(str(exc))

    def save_role(self) -> None:
        try:
            now = now_iso()
            company_id, _ = self.controller.default_company_and_branch()
            role_name = self.role_vars["role_name"].get().strip()
            if not role_name:
                raise ValueError("Role name is required.")
            with self.controller.connect() as connection:
                if self.selected_role_id:
                    connection.execute(
                        """
                        UPDATE user_roles
                        SET role_name = ?, description = ?, is_active = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            role_name,
                            self.role_vars["description"].get().strip(),
                            int(self.role_vars["is_active"].get()),
                            now,
                            self.selected_role_id,
                        ),
                    )
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO user_roles (
                            company_id, role_name, description, is_system_role, is_active, created_at, updated_at
                        ) VALUES (?, ?, ?, 0, ?, ?, ?)
                        """,
                        (
                            company_id,
                            role_name,
                            self.role_vars["description"].get().strip(),
                            int(self.role_vars["is_active"].get()),
                            now,
                            now,
                        ),
                    )
                    self.selected_role_id = int(cursor.lastrowid)
                connection.commit()
            self.logger.info("Role saved.")
            self.load_roles()
            self.load_role_permissions()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def load_role_permissions(self) -> None:
        self.permissions_tree.delete(*self.permissions_tree.get_children())
        if not self.selected_role_id:
            return
        with self.controller.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.id AS permission_id, p.module_name,
                       COALESCE(rp.can_view, 0) AS can_view,
                       COALESCE(rp.can_add, 0) AS can_add,
                       COALESCE(rp.can_edit, 0) AS can_edit,
                       COALESCE(rp.can_delete, 0) AS can_delete,
                       COALESCE(rp.can_print, 0) AS can_print,
                       COALESCE(rp.can_export, 0) AS can_export
                FROM permissions p
                LEFT JOIN role_permissions rp ON rp.permission_id = p.id AND rp.role_id = ?
                ORDER BY p.module_name
                """,
                (self.selected_role_id,),
            ).fetchall()
        for row in rows:
            self.permissions_tree.insert(
                "",
                "end",
                values=(
                    row["permission_id"],
                    row["module_name"],
                    row["can_view"],
                    row["can_add"],
                    row["can_edit"],
                    row["can_delete"],
                    row["can_print"],
                    row["can_export"],
                ),
            )
        self.logger.info("Role permissions loaded.")

    def _toggle_permission_cell(self, event) -> None:
        item = self.permissions_tree.identify_row(event.y)
        column = self.permissions_tree.identify_column(event.x)
        if not item:
            return
        column_index = int(column.replace("#", "")) - 1
        if column_index < 2:
            return
        values = list(self.permissions_tree.item(item, "values"))
        values[column_index] = 0 if int(values[column_index]) else 1
        self.permissions_tree.item(item, values=values)

    def save_role_permissions(self) -> None:
        if not self.selected_role_id:
            messagebox.showwarning("User Management", "Select or save a role first.")
            return
        try:
            now = now_iso()
            with self.controller.connect() as connection:
                for item in self.permissions_tree.get_children():
                    values = self.permissions_tree.item(item, "values")
                    permission_id = int(values[0])
                    flags = [int(values[index]) for index in range(2, 8)]
                    row = connection.execute(
                        "SELECT id FROM role_permissions WHERE role_id = ? AND permission_id = ?",
                        (self.selected_role_id, permission_id),
                    ).fetchone()
                    if row:
                        connection.execute(
                            """
                            UPDATE role_permissions
                            SET can_view = ?, can_add = ?, can_edit = ?, can_delete = ?,
                                can_print = ?, can_export = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (*flags, now, row["id"]),
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO role_permissions (
                                role_id, permission_id, can_view, can_add, can_edit, can_delete,
                                can_print, can_export, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (self.selected_role_id, permission_id, *flags, now, now),
                        )
                connection.commit()
            self.logger.info("Role permissions saved.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def load_user_branch_access(self) -> None:
        for child in self.branch_access_frame.winfo_children():
            child.destroy()
        self.branch_vars.clear()
        if not self.selected_user_id:
            ttk.Label(self.branch_access_frame, text="No user selected.").grid(row=0, column=0, sticky="w")
            return
        try:
            with self.controller.connect() as connection:
                branches = connection.execute("SELECT * FROM branches ORDER BY branch_name").fetchall()
                access_rows = connection.execute(
                    "SELECT branch_id, is_default FROM user_branches WHERE user_id = ?",
                    (self.selected_user_id,),
                ).fetchall()
            selected_ids = {row["branch_id"] for row in access_rows}
            default_id = next((row["branch_id"] for row in access_rows if row["is_default"]), 0)
            self.default_branch_var.set(default_id)
            for index, branch in enumerate(branches):
                branch_id = branch["id"]
                var = tk.BooleanVar(value=branch_id in selected_ids)
                self.branch_vars[branch_id] = var
                ttk.Checkbutton(
                    self.branch_access_frame,
                    text=f"{branch['branch_code']} - {branch['branch_name']}",
                    variable=var,
                ).grid(row=index, column=0, sticky="w", pady=2)
                ttk.Radiobutton(
                    self.branch_access_frame,
                    text="Default",
                    variable=self.default_branch_var,
                    value=branch_id,
                ).grid(row=index, column=1, sticky="w", padx=12, pady=2)
            self.logger.info("User branch access loaded.")
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

    def save_user_branch_access(self) -> None:
        if not self.selected_user_id:
            messagebox.showwarning("User Management", "Select a user first.")
            return
        try:
            selected_branch_ids = [branch_id for branch_id, var in self.branch_vars.items() if var.get()]
            default_branch_id = self.default_branch_var.get()
            if default_branch_id and default_branch_id not in selected_branch_ids:
                raise ValueError("Default branch must also be selected for access.")
            now = now_iso()
            with self.controller.connect() as connection:
                connection.execute("DELETE FROM user_branches WHERE user_id = ?", (self.selected_user_id,))
                for branch_id in selected_branch_ids:
                    connection.execute(
                        """
                        INSERT INTO user_branches (user_id, branch_id, is_default, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (self.selected_user_id, branch_id, int(branch_id == default_branch_id), now, now),
                    )
                connection.execute(
                    "UPDATE users SET default_branch_id = ?, updated_at = ? WHERE id = ?",
                    (default_branch_id or None, now, self.selected_user_id),
                )
                connection.commit()
            self.logger.info("User branch access saved.")
            self.load_users()
        except Exception as exc:
            self.logger.error(str(exc))
            messagebox.showerror("User Management", str(exc))

