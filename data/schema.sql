CREATE TABLE companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        legal_name TEXT,
        address TEXT,
        phone TEXT,
        mobile TEXT,
        email TEXT,
        website TEXT,
        ntn TEXT,
        strn TEXT,
        logo_path TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_code TEXT NOT NULL,
        branch_name TEXT NOT NULL,
        address TEXT,
        phone TEXT,
        mobile TEXT,
        email TEXT,
        is_head_office INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        UNIQUE (company_id, branch_code)
    );
CREATE TABLE company_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        quotation_footer TEXT,
        invoice_footer TEXT,
        bank_details TEXT,
        authorized_person_name TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id)
    );
CREATE TABLE numbering_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        customer_prefix TEXT,
        supplier_prefix TEXT,
        item_prefix TEXT,
        quotation_prefix TEXT,
        confirmation_prefix TEXT,
        delivery_challan_prefix TEXT,
        invoice_prefix TEXT,
        sales_return_prefix TEXT,
        cash_memo_prefix TEXT,
        receipt_prefix TEXT,
        purchase_prefix TEXT,
        purchase_return_prefix TEXT,
        supplier_payment_prefix TEXT,
        service_contract_prefix TEXT,
        expense_voucher_prefix TEXT,
        use_year_in_number INTEGER NOT NULL DEFAULT 1,
        number_padding INTEGER NOT NULL DEFAULT 4,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id)
    );
CREATE TABLE tax_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        default_sales_tax_percent NUMERIC NOT NULL DEFAULT 0,
        default_input_tax_percent NUMERIC NOT NULL DEFAULT 0,
        default_tax_applicable INTEGER NOT NULL DEFAULT 0,
        tax_invoice_label TEXT,
        show_ntn_on_invoice INTEGER NOT NULL DEFAULT 1,
        show_strn_on_invoice INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id)
    );
CREATE TABLE app_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        database_path TEXT,
        database_password_hint TEXT,
        backup_folder_path TEXT,
        auto_backup_on_close INTEGER NOT NULL DEFAULT 0,
        auto_backup_daily INTEGER NOT NULL DEFAULT 0,
        keep_last_backups INTEGER NOT NULL DEFAULT 30,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id)
    );
CREATE TABLE user_roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        role_name TEXT NOT NULL,
        description TEXT,
        is_system_role INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        UNIQUE (company_id, role_name)
    );
CREATE TABLE permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        permission_code TEXT NOT NULL UNIQUE,
        permission_name TEXT NOT NULL,
        module_name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
CREATE TABLE role_permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        can_view INTEGER NOT NULL DEFAULT 0,
        can_add INTEGER NOT NULL DEFAULT 0,
        can_edit INTEGER NOT NULL DEFAULT 0,
        can_delete INTEGER NOT NULL DEFAULT 0,
        can_print INTEGER NOT NULL DEFAULT 0,
        can_export INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (role_id) REFERENCES user_roles(id),
        FOREIGN KEY (permission_id) REFERENCES permissions(id),
        UNIQUE (role_id, permission_id)
    );
CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        password_salt TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT,
        mobile TEXT,
        role_id INTEGER NOT NULL,
        default_branch_id INTEGER,
        is_master_user INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_login TEXT,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (role_id) REFERENCES user_roles(id),
        FOREIGN KEY (default_branch_id) REFERENCES branches(id),
        UNIQUE (company_id, username)
    );
CREATE TABLE user_branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        branch_id INTEGER NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        UNIQUE (user_id, branch_id)
    );
CREATE TABLE user_activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        branch_id INTEGER,
        user_id INTEGER,
        action_type TEXT NOT NULL,
        module_name TEXT,
        table_name TEXT,
        record_id INTEGER,
        description TEXT,
        activity_datetime TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
CREATE TABLE license_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        license_type TEXT NOT NULL,
        hardware_fingerprint TEXT NOT NULL,
        license_key TEXT NOT NULL,
        issue_date TEXT NOT NULL,
        start_date TEXT NOT NULL,
        expiry_date TEXT,
        is_lifetime INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id)
    );
CREATE TABLE backup_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        branch_id INTEGER,
        backup_file_path TEXT NOT NULL,
        backup_type TEXT,
        backup_date TEXT NOT NULL,
        status TEXT,
        remarks TEXT,
        created_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id)
    );
