# Corporate Supplier Accounts System Web App

This folder contains the Phase 2 Django web application foundation for the Corporate Supplier Accounts System.

The web app uses Django Templates, Bootstrap 5, and the SQLite database created by the existing DB App. It does not create or modify database tables in this phase.

The current UI theme is Windows 11 inspired and built with Bootstrap 5, Bootstrap Icons, and lightweight custom CSS. It uses soft surfaces, rounded cards, subtle shadows, responsive navigation, and reusable utility classes for future accounting screens.

## Editions

MainVersion is the current tax-enabled deployment on port `8000` using:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
ENABLE_TAX=True
```

LocalVersion is the non-tax deployment on port `8001` using:

```text
C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db
ENABLE_TAX=False
```

Both versions use one codebase. When `ENABLE_TAX=False`, backend document calculations force tax amounts to zero, report links for tax-specific reports are hidden or disabled, and print totals omit tax rows. The `admin` username is the only user allowed to change the tax switch when the deployment environment permits it.

## Setup

Create and activate a virtual environment:

```powershell
cd web_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Environment File

The app automatically loads environment values from:

```text
web_app/.env
```

Use `web_app/.env.example` as the template for local setup. The local `.env` file is ignored by Git so each machine can keep its own database path and development secret.

Current local example:

```text
VENDOR_ACCOUNTS_DB_PATH=C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
ENABLE_TAX=True
DJANGO_SECRET_KEY=local-dev-secret-key-change-later
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

If `VENDOR_ACCOUNTS_DB_PATH` is missing, the app falls back to the repo-level database path:

```text
vendor-accounts-system/data/vendor_accounts.db
```

The database must be created first using the DB App. The web app will not create or alter the database schema.

For MainVersion deployment, if an older prepared file is still named `vendor_accounts.db`, copy or rename it to:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

## Run With Python

```powershell
python manage.py runserver
```

## Run With Script

From `web_app/` on Windows:

```powershell
.\run_web_app.bat
```

The script activates the repo virtual environment at `..\venv` when it exists, then starts Django at `127.0.0.1:8000`.

Git Bash users can run:

```bash
./run_web_app_gitbash.sh
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/login/

## Phase 3 Login, Branches, and License

The web app login uses the DB App-created user records from the custom `users` table. It does not use Django's default `auth_user` table.

Default web app login:

```text
username: admin
password: mdnuniball
```

The DB App login is separate:

```text
username: admin
password: infoline
```

The web app reads roles, permissions, assigned branches, company details, and license records from the SQLite database created by the DB App. Branch selection is based on the branches assigned to the logged-in user.

Licenses must be generated from the DB App. If the license is missing, expired, inactive, invalid, or belongs to a different hardware fingerprint, the web app redirects to the license expired page and shows the current hardware fingerprint for renewal. The Web App validates the stored license key, license type, active flag, hardware fingerprint, start date, and expiry/lifetime rules.

License behavior:

- Login, logout, static files, and the license expired page are allowed without a valid license.
- Dashboard, transactions, reports/export, print pages, backup/restore, settings, and user management are blocked without a valid license.
- Trial licenses are valid for 30 days from the start date.
- Annual licenses are valid for 365 days from the start date.
- Lifetime licenses do not expire, but still require an active matching license key and hardware fingerprint.
- License failures are logged in `user_activity_log` as `LICENSE_FAILURE` when audit logging is available.

To check the current hardware fingerprint, open the license expired page or use the DB App licensing tab. To generate a license, use the DB App licensing tab, select Trial, Annual, or Lifetime, generate the key, and save the record into the active SQLite database.

The Web App also includes a real License Status / License Activation page:

```text
/license/
```

Use this page to:

- view current license status
- copy the current hardware fingerprint
- paste and activate a DB App-generated license key
- review license history
- deactivate or reactivate valid license records

Activation from Web App:

1. Login as Master Admin/Admin or a user with license/settings access.
2. Open `/license/`.
3. Copy the displayed hardware fingerprint.
4. Open DB App, select the same SQLite database, and open the Licensing tab.
5. Generate Trial, Annual, or Lifetime license.
6. Paste the key into `/license/` and click Activate License.

If the DB App already saved the license directly into the database, click Refresh Status on `/license/`.

