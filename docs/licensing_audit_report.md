# Licensing Audit Report

Date: 2026-05-21

## Scope

This audit reviewed only the licensing system for the DB App and Web App. No accounting, reports, sales, purchases, inventory, print, or business transaction modules were changed.

## Files Inspected

- `db_app/app/licensing/hardware_fingerprint.py`
- `db_app/app/licensing/license_generator.py`
- `db_app/app/ui/licensing_tab.py`
- `db_app/app/database/schema.py`
- `web_app/licensing/hardware_fingerprint.py`
- `web_app/licensing/license_utils.py`
- `web_app/licensing/middleware.py`
- `web_app/licensing/views.py`
- `web_app/licensing/urls.py`
- `web_app/templates/licensing/license_expired.html`
- `web_app/authentication/middleware.py`
- `web_app/authentication/views.py`
- `web_app/core/audit_utils.py`
- `web_app/backup/views.py`
- `web_app/config/settings.py`
- `web_app/config/urls.py`

## Where License Is Generated

Licenses are generated in the DB App:

- UI: `db_app/app/ui/licensing_tab.py`
- Key generator: `db_app/app/licensing/license_generator.py`

The DB App shows the current hardware fingerprint, creates Trial, Annual, or Lifetime keys, and saves the license record into the selected SQLite database.

## Where License Is Stored

License records are stored in the SQLite table:

```text
license_records
```

This table lives inside each database file created/managed by the DB App. For standalone deployment, each SQLite database has its own license records.

## Table and Fields Used

The schema is defined in `db_app/app/database/schema.py`:

```text
id
company_id
branch_id
license_type
hardware_fingerprint
license_key
issue_date
start_date
expiry_date
is_lifetime
is_active
remarks
created_at
updated_at
```

The Web App currently validates company-level licenses. `branch_id` is stored but not used for enforcement.

## Hardware Fingerprint

Both DB App and Web App use the same fingerprint source:

- OS name
- OS release
- machine type
- processor string
- hostname
- MAC/node value from `uuid.getnode()`

The values are joined with `|` and SHA-256 hashed.

Files:

- `db_app/app/licensing/hardware_fingerprint.py`
- `web_app/licensing/hardware_fingerprint.py`

## License Key Logic

The license key is generated from:

```text
LICENSE_TYPE|hardware_fingerprint|start_date|VendorAccountsDBApp
```

The source text is SHA-256 hashed, uppercased, and formatted as five groups of five characters.

The Web App now validates the stored `license_key` against this same generator. This fixes the audit finding where a record with a correct hardware fingerprint and dates but a fake key could pass validation.

## Trial License

Trial licenses are valid for 30 days from `start_date`.

Requirements:

- `license_type = Trial` or `trial`
- `is_active = 1`
- matching hardware fingerprint
- generated license key matches
- `start_date <= today <= expiry_date`

## Annual License

Annual licenses are valid for 365 days from `start_date`.

Requirements:

- `license_type = Annual` or `annual`
- `is_active = 1`
- matching hardware fingerprint
- generated license key matches
- `start_date <= today <= expiry_date`

## Lifetime License

Lifetime licenses do not require an expiry date.

Requirements:

- `license_type = Lifetime` or `lifetime`
- `is_lifetime = 1` or license type is lifetime
- `is_active = 1`
- matching hardware fingerprint
- generated license key matches
- valid start date

## Missing License Behavior

If no valid license exists for the session company, the Web App middleware redirects protected paths to:

```text
/license-expired/
```

The page displays the current hardware fingerprint for renewal.

## Expired License Behavior

Expired Trial or Annual licenses are rejected. Protected pages redirect to `/license-expired/`.

## Invalid License Behavior

The following are rejected:

- unsupported license type
- inactive license
- hardware fingerprint mismatch
- missing or invalid start date
- missing expiry date for Trial/Annual
- expired Trial/Annual license
- license key mismatch

## Locked or Inactive License Behavior

`is_active = 0` is treated as locked/inactive and is rejected.

## Middleware Behavior

Middleware file:

```text
web_app/licensing/middleware.py
```

Allowed without a valid license:

- `/login/`
- `/logout/`
- `/license/`
- `/license-expired/`
- `/static/`
- requests before a company is selected in session

Blocked without a valid license:

- dashboard business data
- settings
- user management
- reports and exports
- print pages
- sales, purchases, receipts, payments, returns, expenses
- inventory
- backup and restore

The block applies to protected read and write routes because it is implemented at middleware path level.

## Login Behavior

