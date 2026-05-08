# Corporate Supplier Accounts System Web App

This folder contains the Phase 2 Django web application foundation for the Corporate Supplier Accounts System.

The web app uses Django Templates, Bootstrap 5, and the SQLite database created by the existing DB App. It does not create or modify database tables in this phase.

The current UI theme is Windows 11 inspired and built with Bootstrap 5, Bootstrap Icons, and lightweight custom CSS. It uses soft surfaces, rounded cards, subtle shadows, responsive navigation, and reusable utility classes for future accounting screens.

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
VENDOR_ACCOUNTS_DB_PATH=D:\Development\vendor-accounts-system\data\vendor_accounts.db
DJANGO_SECRET_KEY=local-dev-secret-key-change-later
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

If `VENDOR_ACCOUNTS_DB_PATH` is missing, the app falls back to the repo-level database path:

```text
vendor-accounts-system/data/vendor_accounts.db
```

The database must be created first using the DB App. The web app will not create or alter the database schema.

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

Licenses must be generated from the DB App. If the license is missing, expired, inactive, or belongs to a different hardware fingerprint, the web app redirects to the license expired page and shows the current hardware fingerprint for renewal.

## Phase 4 Settings Screens

Phase 4 adds working settings screens that use the existing DB App-created tables with raw SQL helpers:

- Company Settings: `/settings/company/`
- Branch Management: `/settings/branches/`
- Numbering Settings: `/settings/numbering/`
- Tax Settings: `/settings/tax/`

These pages require login, a valid license, and the matching role permissions:

- `company_settings`: view/edit
- `branches`: view/add/edit/delete permission family, with add/edit used by the current screens
- `numbering_settings`: view/edit
- `tax_settings`: view/edit

Branch management enforces the current company from the logged-in session, unique branch codes per company, a single Head Office branch, and at least one active branch. Head Office branches cannot be deactivated. When a Master Admin creates a branch, that user is automatically granted branch access in `user_branches`.

Settings updates write to the existing `companies`, `company_settings`, `branches`, `numbering_settings`, and `tax_settings` tables. User actions are logged into `user_activity_log`.

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

## Phase Notes

Phase 2 provides only the Django project foundation, shared layout, dashboard placeholder, login placeholder, and module route placeholders.

Phase 3 adds custom authentication, role permissions, branch session handling, and license checking. Phase 4 adds settings management. Phase 5 adds master data maintenance. Phase 6 adds the hidden journal engine and read-only accounting screens. Phase 6.5 adds validation and safety hardening. Phase 7 adds quotations. Phase 8 adds customer confirmations. Purchase, delivery challan, invoice, receipt, and report modules will be added in later phases.