For MainVersion deployment, DB App must use Browse Database File and select:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

The Web App uses `VENDOR_ACCOUNTS_DB_PATH`, so do not save a license into `vendor_accounts.db` unless the Web App is also configured to use that file.

License test command:

```bash
python manage.py test_license_page
python manage.py test_licensing_system
```

The test commands create temporary license scenarios in a transaction and roll them back. They verify the license page, activation flow, valid, missing, expired, inactive, wrong-hardware, invalid-key, trial, annual, lifetime, middleware, and audit-log behavior.

Standalone deployment notes:

- MainVersion is the current TAX/main version and runs on port `8000` with `ENABLE_TAX=True`.
- MainVersion database path example: `C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db`.
- LocalVersion is the future non-tax/local vendor version and will run on port `8001` with `ENABLE_TAX=False`.
- LocalVersion database path example: `C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db`.
- Each SQLite database has its own `license_records` table and should receive its own saved license record.
- The current key format is tied to hardware, license type, and start date. It does not yet include edition name or database id, so keep edition/license assignments documented during deployment.
- Keep the live SQLite database outside OneDrive, Google Drive, or Dropbox sync folders. Backups may be copied to synced folders.

## Phase 4 Settings Screens

Phase 4 adds working settings screens that use the existing DB App-created tables with raw SQL helpers:

- Company Settings: `/settings/company/`
- Branch Management: `/settings/branches/`
- Users & Roles: `/settings/users-roles/`
- Role Management: `/settings/role-management/`
- Numbering Settings: `/settings/numbering/`
- Tax Settings: `/settings/tax/`

These pages require login, a valid license, and the matching role permissions:

- `company_settings`: view/edit
- `branches`: view/add/edit/delete permission family, with add/edit used by the current screens
- `user_management`: view/add/edit for custom users, branch access, activation, and password reset
- `role_management`: view/add/edit for roles and permission flags
- `numbering_settings`: view/edit
- `tax_settings`: view/edit

Branch management enforces the current company from the logged-in session, unique branch codes per company, a single Head Office branch, and at least one active branch. Head Office branches cannot be deactivated. When a Master Admin creates a branch, that user is automatically granted branch access in `user_branches`.

Users & Roles uses the custom `users`, `user_roles`, and `user_branches` tables only. It does not use Django `auth_user`. New users and password resets receive the temporary password `Temp@12345`; blank passwords are not allowed, and users should change the temporary password after login.

Role Management uses `permissions` and `role_permissions` for view/add/edit/delete/print/export flags. Roles are activated/deactivated instead of hard-deleted.

Generic testing users and roles can be created with:

```powershell
python manage.py seed_generic_users_roles
python manage.py test_users_roles_pages
```

Settings updates write to the existing `companies`, `company_settings`, `branches`, `numbering_settings`, `tax_settings`, `users`, `user_roles`, `user_branches`, and `role_permissions` tables. User actions are logged into `user_activity_log`.

## Phase 5 Master Data Screens

Phase 5 adds branch-level master data screens using existing DB App-created tables:

- Customers: `/masters/customers/`
- Suppliers: `/masters/suppliers/`
- Items / Services: `/masters/items/`
- Cash / Bank Accounts: `/masters/cash-bank/`
- Expense Heads: `/masters/expense-heads/`
- Payment Terms: `/masters/payment-terms/`

All master lists support search, active/inactive/all filters, pagination, permission-based actions, and activate/deactivate behavior. Records are filtered by the logged-in `company_id` and `current_branch_id`; master records are not hard-deleted.

Customers, suppliers, cash/bank accounts, and expense heads automatically create linked records in the existing `accounts` table. The linked account name is updated when the master name changes. No inventory management, stock quantity, or serial number tracking is included in this phase.

Master data actions are logged into `user_activity_log`.

## Phase 6 Hidden Accounting Engine

Phase 6 adds the hidden accounting foundation used by future transaction modules:

- Default Chart of Accounts assurance for each company/branch.
- Double-entry journal validation using `Decimal` money calculations.
- Journal entry creation and reversal helpers.
- Posting helpers for future sales invoices, customer receipts, supplier purchases, supplier payments, sales returns, purchase returns, and expense vouchers.
- Trial balance and account ledger backend utilities for later reports.
- Read-only Chart of Accounts page: `/accounts/chart/`
- Read-only Journal Entries page: `/accounts/journals/`

