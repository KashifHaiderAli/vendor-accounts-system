# Reports Phase Files Changed

## Files Created

- `web_app/templates/reports/group_menu.html`
  - Added the shared submenu/card page used by every report group.
- `web_app/reports/management/commands/test_reports_routes.py`
  - Added route smoke checks for report index, group submenus, individual reports, CSV export, and print mode.
- `web_app/reports/management/commands/test_reports_ui.py`
  - Added UI/content smoke checks to ensure group submenu labels are actually visible in rendered HTML.
  - Added checks that ledger/history pages render required filter controls and friendly required-filter messages.
  - Added checks that report pages hide irrelevant filters, for example customer statement no longer shows supplier, item, account, cash/bank, or system audit filters.
- `web_app/reports/management/commands/test_party_statements.py`
  - Added AUTO-TEST party statement checks for customer invoice/receipt running balance and supplier purchase/payment payable balance.
- `docs/codex_reports_phase_files_changed.md`
  - Documents files changed, routes added, reports implemented, and remaining TODO notes.

## Files Modified

- `web_app/reports/urls.py`
  - Added group submenu routes for customers, suppliers, sales, purchases, services, accounting, tax, inventory, and system reports.
  - Wired all individual report routes through the shared `generic_report` view.
- `web_app/reports/views.py`
  - Reorganized the report index to open group submenu pages.
  - Added report group definitions for every required group.
  - Added report configs and columns for detailed customer, supplier, sales, purchase, item, service, accounting, tax, inventory, and system reports.
  - Changed report index and submenu pages to always show navigation cards; individual report routes still enforce permissions.
  - Fixed report print-context collision so normal report pages render filter UI instead of print-only layout.
  - Added report-specific filter declarations so each report shows only the controls it needs.
- `web_app/core/context_processors.py`
  - Updated left sidebar report links to point at group submenu routes instead of individual default reports.
- `web_app/reports/report_utils.py`
  - Added raw-SQL query helpers for reports that were previously placeholder routes.
  - Added safe inventory report helpers that return friendly notes if inventory tables are unavailable.
  - Added reusable filter lookup helpers for customers, suppliers, items, accounts, cash/bank, branches, and users.
  - Fixed customer and supplier statement queries to use selected party data only and qualified joined columns so receipt/payment/return rows appear correctly.
  - Added opening/running balance behavior for party statements.
- `web_app/templates/reports/index.html`
  - Updated the priority reports wording to reflect full submenu navigation.
- `web_app/templates/reports/generic_table_report.html`
  - Added shared report filter controls including branch, dates, as-of date, customer, supplier, item, account, cash/bank, status, payment mode, invoice type, confirmation type, reference type, user, action, and module.
  - Updated the shared filter form to render only the filters listed by the active report config instead of showing every possible filter on every report.
- `web_app/README.md`
  - Updated the reports section with the full report group/menu structure and CSV/print behavior.

## Routes Added

- `/reports/customers/`
- `/reports/suppliers/`
- `/reports/sales/`
- `/reports/purchases/`
- `/reports/items/`
- `/reports/services/`
- `/reports/accounting/`
- `/reports/tax/`
- `/reports/tax/summary/`
- `/reports/inventory/`
- `/reports/system/`

## Individual Routes Added / Verified

- Customer: `/reports/customers/ledger/`, `/reports/customers/statement/`, `/reports/customers/outstanding/`, `/reports/customers/aging/`, `/reports/customers/sales/`, `/reports/customers/receipts/`
- Supplier: `/reports/suppliers/ledger/`, `/reports/suppliers/statement/`, `/reports/suppliers/payable/`, `/reports/suppliers/aging/`, `/reports/suppliers/purchases/`, `/reports/suppliers/payments/`
- Sales: `/reports/sales/quotations/`, `/reports/sales/confirmations/`, `/reports/sales/delivery-challans/`, `/reports/sales/invoices/`, `/reports/sales/returns/`, `/reports/sales/receipts/`, `/reports/sales/tax/`
- Purchase: `/reports/purchases/purchases/`, `/reports/purchases/returns/`, `/reports/purchases/payments/`, `/reports/purchases/tax/`, `/reports/purchases/profit-by-invoice/`, `/reports/purchases/profit-by-confirmation/`
- Items: `/reports/items/sales/`, `/reports/items/purchases/`, `/reports/items/profit/`, `/reports/items/history/`, `/reports/items/services-sales/`
- Services: `/reports/services/contracts/`, `/reports/services/expiring/`, `/reports/services/billing-due/`, `/reports/services/invoice-history/`
- Accounting: `/reports/accounting/cash-book/`, `/reports/accounting/bank-book/`, `/reports/accounting/general-ledger/`, `/reports/accounting/account-ledger/`, `/reports/accounting/trial-balance/`, `/reports/accounting/profit-loss/`, `/reports/accounting/balance-sheet/`, `/reports/accounting/journals/`, `/reports/accounting/expenses/`, `/reports/accounting/income/`
- Tax: `/reports/tax/summary/`
- Inventory: `/reports/inventory/stock-balance/`, `/reports/inventory/item-ledger/`, `/reports/inventory/stock-in/`, `/reports/inventory/stock-out/`, `/reports/inventory/low-stock/`, `/reports/inventory/valuation/`
- System: `/reports/system/activity/`, `/reports/system/login-logout/`, `/reports/system/prints/`, `/reports/system/exports/`, `/reports/system/backup-restore/`, `/reports/system/validation-failures/`

## Test Commands

- `python manage.py test_reports_ui`
- `python manage.py test_party_statements`
- `python manage.py test_reports_routes`
- `python manage.py test_reports_queries`

## Manual Test URLs

- `/reports/`
- `/reports/customers/`
- `/reports/customers/ledger/`
- `/reports/customers/statement/`
- `/reports/suppliers/`
- `/reports/suppliers/ledger/`
- `/reports/items/history/`
- `/reports/accounting/account-ledger/`

## Reports Implemented

- Customer: ledger, statement, outstanding, aging, customer-wise sales, customer-wise receipts.
- Supplier: ledger, statement, payable, aging, supplier-wise purchase, supplier-wise payment.
- Sales: quotations, confirmations/PO, delivery challans, invoices, returns, receipts, sales tax.
- Purchases: purchases, purchase returns, supplier payments, purchase tax, profit by invoice, profit by confirmation.
- Items: item-wise sales, item-wise purchases, item-wise profit, item transaction history, service-wise sales.
- Services: contract list, expiring contracts, billing due, invoice history.
- Accounting: cash book, bank book, general ledger, account ledger, trial balance, profit and loss, balance sheet, journals, expenses, income.
- Tax: tax summary.
- Inventory: stock balance, item ledger, stock in, stock out, low stock, valuation.
- System/Audit: activity, login/logout, prints, exports, backup/restore, validation failures.

## Reports Still TODO

- Inventory reports depend on optional inventory tables. If those tables are not upgraded in an existing database, the routes show a friendly empty/note state instead of crashing.
- Service contract invoice history uses safe remarks/service-type matching because no direct invoice-to-contract link column exists.
- Profit reports use confirmation-linked purchases where available and otherwise show zero/estimated cost according to available data.