CREATE TABLE accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        account_code TEXT NOT NULL,
        account_name TEXT NOT NULL,
        account_type TEXT NOT NULL,
        parent_id INTEGER,
        is_control_account INTEGER NOT NULL DEFAULT 0,
        is_system_account INTEGER NOT NULL DEFAULT 1,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (parent_id) REFERENCES accounts(id),
        UNIQUE (company_id, branch_id, account_code)
    );
CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        entry_no TEXT NOT NULL,
        entry_date TEXT NOT NULL,
        reference_type TEXT,
        reference_id INTEGER,
        description TEXT,
        created_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, entry_no)
    );
CREATE TABLE journal_entry_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_entry_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        debit NUMERIC NOT NULL DEFAULT 0,
        credit NUMERIC NOT NULL DEFAULT 0,
        description TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id)
    );
CREATE TABLE payment_terms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        name TEXT NOT NULL,
        days INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id)
    );
CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        customer_code TEXT NOT NULL,
        company_name TEXT NOT NULL,
        contact_person TEXT,
        phone TEXT,
        mobile TEXT,
        email TEXT,
        address TEXT,
        ntn TEXT,
        strn TEXT,
        payment_terms_id INTEGER,
        credit_limit NUMERIC NOT NULL DEFAULT 0,
        opening_balance NUMERIC NOT NULL DEFAULT 0,
        opening_balance_type TEXT,
        account_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (payment_terms_id) REFERENCES payment_terms(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, customer_code)
    );
CREATE TABLE suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        supplier_code TEXT NOT NULL,
        supplier_name TEXT NOT NULL,
        contact_person TEXT,
        phone TEXT,
        mobile TEXT,
        email TEXT,
        address TEXT,
        ntn TEXT,
        strn TEXT,
        opening_balance NUMERIC NOT NULL DEFAULT 0,
        opening_balance_type TEXT,
        account_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, supplier_code)
    );
CREATE TABLE item_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        item_code TEXT NOT NULL,
        item_name TEXT NOT NULL,
        item_type TEXT,
        category TEXT,
        default_purchase_rate NUMERIC NOT NULL DEFAULT 0,
        default_sale_rate NUMERIC NOT NULL DEFAULT 0,
        default_tax_rate NUMERIC NOT NULL DEFAULT 0,
        warranty_or_service_description TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, item_code)
    );
CREATE TABLE cash_bank_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        account_name TEXT NOT NULL,
        account_type TEXT,
        bank_name TEXT,
        account_number TEXT,
        branch TEXT,
        iban TEXT,
        opening_balance NUMERIC NOT NULL DEFAULT 0,
        account_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id)
    );
CREATE TABLE expense_heads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        expense_code TEXT NOT NULL,
        expense_name TEXT NOT NULL,
        category TEXT,
        account_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, expense_code)
    );
CREATE TABLE quotations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        quotation_no TEXT NOT NULL,
        quotation_date TEXT NOT NULL,
        customer_id INTEGER,
        contact_person TEXT,
        subject TEXT,
        validity_days INTEGER,
        valid_till TEXT,
        payment_terms_id INTEGER,
        tax_option TEXT,
        subtotal NUMERIC NOT NULL DEFAULT 0,
        discount_total NUMERIC NOT NULL DEFAULT 0,
        tax_total NUMERIC NOT NULL DEFAULT 0,
        grand_total NUMERIC NOT NULL DEFAULT 0,
        terms_conditions TEXT,
        remarks TEXT,
        status TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (payment_terms_id) REFERENCES payment_terms(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, quotation_no)
    );
CREATE TABLE quotation_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quotation_id INTEGER NOT NULL,
        item_service_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        rate NUMERIC NOT NULL DEFAULT 0,
        discount_percent NUMERIC NOT NULL DEFAULT 0,
        discount_amount NUMERIC NOT NULL DEFAULT 0,
        tax_percent NUMERIC NOT NULL DEFAULT 0,
        tax_amount NUMERIC NOT NULL DEFAULT 0,
        line_total NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (quotation_id) REFERENCES quotations(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id)
    );
CREATE TABLE customer_confirmations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        confirmation_no TEXT NOT NULL,
        confirmation_date TEXT NOT NULL,
        customer_id INTEGER,
        quotation_id INTEGER,
        confirmation_type TEXT,
        po_number TEXT,
        po_date TEXT,
        po_amount NUMERIC NOT NULL DEFAULT 0,
        contact_person TEXT,
        confirmation_note TEXT,
        attachment_path TEXT,
        total_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (quotation_id) REFERENCES quotations(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, confirmation_no)
    );
