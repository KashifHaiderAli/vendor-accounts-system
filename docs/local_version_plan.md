# LocalVersion / Non-Tax Mode

MainVersion remains the tax-enabled deployment:

- Folder: `C:\VendorAccounts\MainVersion\`
- Database: `C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db`
- Port: `8000`
- Environment: `ENABLE_TAX=True`

LocalVersion is the non-tax/local vendor deployment:

- Folder: `C:\VendorAccounts\LocalVersion\`
- Database: `C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db`
- Port: `8001`
- Environment: `ENABLE_TAX=False`

Both versions use the same codebase. The edition behavior is controlled by `core.edition_utils`.

## Tax Switch

The deployment environment is the top-level control. If `ENABLE_TAX=False`, tax is disabled regardless of posted form values or saved settings.

When `ENABLE_TAX=True`, the `admin` username can change the database-backed tax setting from Settings. Other administrators cannot switch the edition mode.

## LocalVersion Behavior

When tax is disabled:

- Backend calculations force tax option and tax amounts to zero.
- Quotation, invoice, supplier purchase, return, and expense calculations ignore posted tax values.
- Sidebar hides tax summary/settings links.
- Report group menus hide sales/purchase/tax summary reports.
- Print totals omit tax rows.
- Existing line-level/document totals keep the local layout simple: subtotal, discount, and grand total. No database columns were added for a separate document-discount field in this phase.
- LocalVersion uses the separate SQLite file and a separate `license_records` table.

## LocalVersion Deployment

Deployment files live in `deployment\local\`:

- `start_local_web.bat`
- `build_local_web_package.bat`
- `VendorAccountsWebApp_Local_Setup.iss`
- `open_firewall_port_8001.bat`
- `test_installed_local_web.bat`
- `README_DEPLOY_LOCAL.md`

The installer uses the same portable Python runtime pattern as MainVersion and patches `python*._pth` automatically so `..\..\web_app` is importable after installation.

## DB App

DB App supports both deployment database files. Use Database tab:

- MainVersion: `C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db`
- LocalVersion: `C:\VendorAccounts\LocalVersion\data\vendor_accounts_local.db`

Generate one license for MainVersion DB and another license for LocalVersion DB.

## Commands

```powershell
python manage.py test_tax_switch
python manage.py test_local_version_mode
python manage.py test_local_version_license
python ..\db_app_test_local_version_db.py
```