The accounting engine writes only to existing DB App-created tables: `accounts`, `journal_entries`, `journal_entry_lines`, and `user_activity_log`. It does not create or alter database schema.

Developer smoke test:

```powershell
python manage.py test_journal_engine
```

The command ensures the default chart of accounts, creates one balanced test journal if one does not already exist with `reference_type = "test_journal_engine"`, and prints `PASS`.

## Phase 6.5 Validation and Safety Pass

Phase 6.5 strengthens master data safety before transaction modules:

- Shared validation utilities in `core/validators.py`
- Friendly field-level errors and form error summaries
- Preserved submitted form values after validation failures
- Stronger duplicate, email, decimal, integer, choice, tax-rate, and opening-balance checks
- Safer linked-account creation for customers, suppliers, cash/bank accounts, and expense heads
- Transaction rollback when a master record and linked account cannot both be saved
- No hard deletes; master records still use activate/deactivate
- Cash/bank accounts with journal entries are blocked from deactivation
- Placeholder reference checks are in place for future invoice/purchase safety

Validation smoke test:

```powershell
python manage.py test_master_validations
```

The command checks the reusable validation helpers and duplicate detection without creating database records.

## Phase 6.6 Strong Field Validation

Phase 6.6 adds stricter backend and frontend validation across the existing settings and master forms:

- Phone and mobile format checks
- Email and website validation
- Money, decimal, percentage, integer, and date validators
- Max-length checks for important text fields
- Stronger frontend input attributes for contact, money, percentage, and integer fields
- Continued backend enforcement even if browser validation is bypassed

Manual validation scenarios are documented in `docs/validation_checklist.md`.

## Phase 7 Quotation Module

Phase 7 adds the customer quotation workflow under `/sales/quotations/`:

- Quotation list with search, status/date filters, pagination, and permission-based actions
- Quotations for either existing Customer Master records or new/unregistered walk-in parties
- Existing customer details are copied into the quotation for historical print accuracy
- Unregistered quotation parties can later be added to Customer Master from the quotation detail page
- Create and edit forms with a lightweight dynamic item grid
- Server-side validation and total recalculation for every quotation line
- Detail, duplicate, cancel, print, and PDF-friendly HTML views
- Quotation statuses: Draft, Printed, Converted, Cancelled, with Expired shown visually when valid-till has passed
- Activity logging for create, update, duplicate, cancel, and print/PDF views
- Convert to Customer Confirmation / PO route that opens the Phase 8 confirmation form

Quotations do not post journal entries and do not affect accounts. The `/pdf/` route currently returns the same clean print-friendly HTML response so it stays reliable on Windows without adding a native PDF dependency. A dedicated PDF engine can be added later if needed.

Existing databases created before unregistered quotation-party support should be upgraded once:

```powershell
python manage.py upgrade_schema_quotation_customer_fields
```

New databases created by the DB App already include the quotation customer snapshot fields.

## Phase 8 Customer Confirmation / PO Module

Phase 8 adds Customer Confirmation / PO tracking under `/sales/confirmations/`:

- Confirmation list with search, type/status/date filters, pagination, and permission-based actions
- Direct confirmations for existing customers
- Quotation-based confirmations for both saved customers and unregistered quotation parties
- Confirmation types: PO, Phone, WhatsApp, Email, and Direct
- PO number is required only when confirmation type is PO
- Conversion from quotation updates the quotation status to Converted
- Duplicate active confirmations from the same quotation are blocked
- Confirmation detail, edit, cancel, and print views
- Future Create Purchase, Create Delivery Challan, and Create Invoice buttons are visible as disabled placeholders
- Activity logging for create, update, conversion, cancel, and print

Confirmations do not create journal entries and do not affect accounts. In Version 1, direct confirmation without a quotation requires selecting an existing customer. New or unregistered parties are supported through quotation-based confirmation.

## Phase 9 Supplier Purchase Module

Phase 9 adds supplier purchase recording under `/purchases/supplier-purchases/`:

