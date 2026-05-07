DB_APP_USERNAME = "admin"
DB_APP_PASSWORD = "infoline"

ROLE_MASTER_ADMIN = "Master Admin"
ROLE_ACCOUNTANT = "Accountant"
ROLE_ASSISTANT_ACCOUNTANT = "Assistant Accountant"
ROLE_VIEWER = "Viewer"

DEFAULT_ROLES = [
    (
        ROLE_MASTER_ADMIN,
        "Full access, including database actions, settings, users, roles, licensing, and reset database.",
        1,
    ),
    (
        ROLE_ACCOUNTANT,
        "Full accounting and business access, without database reset or licensing generation.",
        1,
    ),
    (
        ROLE_ASSISTANT_ACCOUNTANT,
        "Routine transaction access without sensitive settings, deletion, users, or licensing.",
        1,
    ),
    (ROLE_VIEWER, "Read-only access to records and reports.", 1),
]

PERMISSION_MODULES = [
    "dashboard",
    "company_settings",
    "branches",
    "numbering_settings",
    "tax_settings",
    "backup_restore",
    "user_management",
    "role_management",
    "licensing",
    "customers",
    "suppliers",
    "item_services",
    "cash_bank_accounts",
    "expense_heads",
    "payment_terms",
    "quotations",
    "customer_confirmations",
    "delivery_challans",
    "sales_invoices",
    "sales_returns",
    "customer_receipts",
    "supplier_purchases",
    "purchase_returns",
    "supplier_payments",
    "service_contracts",
    "customer_reports",
    "supplier_reports",
    "sales_reports",
    "purchase_reports",
    "service_reports",
    "accounting_reports",
]

BUSINESS_MODULES = {
    "dashboard",
    "customers",
    "suppliers",
    "item_services",
    "cash_bank_accounts",
    "expense_heads",
    "payment_terms",
    "quotations",
    "customer_confirmations",
    "delivery_challans",
    "sales_invoices",
    "sales_returns",
    "customer_receipts",
    "supplier_purchases",
    "purchase_returns",
    "supplier_payments",
    "service_contracts",
    "customer_reports",
    "supplier_reports",
    "sales_reports",
    "purchase_reports",
    "service_reports",
    "accounting_reports",
}

ROUTINE_TRANSACTION_MODULES = {
    "dashboard",
    "customers",
    "suppliers",
    "item_services",
    "quotations",
    "customer_confirmations",
    "delivery_challans",
    "sales_invoices",
    "sales_returns",
    "customer_receipts",
    "supplier_purchases",
    "purchase_returns",
    "supplier_payments",
    "service_contracts",
}

REPORT_MODULES = {
    "customer_reports",
    "supplier_reports",
    "sales_reports",
    "purchase_reports",
    "service_reports",
    "accounting_reports",
}

VIEWER_MODULES = BUSINESS_MODULES | REPORT_MODULES

DEFAULT_ACCOUNT_GROUPS = [
    ("1000", "Cash", "Assets"),
    ("1010", "Bank", "Assets"),
    ("1020", "Accounts Receivable", "Assets"),
    ("1030", "Input Tax Receivable", "Assets"),
    ("2000", "Accounts Payable", "Liabilities"),
    ("2010", "Output Tax Payable", "Liabilities"),
    ("3000", "Capital / Opening Balance", "Equity"),
    ("4000", "Sales", "Income"),
    ("4010", "Service Income", "Income"),
    ("5000", "Purchases / Cost of Goods", "Expenses"),
    ("5010", "Office Expenses", "Expenses"),
]