CREATE TABLE delivery_challans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        dc_no TEXT NOT NULL,
        dc_date TEXT NOT NULL,
        customer_id INTEGER,
        confirmation_id INTEGER,
        quotation_id INTEGER,
        po_number TEXT,
        delivered_by TEXT,
        received_by TEXT,
        signed_copy_path TEXT,
        status TEXT,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (confirmation_id) REFERENCES customer_confirmations(id),
        FOREIGN KEY (quotation_id) REFERENCES quotations(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, dc_no)
    );
CREATE TABLE delivery_challan_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        delivery_challan_id INTEGER NOT NULL,
        item_service_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (delivery_challan_id) REFERENCES delivery_challans(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id)
    );
CREATE TABLE sales_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        invoice_no TEXT NOT NULL,
        invoice_date TEXT NOT NULL,
        invoice_type TEXT,
        customer_id INTEGER,
        delivery_challan_id INTEGER,
        confirmation_id INTEGER,
        po_number TEXT,
        payment_terms_id INTEGER,
        due_date TEXT,
        subtotal NUMERIC NOT NULL DEFAULT 0,
        discount_total NUMERIC NOT NULL DEFAULT 0,
        tax_total NUMERIC NOT NULL DEFAULT 0,
        grand_total NUMERIC NOT NULL DEFAULT 0,
        received_amount NUMERIC NOT NULL DEFAULT 0,
        balance_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (delivery_challan_id) REFERENCES delivery_challans(id),
        FOREIGN KEY (confirmation_id) REFERENCES customer_confirmations(id),
        FOREIGN KEY (payment_terms_id) REFERENCES payment_terms(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, invoice_no)
    );
CREATE TABLE sales_invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sales_invoice_id INTEGER NOT NULL,
        item_service_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        rate NUMERIC NOT NULL DEFAULT 0,
        discount_percent NUMERIC NOT NULL DEFAULT 0,
        discount_amount NUMERIC NOT NULL DEFAULT 0,
        tax_percent NUMERIC NOT NULL DEFAULT 0,
        tax_amount NUMERIC NOT NULL DEFAULT 0,
        line_total NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (sales_invoice_id) REFERENCES sales_invoices(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id)
    );
CREATE TABLE sales_returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        sales_return_no TEXT NOT NULL,
        return_date TEXT NOT NULL,
        customer_id INTEGER,
        sales_invoice_id INTEGER,
        return_reason TEXT,
        subtotal NUMERIC NOT NULL DEFAULT 0,
        discount_total NUMERIC NOT NULL DEFAULT 0,
        tax_total NUMERIC NOT NULL DEFAULT 0,
        grand_total NUMERIC NOT NULL DEFAULT 0,
        refund_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (sales_invoice_id) REFERENCES sales_invoices(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, sales_return_no)
    );
CREATE TABLE sales_return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sales_return_id INTEGER NOT NULL,
        item_service_id INTEGER,
        sales_invoice_item_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        rate NUMERIC NOT NULL DEFAULT 0,
        discount_percent NUMERIC NOT NULL DEFAULT 0,
        discount_amount NUMERIC NOT NULL DEFAULT 0,
        tax_percent NUMERIC NOT NULL DEFAULT 0,
        tax_amount NUMERIC NOT NULL DEFAULT 0,
        line_total NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (sales_return_id) REFERENCES sales_returns(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id),
        FOREIGN KEY (sales_invoice_item_id) REFERENCES sales_invoice_items(id)
    );
CREATE TABLE customer_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        receipt_no TEXT NOT NULL,
        receipt_date TEXT NOT NULL,
        customer_id INTEGER,
        payment_mode TEXT,
        cash_bank_account_id INTEGER,
        cheque_reference_no TEXT,
        amount NUMERIC NOT NULL DEFAULT 0,
        adjusted_invoice_id INTEGER,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (cash_bank_account_id) REFERENCES cash_bank_accounts(id),
        FOREIGN KEY (adjusted_invoice_id) REFERENCES sales_invoices(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, receipt_no)
    );