- Supplier purchase list with search, status/date filters, pagination, and permission-based actions
- Purchase form with dynamic item rows and server-side total recalculation
- Supplier purchases post accounting journals through the hidden journal engine
- Debit Purchases / Cost of Goods, debit Input Tax Receivable when applicable, and credit Supplier Payable
- `journal_entry_id` is saved on the purchase header for audit drill-down
- Purchases do not affect inventory and do not add serial tracking
- Posted purchase financial details are read-only; only supplier bill details and remarks can be edited
- Cancelling a purchase keeps the record, marks it Cancelled, and creates a reversal journal entry
- Supplier payments and purchase returns remain future modules

## Phase 10 Delivery Challan Module

Phase 10 adds Delivery Challans under `/sales/delivery-challans/`:

- Create delivery challans directly, from a customer confirmation, or from a quotation
- Delivery challans do not post accounting entries
- Delivery challans do not include rates, taxes, or amounts
- Quotation and confirmation item rows can be copied into the challan
- Unregistered quotation parties are supported through the stored quotation customer snapshot
- Print-friendly A4 delivery challan with receiver signature/stamp area
- Signed copy path support through `/upload-signed-copy/`
- Cancelled challans are retained for audit history
- Invoice creation remains a future phase

Development smoke data can be generated with:

```powershell
python manage.py seed_smoke_test_data
```

The command is idempotent and creates `SMK` / `Smoke` sample records for masters, quotations, confirmations, supplier purchases, and delivery challans without deleting existing data. It is intended for local development and testing only.

## Phase 11 Sales Invoice / Cash Memo Module

Phase 11 adds Sales Invoices and Cash Memos under `/sales/invoices/`:

- Create invoices directly, from delivery challan, from confirmation, or from quotation
- Invoices post journal entries through the hidden accounting engine
- Debit Customer Receivable, credit Sales, and credit Output Tax Payable when tax is present
- Posted financial fields and item rows are locked; cancel and recreate if financial details need correction
- Cancelling an invoice creates a reversal journal entry and restores source document status where safe
- Pre-printed invoice print excludes logo/company header and uses CSS offsets for A4 invoice stationery
- Digital print includes company details and logo path when available
- Payments are recorded through the Customer Receipt module added in Phase 12

The smoke data command also creates one posted smoke sales invoice from the smoke delivery challan.

## Phase 12 Customer Receipt Module

Phase 12 adds Customer Receipts under `/sales/receipts/`:

- Create receipts directly or from a sales invoice
- Supports Cash, Bank, Cheque, and Online Transfer modes
- Receipts post journal entries through the hidden accounting engine
- Debit Cash/Bank and credit Customer Receivable
- Partial payments are supported and invoice balance/status is updated
- Overpayment is blocked when adjusting a specific invoice
- Advance/unadjusted customer receipts are allowed
- Posted financial fields are locked; only reference number and remarks can be edited
- Cancelling a receipt creates a reversal journal and restores invoice balance where applicable

## Phase 13 Supplier Payment Module

Phase 13 adds Supplier Payments under `/purchases/supplier-payments/`:

- Create payments directly or from a supplier purchase
- Supports Cash, Bank, Cheque, and Online Transfer modes
- Supplier payments post journal entries through the hidden accounting engine
- Debit Supplier Payable and credit Cash/Bank
- Partial payments are supported and purchase balance/status is updated
- Overpayment is blocked when adjusting a specific purchase
- Advance/unadjusted supplier payments are allowed
- Posted financial fields are locked; only reference number and remarks can be edited
- Cancelling a payment creates a reversal journal and restores purchase balance where applicable

The smoke data command also creates one smoke customer receipt and one smoke supplier payment when matching smoke invoice/purchase balances are available.

## Phase 14 Sales and Purchase Returns

Phase 14 adds return workflows:

- Sales Returns under `/sales/returns/`
- Purchase Returns under `/purchases/returns/`
- Returns can be created directly or from the related invoice/purchase
- Return quantities are checked against original quantities less previous non-cancelled returns
- Sales returns post credit note journals and reduce invoice balance
- Purchase returns post debit note journals and reduce supplier purchase balance
- Posted return financial fields are locked; cancel and recreate if financial details need correction
- Cancelling a return keeps the record, creates a reversal journal, and restores source balance/status
- Returns do not affect inventory and do not create cash refunds automatically

