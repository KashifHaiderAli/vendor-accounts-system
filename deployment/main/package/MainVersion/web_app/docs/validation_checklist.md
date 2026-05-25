# Phase 6.6 Validation Checklist

Use these manual checks after starting the web app and logging in.

## Contact Fields

- Enter `phone123` in any phone field and submit. The form should stay open and show a phone validation error.
- Enter `0300@test` in a phone or mobile field and submit. The form should block saving.
- Enter `123` in a mobile field and submit. The form should block saving because mobile needs at least 10 digits.
- Enter `+92 300 1234567` in a mobile field and submit. The value should pass validation.

## Email and Website Fields

- Enter `not-an-email` in an email field and submit. The form should block saving.
- Enter `info@example.com` in an email field and submit. The value should pass validation.
- Enter `example dot com` in the company website field and submit. The form should block saving.
- Enter `example.com` or `https://example.com` in the website field and submit. The value should pass validation.

## Numeric Fields

- Enter a negative value in credit limit, opening balance, purchase rate, sale rate, or cash/bank opening balance. The form should block saving.
- Enter alphabetic text in a money field by bypassing browser validation and submitting. Backend validation should still block saving.
- Enter `101` in a tax percentage field. The form should block saving.
- Enter `-1` in a tax percentage field. The form should block saving.
- Enter `1.5` in payment term days. The form should block saving.
- Enter `-1` in payment term days. The form should block saving.

## Required and Duplicate Fields

- Submit a blank required code/name field. The form should show a required-field error.
- Create or edit a customer using an existing customer code in the same branch. The form should block saving.
- Create or edit a supplier using an existing supplier code in the same branch. The form should block saving.
- Create or edit an item, expense head, cash/bank account, or payment term using a duplicate unique value. The form should block saving.

## Form Behavior

- After any validation failure, previously submitted values should remain visible.
- Field-level errors should appear near the relevant input where practical.
- The error summary should appear near the top of the form.
- No database schema changes or migrations should be required.