CREATE TABLE supplier_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        purchase_no TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        supplier_id INTEGER,
        supplier_bill_no TEXT,
        supplier_bill_date TEXT,
        confirmation_id INTEGER,
        subtotal NUMERIC NOT NULL DEFAULT 0,
        tax_total NUMERIC NOT NULL DEFAULT 0,
        grand_total NUMERIC NOT NULL DEFAULT 0,
        paid_amount NUMERIC NOT NULL DEFAULT 0,
        balance_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (confirmation_id) REFERENCES customer_confirmations(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, purchase_no)
    );
CREATE TABLE supplier_purchase_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_purchase_id INTEGER NOT NULL,
        item_service_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        purchase_rate NUMERIC NOT NULL DEFAULT 0,
        tax_percent NUMERIC NOT NULL DEFAULT 0,
        tax_amount NUMERIC NOT NULL DEFAULT 0,
        line_total NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (supplier_purchase_id) REFERENCES supplier_purchases(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id)
    );
CREATE TABLE purchase_returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        purchase_return_no TEXT NOT NULL,
        return_date TEXT NOT NULL,
        supplier_id INTEGER,
        supplier_purchase_id INTEGER,
        supplier_bill_no TEXT,
        return_reason TEXT,
        subtotal NUMERIC NOT NULL DEFAULT 0,
        tax_total NUMERIC NOT NULL DEFAULT 0,
        grand_total NUMERIC NOT NULL DEFAULT 0,
        refund_amount NUMERIC NOT NULL DEFAULT 0,
        status TEXT,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (supplier_purchase_id) REFERENCES supplier_purchases(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, purchase_return_no)
    );
CREATE TABLE purchase_return_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        purchase_return_id INTEGER NOT NULL,
        item_service_id INTEGER,
        supplier_purchase_item_id INTEGER,
        description TEXT,
        quantity NUMERIC NOT NULL DEFAULT 0,
        purchase_rate NUMERIC NOT NULL DEFAULT 0,
        tax_percent NUMERIC NOT NULL DEFAULT 0,
        tax_amount NUMERIC NOT NULL DEFAULT 0,
        line_total NUMERIC NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (purchase_return_id) REFERENCES purchase_returns(id),
        FOREIGN KEY (item_service_id) REFERENCES item_services(id),
        FOREIGN KEY (supplier_purchase_item_id) REFERENCES supplier_purchase_items(id)
    );
CREATE TABLE supplier_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        payment_no TEXT NOT NULL,
        payment_date TEXT NOT NULL,
        supplier_id INTEGER,
        payment_mode TEXT,
        cash_bank_account_id INTEGER,
        cheque_reference_no TEXT,
        amount NUMERIC NOT NULL DEFAULT 0,
        adjusted_purchase_id INTEGER,
        journal_entry_id INTEGER,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (cash_bank_account_id) REFERENCES cash_bank_accounts(id),
        FOREIGN KEY (adjusted_purchase_id) REFERENCES supplier_purchases(id),
        FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, payment_no)
    );
CREATE TABLE service_contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        contract_no TEXT NOT NULL,
        customer_id INTEGER,
        service_type TEXT,
        start_date TEXT,
        end_date TEXT,
        billing_cycle TEXT,
        contract_amount NUMERIC NOT NULL DEFAULT 0,
        tax_applicable INTEGER NOT NULL DEFAULT 0,
        next_billing_date TEXT,
        renewal_reminder_date TEXT,
        contract_details TEXT,
        status TEXT,
        remarks TEXT,
        created_by_id INTEGER,
        updated_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id),
        FOREIGN KEY (updated_by_id) REFERENCES users(id),
        UNIQUE (company_id, branch_id, contract_no)
    );
CREATE TABLE attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER NOT NULL,
        branch_id INTEGER,
        related_table TEXT NOT NULL,
        related_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT,
        description TEXT,
        created_by_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies(id),
        FOREIGN KEY (branch_id) REFERENCES branches(id),
        FOREIGN KEY (created_by_id) REFERENCES users(id)
    );
