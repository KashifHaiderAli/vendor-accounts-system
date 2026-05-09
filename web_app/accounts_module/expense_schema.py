EXPENSE_VOUCHER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expense_vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    branch_id INTEGER,
    voucher_no TEXT NOT NULL,
    voucher_date TEXT NOT NULL,
    expense_head_id INTEGER NOT NULL,
    cash_bank_account_id INTEGER NOT NULL,
    payment_mode TEXT,
    cheque_reference_no TEXT,
    amount NUMERIC NOT NULL DEFAULT 0,
    tax_percent NUMERIC NOT NULL DEFAULT 0,
    tax_amount NUMERIC NOT NULL DEFAULT 0,
    total_amount NUMERIC NOT NULL DEFAULT 0,
    status TEXT,
    journal_entry_id INTEGER,
    remarks TEXT,
    created_by_id INTEGER,
    updated_by_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies(id),
    FOREIGN KEY (branch_id) REFERENCES branches(id),
    FOREIGN KEY (expense_head_id) REFERENCES expense_heads(id),
    FOREIGN KEY (cash_bank_account_id) REFERENCES cash_bank_accounts(id),
    FOREIGN KEY (journal_entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY (created_by_id) REFERENCES users(id),
    FOREIGN KEY (updated_by_id) REFERENCES users(id),
    UNIQUE (company_id, branch_id, voucher_no)
)
"""

EXPENSE_VOUCHER_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_company_branch ON expense_vouchers(company_id, branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_no ON expense_vouchers(voucher_no)",
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_date ON expense_vouchers(voucher_date)",
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_expense_head ON expense_vouchers(expense_head_id)",
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_cash_bank ON expense_vouchers(cash_bank_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_expense_vouchers_status ON expense_vouchers(status)",
]


def expense_voucher_schema_sql():
    return [EXPENSE_VOUCHER_TABLE_SQL] + EXPENSE_VOUCHER_INDEX_SQL