Login is allowed without a valid license. After login, protected routes are checked once `company_id` is present in the session.

## Reports and Viewing Behavior

Reports and normal protected viewing pages are blocked without a valid license. The current policy does not allow read-only reports after license expiry.

## Backup and Restore Behavior

Backup and restore URLs live under `/system/`, which is not exempt. They are blocked without a valid license.

## License Failure Audit

License failures are logged through:

```text
core.audit_utils.log_license_failure()
```

The middleware logs action:

```text
LICENSE_FAILURE
```

Audit logging is best-effort and intentionally does not break the request if logging fails.

## Known Risks and Problems

1. The original Web App validation did not verify `license_key`. This has been fixed.
2. License enforcement is company-level. `branch_id` exists in `license_records` but is not enforced.
3. License keys do not currently include edition name, database path, or company id.
4. Hardware fingerprint uses hostname and MAC/node value; hardware or hostname changes may require license renewal.
5. Login remains allowed without a license by design, so users can reach the license-expired page and copy the fingerprint.

## Fixes Completed

1. Added shared Web App license utilities in `web_app/licensing/license_utils.py`.
2. Updated `web_app/licensing/middleware.py` to validate `license_key`.
3. Completed the `/license/` License Status / License Activation page.
4. Added safe management command:

```text
python manage.py test_licensing_system
```

The command creates temporary license scenarios inside a transaction and rolls them back.

5. Added focused license page test command:

```text
python manage.py test_license_page
```

## License Status / Activation Page

The Web App `/license/` page is now a real license management page instead of a placeholder.

It shows:

- current license status
- company and branch context
- current hardware fingerprint
- active license type, start date, expiry date, lifetime flag, days remaining, and validation message
- activation form for Trial, Annual, and Lifetime licenses
- license history table
- deactivate/reactivate actions
- DB App activation instructions

Activation workflow:

1. Login as Master Admin/Admin or a user with license/settings access.
2. Open `/license/`.
3. Copy the displayed hardware fingerprint.
4. Open DB App and select the target SQLite database file.
5. Generate Trial, Annual, or Lifetime license in the Licensing tab.
6. Paste the license key into `/license/`.
7. Activate.

If the DB App has already saved the license into the same database, click Refresh Status.

For MainVersion deployment, DB App must select:

```text
C:\VendorAccounts\MainVersion\data\vendor_accounts_main.db
```

The Web App reads the database from `VENDOR_ACCOUNTS_DB_PATH`, so DB App must save the license into that same file.

## Recommended Fixes Before Deployment

Recommended before first TAX deployment:

- Generate the license from the DB App on the deployment machine.
- Confirm `python manage.py test_licensing_system` passes on a writable copy or deployment database.
- Keep the live SQLite database outside OneDrive, Google Drive, or Dropbox sync folders.
- Record the hardware fingerprint and edition in client deployment notes.

Recommended later:

- Include edition name in the license key source for stricter two-edition enforcement.
- Consider branch-level enforcement only if the client sells per-branch licenses.

## Two-Edition Standalone Deployment Readiness

Planned deployment:

TAX version:

```text
Folder: C:\VendorAccounts\MainVersion\
Database: vendor_accounts_main.db
Port: 8000
Edition: Corporate Supplier Accounts System / Tax Edition
```

Local Vendor Accounting System:

```text
Folder: C:\VendorAccounts\LocalVersion\
Database: vendor_accounts_local.db
Port: 8001
Edition: Local Vendor Accounting System
Tax: disabled later with ENABLE_TAX=False
```

Findings:

- Both editions can run on the same PC/server if each app instance points to a separate SQLite database file and port.
- Each SQLite database has its own `license_records` table.
- The same hardware fingerprint can be used for both databases.
- The current license key does not include edition name, database name, or company id.
- Because license records are stored per database, the two editions will not conflict at storage level.
- Because the key does not include edition, a license generated for the same hardware, type, and start date could technically be reused between editions if copied into the other database.

Simple standalone policy:

- Use one SQLite database per edition.
- Generate and save one license record inside each database.
- Keep the hardware fingerprint the same.
- Track the edition manually in deployment notes until edition-aware keys are added.

## Test Command Result

The command was tested against a writable copy of the SQLite database:

```text
python manage.py test_license_page
python manage.py test_licensing_system
```

Result:

```text
test_license_page: PASS=5 FAIL=0
test_licensing_system: PASS=14 FAIL=0 WARNING=0
```

The default database in the current sandbox is read-only, so direct mutation tests against it fail safely with:

```text
FAIL: licensing test could not run: attempt to write a readonly database
```