CREATE INDEX idx_branches_company_id ON branches(company_id);
CREATE INDEX idx_users_company_id ON users(company_id);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role_id ON users(role_id);
CREATE INDEX idx_role_permissions_role_id ON role_permissions(role_id);
CREATE INDEX idx_accounts_company_branch ON accounts(company_id, branch_id);
CREATE INDEX idx_accounts_account_code ON accounts(account_code);
CREATE INDEX idx_journal_entries_date ON journal_entries(entry_date);
CREATE INDEX idx_journal_entries_entry_no ON journal_entries(entry_no);
CREATE INDEX idx_customers_company_branch ON customers(company_id, branch_id);
CREATE INDEX idx_customers_code ON customers(customer_code);
CREATE INDEX idx_suppliers_company_branch ON suppliers(company_id, branch_id);
CREATE INDEX idx_suppliers_code ON suppliers(supplier_code);
CREATE INDEX idx_item_services_company_branch ON item_services(company_id, branch_id);
CREATE INDEX idx_cash_bank_accounts_account_id ON cash_bank_accounts(account_id);
CREATE INDEX idx_expense_heads_account_id ON expense_heads(account_id);
CREATE INDEX idx_quotations_company_branch ON quotations(company_id, branch_id);
CREATE INDEX idx_quotations_date ON quotations(quotation_date);
CREATE INDEX idx_quotations_no ON quotations(quotation_no);
CREATE INDEX idx_quotations_customer_id ON quotations(customer_id);
CREATE INDEX idx_quotations_status ON quotations(status);
CREATE INDEX idx_confirmations_date ON customer_confirmations(confirmation_date);
CREATE INDEX idx_confirmations_no ON customer_confirmations(confirmation_no);
CREATE INDEX idx_confirmations_customer_id ON customer_confirmations(customer_id);
CREATE INDEX idx_confirmations_status ON customer_confirmations(status);
CREATE INDEX idx_delivery_challans_date ON delivery_challans(dc_date);
CREATE INDEX idx_delivery_challans_no ON delivery_challans(dc_no);
CREATE INDEX idx_delivery_challans_customer_id ON delivery_challans(customer_id);
CREATE INDEX idx_delivery_challans_status ON delivery_challans(status);
CREATE INDEX idx_sales_invoices_date ON sales_invoices(invoice_date);
CREATE INDEX idx_sales_invoices_no ON sales_invoices(invoice_no);
CREATE INDEX idx_sales_invoices_customer_id ON sales_invoices(customer_id);
CREATE INDEX idx_sales_invoices_status ON sales_invoices(status);
CREATE INDEX idx_sales_returns_company_branch ON sales_returns(company_id, branch_id);
CREATE INDEX idx_sales_returns_date ON sales_returns(return_date);
CREATE INDEX idx_sales_returns_no ON sales_returns(sales_return_no);
CREATE INDEX idx_sales_returns_customer_id ON sales_returns(customer_id);
CREATE INDEX idx_sales_returns_invoice_id ON sales_returns(sales_invoice_id);
CREATE INDEX idx_sales_returns_status ON sales_returns(status);
CREATE INDEX idx_customer_receipts_date ON customer_receipts(receipt_date);
CREATE INDEX idx_customer_receipts_customer_id ON customer_receipts(customer_id);
CREATE INDEX idx_supplier_purchases_date ON supplier_purchases(purchase_date);
CREATE INDEX idx_supplier_purchases_no ON supplier_purchases(purchase_no);
CREATE INDEX idx_supplier_purchases_supplier_id ON supplier_purchases(supplier_id);
CREATE INDEX idx_supplier_purchases_status ON supplier_purchases(status);
CREATE INDEX idx_purchase_returns_company_branch ON purchase_returns(company_id, branch_id);
CREATE INDEX idx_purchase_returns_date ON purchase_returns(return_date);
CREATE INDEX idx_purchase_returns_no ON purchase_returns(purchase_return_no);
CREATE INDEX idx_purchase_returns_supplier_id ON purchase_returns(supplier_id);
CREATE INDEX idx_purchase_returns_purchase_id ON purchase_returns(supplier_purchase_id);
CREATE INDEX idx_purchase_returns_status ON purchase_returns(status);
CREATE INDEX idx_supplier_payments_date ON supplier_payments(payment_date);
CREATE INDEX idx_supplier_payments_supplier_id ON supplier_payments(supplier_id);
CREATE INDEX idx_service_contracts_customer_id ON service_contracts(customer_id);
CREATE INDEX idx_service_contracts_status ON service_contracts(status);
CREATE INDEX idx_license_records_company_branch ON license_records(company_id, branch_id);
CREATE INDEX idx_user_activity_datetime ON user_activity_log(activity_datetime);