## Phase 15 Service Contracts

Phase 15 adds Service Contracts under `/services/contracts/`:

- Create, edit, print, and close customer service contracts
- Supports Monthly, Quarterly, Yearly, and One Time billing cycles
- Contract invoice generation creates a posted sales invoice through the existing invoice module
- Contract invoice generation updates next billing date, or closes one-time contracts
- Service contracts do not post journal entries directly; accounting starts when an invoice is generated

The smoke data command also creates one smoke sales return, one smoke purchase return, one active service contract, and one idempotent contract invoice when possible.

## Phase 16 Expense Vouchers

Phase 16 adds Expense Vouchers under `/accounts/expenses/`:

- Expense vouchers post journal entries immediately
- Debit Expense Head, debit Input Tax Receivable when tax is present, and credit Cash/Bank
- Posted financial fields are locked; only reference number and remarks can be edited
- Cancelling a voucher keeps the record and creates a reversal journal
- Existing databases may need the raw SQL schema upgrade:

```powershell
python manage.py upgrade_schema_expense_vouchers
```

New databases created by the DB App include the expense voucher table.

## Phase 17 Real Dashboard

The dashboard at `/` now uses live branch-level data:

- Today sales, month sales, customer outstanding, supplier payable, cash/bank balance
- Today receipts and supplier payments excluding detected reversals
- Active contracts, expiring contracts, license status
- Recent invoices, receipts, purchases, delivery challans, and activity logs
- Permission-aware quick actions
- Lightweight six-month sales and receipts bars

Dashboard query testing:

```powershell
python manage.py test_dashboard_queries
```

Smoke data now creates one expense voucher when the expense voucher table exists.

## Company Logo Upload

Company logos now use the existing `companies.logo_path` field.

- DB App company setup includes a Browse Logo button
- Web App `/settings/company/` supports logo upload, preview, and remove
- Allowed logo formats: PNG, JPG, JPEG, WEBP, BMP
- Maximum web upload size: 2 MB
- Logos are copied to the database folder under `company_assets/logo/company_logo.<ext>`
- Quotation print, digital invoice print, service contract print, and report print headers show the logo when available
- Pre-printed invoice output intentionally does not show the logo or company header

## Phase 18 Reports

Reports are available under `/reports/` with branch-aware filters, CSV export, and print-friendly pages.

The reports index opens group submenu pages instead of sending users directly into one generic report:

- Customer Reports: ledger, statement, outstanding, aging, customer-wise sales, customer-wise receipts
- Supplier Reports: ledger, statement, payable, aging, supplier-wise purchase, supplier-wise payment
- Sales Reports: quotations, confirmations/PO, delivery challans, invoices, returns, receipts, sales tax
- Purchase Reports: purchases, purchase returns, supplier payments, purchase tax, profit by invoice, profit by confirmation/PO
- Item / Product Reports: item-wise sales, purchases, profit, transaction history, service-wise sales
- Service Reports: contract list, expiring contracts, billing due, invoice history
- Accounting Reports: cash book, bank book, general ledger, account ledger, trial balance, profit and loss, balance sheet, journals, expenses, income
- Tax Summary: output tax, input tax, and net tax payable/receivable
- Inventory Reports: stock balance, item ledger, stock in, stock out, low stock, valuation when inventory tables exist
- System / Audit Reports: activity, login/logout, prints, exports, backup/restore, validation failures

Run the report query smoke test:

```powershell
python manage.py seed_smoke_test_data
python manage.py test_reports_queries
python manage.py test_reports_ui
python manage.py test_party_statements
python manage.py test_reports_routes
```

CSV export is available from each report screen. The PDF button opens the print-friendly HTML view so the browser can print or save as PDF without adding a heavy Windows-sensitive PDF dependency.

## Phase 18.5 Additional Reports

Additional business and audit reports are available from the same reporting framework:

- Item / Product Reports: item-wise sales, purchases, profit, transaction history, and service-wise sales
- Accounting Reports: expense report, income report, tax summary, and account ledger
- System / Audit Reports: user activity, login/logout, document prints, report exports, backup/restore, and validation failures

Item reports are transaction/history/profit reports only. Stock balances are handled by the Inventory Control System described below.

Run the expanded report query smoke test:

