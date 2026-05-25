# DB App New Client Reset

## Purpose

The DB App can prepare a SQLite database for a new client deployment by removing development, smoke, demo, AUTO-TEST, and business transaction data while keeping the required system setup.

This is intended for standalone SQLite deployment before installing the system for a fresh client.

## DB App UI

Open DB App and go to:

```text
Database tab -> Prepare Database for New Client
```

For MainVersion deployment, first click Browse Database File and select:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

The reset runs against the exact selected database file. Folder mode still uses `selected folder\vendor_accounts.db` for development.

The app shows a warning and requires typing:

```text
RESET
```

before it runs.

## Backup Behavior

Before any real reset, the DB App creates a backup copy:

```text
<database folder>/backups/pre_client_reset_YYYYMMDD_HHMMSS.db
```

If backup creation fails, reset stops.

## Data Kept

The reset keeps:

- companies
- branches
- users
- user_roles
- permissions
- role_permissions
- user_branches
- license_records
- numbering_settings
- company_settings
- tax_settings
- accounts / chart of accounts
- system_pages, app_state, app_settings if present
- table structure for every table

Master/Admin users, passwords, roles, permissions, company, branch, chart of accounts, numbering, settings, and licenses remain unchanged.

## Data Deleted

The reset deletes rows from business/demo tables when those tables exist:

- customers
- suppliers
- item_services
- quotations and quotation_items
- customer_confirmations and customer_confirmation_items
- delivery_challans and delivery_challan_items
- sales_invoices and sales_invoice_items
- customer_receipts and customer_receipt_allocations
- sales_returns and sales_return_items
- supplier_purchases and supplier_purchase_items
- supplier_payments and supplier_payment_allocations
- purchase_returns and purchase_return_items
- service_contracts and service_contract_items
- stock_movements
- stock_adjustments and stock_adjustment_items
- journal_entries and journal_entry_lines
- expense_vouchers and expense_voucher_items
- user_activity_log, audit_logs, print_logs, export_logs unless `keep_logs=True`

Tables that do not exist are skipped safely.

## What It Does Not Do

- It does not drop tables.
- It does not run Django migrations.
- It does not delete the SQLite database file.
- It does not delete users, roles, permissions, company, branch, accounts, or license records.

## Command Line Usage

Dry-run:

```powershell
python db_app_reset_for_new_client.py --db "C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db" --dry-run
```

Real reset:

```powershell
python db_app_reset_for_new_client.py --db "C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db"
```

Keep audit/log rows:

```powershell
python db_app_reset_for_new_client.py --db "C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db" --keep-logs
```

## Test Script

Run:

```powershell
python db_app_test_reset_database.py
```

The test creates a temporary database, inserts AUTO-TEST data, runs dry-run, runs reset, verifies setup tables remain, verifies business tables are empty, and prints PASS.

## Verification Before Client Deployment

1. Run the dry-run command and review the row counts.
2. Run the reset from DB App or CLI.
3. Confirm backup path was created.
4. Open DB App and check company, branch, admin user, roles, permissions, accounts, license, numbering, and settings.
5. Open Web App and login as admin.
6. Confirm business lists are empty.

## Warning

This action is irreversible except by restoring the backup database file created before reset. Always keep the backup file.