```powershell
python manage.py test_reports_queries
python manage.py test_reports_ui
python manage.py test_party_statements
python manage.py test_reports_routes
```

## Phase 19 Print Finalization

Common print helpers and CSS were added for stable A4 output.

- Shared print CSS lives in `static/css/print.css`
- Pre-printed invoice alignment defaults live in `core/print_settings.py`
- Pre-printed invoice supports CSS variables for top offset, left offset, font size, and line height
- Digital document prints can show the company logo through a safe logo-serving route
- Future work can move print alignment settings from constants into database-backed settings

## Client Print / PDF Layout Update

Business document detail pages now expose three print choices:

- Print Without Logo: compact A4 output without logo/header block
- Print With Logo: compact A4 output with logo when `companies.logo_path` points to an existing file
- PDF / Digital Copy: print-friendly digital output with logo enabled, intended for browser Save as PDF

Company address, phone, email, website, NTN, and STRN are shown once in the document footer. Headers no longer repeat the full company address.

Print layouts use narrow A4 margins, compact table padding, and smaller row heights so normal invoices, quotations, delivery challans, returns, vouchers, and contracts can fit at least 10 detail rows comfortably.

Customer, party, and document metadata is shown in a compact tabular detail block, normally three columns across and about three rows deep. Long values such as address, subject, or reason can span columns so the item table starts higher on the page.

Tax is still calculated and stored normally, but item detail tables on print/PDF formats no longer show per-row tax columns. Tax appears in the totals section only.

Quantities are displayed without unnecessary decimal places. For example, `1.00` displays as `1`, while `2.50` displays as `2.5`.

Quotation print/PDF output shows `Tax Total` in the totals section when quotation tax is saved, while keeping the item detail table free of per-row tax columns.

Quotation and invoice tax are calculated after discount:

- Exclusive tax: `base = qty * rate`, `discounted = base - discount`, `tax = discounted * tax% / 100`, `grand = discounted + tax`
- Inclusive tax: `gross = qty * rate`, `discounted_gross = gross - discount`, `tax = discounted_gross * tax% / (100 + tax%)`, `grand = discounted_gross`

On quotation entry, the posted row tax percent is saved and used first. The product master `default_tax_rate` is only used when the row tax is blank, and a missing form tax option defaults to `tax_exclusive` rather than silently disabling tax.

The quotation form JavaScript mirrors the backend formula so the live row tax, subtotal, discount, tax total, and grand total preview match the saved quotation before submission.

If the quotation form still appears to use an old tax calculation after an update, hard refresh the browser with `Ctrl+F5`. The quotation page loads `static/js/quotation.js` with a version query string and logs `quotation.js loaded: qtax_discount_fix_20260520` in the browser console for quick verification.

Run the print template check:

```powershell
python manage.py test_print_templates
python manage.py test_quantity_and_quotation_tax
python manage.py test_quotation_tax_discount
```

## Phase 20 Backup / Restore

System backup and restore tools are available under `/system/backup/`.

- Backup Now creates `vendor_accounts_backup_YYYYMMDD_HHMMSS.db`
- Backup metadata is written next to the backup as JSON
- Backup history is stored in `data/backup_history.json` when no database history table exists
- Backup folder settings are stored in `data/system_settings.json`
- Restore is Master Admin only
- Restore always creates `safety_before_restore_YYYYMMDD_HHMMSS.db` before replacing the live database
- The system keeps the latest 30 `vendor_accounts_backup_*.db` files and leaves safety backups alone
- If the live DB path appears to be inside OneDrive, Google Drive, or Dropbox, the backup dashboard shows a warning
- Backup files may be stored in synced folders, but the live database should stay in a local non-synced folder

## Phase 21 Audit Log And Safety

Audit tools are available under `/system/audit-log/`.

- Login, logout, permission denial, license failure, report export/print, backup, and restore events are logged
- Existing module create/edit/cancel/print actions continue writing into `user_activity_log`
- Audit log is read-only and can be filtered or exported to CSV
- Business records should not be hard-deleted; use cancel/close flows and reversal journals for posted records
- Posted financial records remain protected from silent financial edits; cancel and recreate is the safe default

## Phase 22 Validation And Bug Prevention

Validation safety checks were added in a management command:

```powershell
python manage.py seed_smoke_test_data
python manage.py test_validation_safety
```

The command checks duplicate document numbers, invalid invoice dates, negative totals, over-receipts, over-payments, unbalanced journals, missing linked accounts, invalid branch access, and expense voucher amount validation.

## Inventory Control System

The inventory module tracks product quantities only. It does not change accounting journals, inventory valuation accounting, COGS posting, serial numbers, warehouses, batches, or expiry.

- Product items can track inventory; service items never affect stock.
- Stock increases from supplier purchases, sales returns marked `Return to Stock`, opening stock, and stock adjustments in.
- Stock decreases from delivery challans, direct sales invoices without a delivery challan, purchase returns, and stock adjustments out.
- Invoices created from delivery challans do not reduce stock again.
- Negative stock is blocked for delivery challans, direct invoices, purchase returns, and stock adjustments out.
- Cancelling a purchase is blocked if that purchase stock has already been issued.
- Inventory settings live under Settings -> Inventory Settings.
- Inventory pages live under `/inventory/`.
- Report shortcuts are available at `/reports/inventory/stock-balance/` and `/reports/inventory/item-ledger/`.

Existing databases must be upgraded with raw SQL helpers, not Django migrations:

```powershell
python manage.py upgrade_schema_inventory
python manage.py rebuild_stock_movements
python manage.py test_inventory_validation
```

Use `python manage.py rebuild_stock_movements --reset` only when you intentionally want to regenerate system stock movements from existing transactions.

## Full System Scenario Test

Run the complete scenario-based smoke test with:

```powershell
python manage.py run_full_system_scenario_test --report-format=html --verbose
```

The command creates/reuses `AUTO-TEST` records and generates detailed HTML/TXT reports in `web_app/test_reports/`.

It checks the full business story:

- Quotation, Confirmation/PO, Supplier Purchase, Delivery Challan, Sales Invoice
- Customer Receipts, Supplier Payments, Sales/Purchase Returns, Service Contracts, Expense Vouchers
- Accounting journals, trial balance, control-account safety, and linked accounts
- Inventory stock in/out, negative-stock blocking, service-item stock exclusion, and rebuild helpers
- Validation blocks, report query functions, print template checks, audit log growth, backup creation, and license/restore skip policy

The report includes each step, input, expected result, actual result, PASS/FAIL/WARNING/SKIPPED status, errors, and safe auto-fix notes. It is intended for development/testing databases and is not recommended on a live database without a fresh backup.

## Chart Of Accounts Flags

The Chart of Accounts uses two protection flags from the `accounts` table:

- Control: parent/group accounts such as Assets, Liabilities, Accounts Receivable, and Office Expenses. These are shown as `Yes` and cannot receive direct journal postings.
- System: accounts created or managed by the application. These are protected from unsafe edit/delete flows.

Posting/detail accounts such as Cash, Bank, Sales, Purchases / Cost of Goods, tax accounts, customer linked accounts, supplier linked accounts, cash/bank linked accounts, and expense head linked accounts should show Control = `No`.

For existing databases, repair account flags with:

```powershell
python manage.py fix_account_flags
```

## Phase Notes

Phase 2 provides only the Django project foundation, shared layout, dashboard placeholder, login placeholder, and module route placeholders.

Phase 3 adds custom authentication, role permissions, branch session handling, and license checking. Phase 4 adds settings management. Phase 5 adds master data maintenance. Phase 6 adds the hidden journal engine and read-only accounting screens. Phase 6.5 adds validation and safety hardening. Phase 7 adds quotations. Phase 8 adds customer confirmations. Phase 9 adds supplier purchases. Phase 10 adds delivery challans. Phase 11 adds sales invoices. Phase 12 adds customer receipts. Phase 13 adds supplier payments. Phase 14 adds sales and purchase returns. Phase 15 adds service contracts. Phase 16 adds expense vouchers. Phase 17 replaces the placeholder dashboard with live branch metrics. Phase 18 adds the reporting framework and priority reports. Phase 19 adds print/PDF layout finalization helpers. Phase 20 adds web backup/restore. Phase 21 adds audit log and safety logging. Phase 22 adds validation safety checks. The inventory phase adds quantity-only stock control and inventory reports without changing accounting flow.
