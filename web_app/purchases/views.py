from __future__ import annotations

from django.contrib import messages
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts_module.accounting_engine import AccountingError
from authentication.auth_utils import user_has_permission
from authentication.decorators import login_required_custom, permission_required_custom
from core import validators
from core.print_utils import build_print_context
from settings_module.services import log_user_activity

from . import payment_services, return_services, services


PURCHASE_CARDS = [
    ("Supplier Purchases", "supplier_purchases", "purchases:supplier_purchases", "bi-bag-check", "Record supplier bills and post purchase journals."),
    ("Purchase Returns", "purchase_returns", "purchases:returns", "bi-arrow-counterclockwise", "Record purchase returns and post debit note journals."),
    ("Supplier Payments", "supplier_payments", "purchases:supplier_payments", "bi-wallet2", "Record supplier payments and post payment journals."),
]


@login_required_custom
def index(request):
    cards = []
    for label, permission, url_name, icon, description in PURCHASE_CARDS:
        if user_has_permission(request, permission, "view"):
            cards.append({"label": label, "url_name": url_name, "icon": icon, "description": description})
    return render(request, "purchases/index.html", {"page_title": "Purchases", "purchase_cards": cards})


@permission_required_custom("supplier_purchases", "view")
def purchases_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = services.list_purchases(company_id, branch_id, search, status, date_from, date_to, page)
    return render(
        request,
        "purchases/supplier_purchases_list.html",
        {
            "page_title": "Supplier Purchases",
            "rows": rows,
            "search": search,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "statuses": services.PURCHASE_STATUSES,
            "can_add": user_has_permission(request, "supplier_purchases", "add"),
            "can_edit": user_has_permission(request, "supplier_purchases", "edit"),
            "can_cancel": can_cancel(request),
            "can_print": can_print(request),
            "can_payment": user_has_permission(request, "supplier_payments", "add"),
            "can_return": user_has_permission(request, "purchase_returns", "add"),
        },
    )


@login_required_custom
def purchase_form(request, purchase_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = purchase_id is not None
    if not user_has_permission(request, "supplier_purchases", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)

    purchase = services.get_purchase(company_id, branch_id, purchase_id) if is_edit else None
    if is_edit and not purchase:
        messages.error(request, "Supplier purchase was not found.")
        return redirect("purchases:supplier_purchases")
    if is_edit and purchase.get("status") == "Cancelled":
        messages.error(request, "Cancelled purchases cannot be edited.")
        return redirect("purchases:supplier_purchase_detail", purchase_id=purchase_id)

    posted = bool(purchase and purchase.get("journal_entry_id"))
    form_data = purchase_form_data(purchase) if is_edit else services.default_form_data(company_id, branch_id)
    errors = {}

    if request.method == "POST":
        if posted:
            form_data.update(
                {
                    "supplier_bill_no": request.POST.get("supplier_bill_no", ""),
                    "supplier_bill_date": request.POST.get("supplier_bill_date", ""),
                    "remarks": request.POST.get("remarks", ""),
                }
            )
            bill_no, errors["supplier_bill_no"] = validators.clean_text(form_data.get("supplier_bill_no"), max_length=100, field_name="Supplier Bill No")
            bill_date, errors["supplier_bill_date"] = validators.validate_date(form_data.get("supplier_bill_date"), "Supplier Bill Date", required=False)
            remarks, errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {key: value for key, value in errors.items() if value}
            if not errors:
                form_data["supplier_bill_no"] = bill_no
                form_data["supplier_bill_date"] = bill_date.isoformat() if bill_date else None
                form_data["remarks"] = remarks
                services.save_purchase(company_id, branch_id, request.session.get("user_id"), form_data, purchase_id)
                log_user_activity(request, "UPDATE", "Supplier Purchases", "supplier_purchases", purchase_id, f"Updated non-financial details for purchase {purchase['purchase_no']}.")
                messages.success(request, "Supplier purchase updated successfully.")
                return redirect("purchases:supplier_purchase_detail", purchase_id=purchase_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = services.parse_purchase_post(request.POST)
            errors, form_data = services.validate_and_calculate(form_data, company_id, branch_id, purchase_id)
            if not errors:
                try:
                    saved_id = services.save_purchase(company_id, branch_id, request.session.get("user_id"), form_data, purchase_id)
                    log_user_activity(
                        request,
                        "UPDATE" if is_edit else "CREATE",
                        "Supplier Purchases",
                        "supplier_purchases",
                        saved_id,
                        f"{'Updated' if is_edit else 'Created'} supplier purchase {form_data['purchase_no']}.",
                    )
                    messages.success(request, f"Supplier purchase {'updated' if is_edit else 'created'} successfully.")
                    return redirect("purchases:supplier_purchase_detail", purchase_id=saved_id)
                except ValueError as exc:
                    messages.error(request, str(exc))
                except ValueError as exc:
                    messages.error(request, str(exc))
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save supplier purchase. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "purchases/supplier_purchase_form.html",
        {
            "page_title": "Edit Supplier Purchase" if is_edit else "New Supplier Purchase",
            "form_data": form_data,
            "form_items": form_data.get("items", []),
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "posted": posted,
            "suppliers": services.get_suppliers(company_id, branch_id),
            "items": services.get_items(company_id, branch_id),
            "confirmations": services.get_confirmations(company_id, branch_id),
            "statuses": services.PURCHASE_STATUSES,
        },
    )


@permission_required_custom("supplier_purchases", "view")
def purchase_detail(request, purchase_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase = services.get_purchase(company_id, branch_id, purchase_id)
    if not purchase:
        messages.error(request, "Supplier purchase was not found.")
        return redirect("purchases:supplier_purchases")
    return render(
        request,
        "purchases/supplier_purchase_detail.html",
        {
            "page_title": purchase["purchase_no"],
            "purchase": purchase,
            "items": services.get_purchase_items(purchase_id),
            "can_edit": user_has_permission(request, "supplier_purchases", "edit") and purchase.get("status") != "Cancelled",
            "can_cancel": can_cancel(request) and purchase.get("status") != "Cancelled",
            "can_print": can_print(request),
            "can_payment": user_has_permission(request, "supplier_payments", "add") and purchase.get("status") not in {"Cancelled", "Paid"},
            "can_return": user_has_permission(request, "purchase_returns", "add") and purchase.get("status") != "Cancelled",
        },
    )


@login_required_custom
def cancel_purchase(request, purchase_id):
    if not can_cancel(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase = services.get_purchase(company_id, branch_id, purchase_id)
    if not purchase:
        messages.error(request, "Supplier purchase was not found.")
        return redirect("purchases:supplier_purchases")
    if request.method == "POST":
        try:
            services.cancel_purchase(request, purchase)
            messages.success(request, "Supplier purchase cancelled and reversal journal created successfully.")
            return redirect("purchases:supplier_purchase_detail", purchase_id=purchase_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel supplier purchase.")
            return redirect("purchases:supplier_purchase_detail", purchase_id=purchase_id)
    return render(request, "purchases/confirm_cancel_purchase.html", {"page_title": "Cancel Supplier Purchase", "purchase": purchase})


@login_required_custom
def print_purchase(request, purchase_id):
    if not can_print(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase = services.get_purchase(company_id, branch_id, purchase_id)
    if not purchase:
        messages.error(request, "Supplier purchase was not found.")
        return redirect("purchases:supplier_purchases")
    log_user_activity(request, "PRINT", "Supplier Purchases", "supplier_purchases", purchase_id, f"Printed supplier purchase {purchase['purchase_no']}.")
    context = services.get_print_context(company_id, branch_id, purchase_id)
    context.update(build_print_context(company_id, request, "Supplier Purchase"))
    return render(request, "purchases/supplier_purchase_print.html", context)


@permission_required_custom("supplier_payments", "view")
def supplier_payments_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    payment_mode = request.GET.get("payment_mode", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = payment_services.list_payments(company_id, branch_id, search, payment_mode, date_from, date_to, page)
    return render(
        request,
        "purchases/supplier_payments_list.html",
        {
            "page_title": "Supplier Payments",
            "rows": rows,
            "search": search,
            "payment_mode": payment_mode,
            "date_from": date_from,
            "date_to": date_to,
            "pagination": pagination,
            "payment_modes": payment_services.PAYMENT_MODES,
            "can_add": user_has_permission(request, "supplier_payments", "add"),
            "can_edit": user_has_permission(request, "supplier_payments", "edit"),
            "can_cancel": can_cancel_payment(request),
        },
    )


@login_required_custom
def supplier_payment_form(request, payment_id=None, purchase_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = payment_id is not None
    if not user_has_permission(request, "supplier_payments", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    payment = payment_services.get_payment(company_id, branch_id, payment_id) if is_edit else None
    if is_edit and not payment:
        messages.error(request, "Supplier payment was not found.")
        return redirect("purchases:supplier_payments")
    if is_edit and payment.get("reversal_id"):
        messages.error(request, "Cancelled supplier payments cannot be edited.")
        return redirect("purchases:supplier_payment_detail", payment_id=payment_id)
    source_purchase = payment_services.get_purchase(company_id, branch_id, purchase_id) if purchase_id else None
    if purchase_id and not source_purchase:
        messages.error(request, "Supplier purchase was not found or has no payable balance.")
        return redirect("purchases:supplier_purchases")

    posted = bool(payment and payment.get("journal_entry_id"))
    form_data = supplier_payment_form_data(payment) if is_edit else payment_services.default_form_data(company_id, branch_id, source_purchase)
    errors = {}
    if request.method == "POST":
        if posted:
            form_data.update({"cheque_reference_no": request.POST.get("cheque_reference_no", ""), "remarks": request.POST.get("remarks", "")})
            form_data["cheque_reference_no"], errors["cheque_reference_no"] = validators.clean_text(form_data.get("cheque_reference_no"), max_length=100, field_name="Reference No")
            form_data["remarks"], errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {key: value for key, value in errors.items() if value}
            if not errors:
                payment_services.save_payment(company_id, branch_id, request.session.get("user_id"), form_data, payment_id)
                log_user_activity(request, "UPDATE", "Supplier Payments", "supplier_payments", payment_id, f"Updated non-financial details for supplier payment {payment['payment_no']}.")
                messages.success(request, "Supplier payment updated successfully.")
                return redirect("purchases:supplier_payment_detail", payment_id=payment_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = payment_services.parse_post(request.POST)
            errors, form_data = payment_services.validate_and_clean(form_data, company_id, branch_id, payment_id)
            if not errors:
                try:
                    saved_id = payment_services.save_payment(company_id, branch_id, request.session.get("user_id"), form_data, payment_id)
                    log_user_activity(request, "CREATE" if not is_edit else "UPDATE", "Supplier Payments", "supplier_payments", saved_id, f"{'Created' if not is_edit else 'Updated'} supplier payment {form_data['payment_no']}.")
                    messages.success(request, f"Supplier payment {'created' if not is_edit else 'updated'} successfully.")
                    return redirect("purchases:supplier_payment_detail", payment_id=saved_id)
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save supplier payment. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")

    return render(
        request,
        "purchases/supplier_payment_form.html",
        {
            "page_title": "Edit Supplier Payment" if is_edit else "New Supplier Payment",
            "form_data": form_data,
            "errors": errors,
            "error_summary": collect_errors(errors),
            "is_edit": is_edit,
            "posted": posted,
            "suppliers": payment_services.get_suppliers(company_id, branch_id),
            "cash_bank_accounts": payment_services.get_cash_bank_accounts(company_id, branch_id),
            "open_purchases": payment_services.get_open_purchases(company_id, branch_id, form_data.get("supplier_id") or None),
            "payment_modes": payment_services.PAYMENT_MODES,
        },
    )


@permission_required_custom("supplier_payments", "view")
def supplier_payment_detail(request, payment_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    payment = payment_services.get_payment(company_id, branch_id, payment_id)
    if not payment:
        messages.error(request, "Supplier payment was not found.")
        return redirect("purchases:supplier_payments")
    return render(
        request,
        "purchases/supplier_payment_detail.html",
        {
            "page_title": payment["payment_no"],
            "payment": payment,
            "can_edit": user_has_permission(request, "supplier_payments", "edit") and not payment.get("reversal_id"),
            "can_cancel": can_cancel_payment(request) and not payment.get("reversal_id"),
        },
    )


@login_required_custom
def cancel_supplier_payment(request, payment_id):
    if not can_cancel_payment(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    payment = payment_services.get_payment(company_id, branch_id, payment_id)
    if not payment:
        messages.error(request, "Supplier payment was not found.")
        return redirect("purchases:supplier_payments")
    if request.method == "POST":
        try:
            payment_services.cancel_payment(request, payment)
            messages.success(request, "Supplier payment reversed successfully. The historical payment record remains visible.")
            return redirect("purchases:supplier_payment_detail", payment_id=payment_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to reverse supplier payment.")
            return redirect("purchases:supplier_payment_detail", payment_id=payment_id)
    return render(request, "purchases/confirm_cancel_supplier_payment.html", {"page_title": "Reverse Supplier Payment", "payment": payment})


@permission_required_custom("supplier_payments", "view")
def print_supplier_payment(request, payment_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    payment = payment_services.get_payment(company_id, branch_id, payment_id)
    if not payment:
        messages.error(request, "Supplier payment was not found.")
        return redirect("purchases:supplier_payments")
    payment_services.mark_printed(request, payment)
    context = payment_services.get_print_context(company_id, branch_id, payment_id)
    context.update(build_print_context(company_id, request, "Supplier Payment Voucher"))
    return render(request, "purchases/supplier_payment_print.html", context)


@permission_required_custom("purchase_returns", "view")
def purchase_returns_list(request):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    rows, pagination = return_services.list_returns(company_id, branch_id, search, status, date_from, date_to, page)
    return render(request, "purchases/purchase_returns_list.html", {"page_title": "Purchase Returns", "rows": rows, "search": search, "status": status, "date_from": date_from, "date_to": date_to, "pagination": pagination, "statuses": return_services.RETURN_STATUSES, "can_add": user_has_permission(request, "purchase_returns", "add"), "can_edit": user_has_permission(request, "purchase_returns", "edit"), "can_cancel": can_cancel_purchase_return(request)})


@login_required_custom
def purchase_return_form(request, return_id=None, purchase_id=None):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    is_edit = return_id is not None
    if not user_has_permission(request, "purchase_returns", "edit" if is_edit else "add"):
        return render(request, "errors/403.html", status=403)
    purchase_return = return_services.get_return(company_id, branch_id, return_id) if is_edit else None
    if is_edit and not purchase_return:
        messages.error(request, "Purchase return was not found.")
        return redirect("purchases:returns")
    if is_edit and purchase_return.get("status") == "Cancelled":
        messages.error(request, "Cancelled purchase returns cannot be edited.")
        return redirect("purchases:return_detail", return_id=return_id)
    source_purchase = return_services.get_purchase(company_id, branch_id, purchase_id) if purchase_id else None
    if purchase_id and not source_purchase:
        messages.error(request, "Supplier purchase was not found.")
        return redirect("purchases:supplier_purchases")
    posted = bool(purchase_return and purchase_return.get("journal_entry_id"))
    form_data = purchase_return_form_data(purchase_return) if is_edit else return_services.default_form_data(company_id, branch_id, source_purchase)
    errors = {}
    if request.method == "POST":
        if posted:
            form_data.update({"return_reason": request.POST.get("return_reason", ""), "remarks": request.POST.get("remarks", "")})
            form_data["return_reason"], errors["return_reason"] = validators.clean_text(form_data.get("return_reason"), field_name="Return Reason")
            form_data["remarks"], errors["remarks"] = validators.clean_text(form_data.get("remarks"), field_name="Remarks")
            errors = {key: value for key, value in errors.items() if value}
            if not errors:
                return_services.save_return(company_id, branch_id, request.session.get("user_id"), form_data, return_id)
                log_user_activity(request, "UPDATE", "Purchase Returns", "purchase_returns", return_id, f"Updated non-financial details for purchase return {purchase_return['purchase_return_no']}.")
                messages.success(request, "Purchase return updated successfully.")
                return redirect("purchases:return_detail", return_id=return_id)
            messages.error(request, "Please correct the highlighted errors.")
        else:
            form_data = return_services.parse_post(request.POST)
            errors, form_data = return_services.validate_and_calculate(form_data, company_id, branch_id, return_id)
            if not errors:
                try:
                    saved_id = return_services.save_return(company_id, branch_id, request.session.get("user_id"), form_data, return_id)
                    log_user_activity(request, "CREATE", "Purchase Returns", "purchase_returns", saved_id, f"Created purchase return {form_data['purchase_return_no']}.")
                    messages.success(request, "Purchase return created and posted successfully.")
                    return redirect("purchases:return_detail", return_id=saved_id)
                except AccountingError as exc:
                    messages.error(request, f"Accounting posting failed: {exc}")
                except DatabaseError:
                    messages.error(request, "Unable to save purchase return. Please retry.")
            else:
                messages.error(request, "Please correct the highlighted errors.")
    return render(request, "purchases/purchase_return_form.html", {"page_title": "Edit Purchase Return" if is_edit else "New Purchase Return", "form_data": form_data, "form_items": form_data.get("items", []), "errors": errors, "error_summary": collect_errors(errors), "is_edit": is_edit, "posted": posted, "suppliers": return_services.get_suppliers(company_id, branch_id), "purchases": return_services.get_purchases(company_id, branch_id, form_data.get("supplier_id") or None), "items": return_services.get_items(company_id, branch_id)})


@login_required_custom
def purchase_return_purchase_items(request, purchase_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return JsonResponse({"ok": False, "error": "Company or branch session is missing."}, status=403)
    if not user_has_permission(request, "purchase_returns", "add"):
        return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)
    purchase = return_services.get_purchase(company_id, branch_id, purchase_id)
    if not purchase:
        return JsonResponse({"ok": False, "error": "Supplier purchase was not found."}, status=404)
    data = return_services.default_form_data(company_id, branch_id, purchase)
    return JsonResponse({
        "ok": True,
        "supplier_id": purchase.get("supplier_id") or "",
        "supplier_bill_no": purchase.get("supplier_bill_no") or "",
        "items": [
            {
                "item_service_id": row.get("item_service_id") or "",
                "supplier_purchase_item_id": row.get("supplier_purchase_item_id") or "",
                "description": row.get("description") or "",
                "quantity": str(row.get("quantity") or "0"),
                "max_quantity": str(row.get("max_quantity") or row.get("quantity") or "0"),
                "purchase_rate": str(row.get("purchase_rate") or "0"),
                "tax_percent": str(row.get("tax_percent") or "0"),
            }
            for row in data.get("items", [])
            if row.get("supplier_purchase_item_id")
        ],
    })


@permission_required_custom("purchase_returns", "view")
def purchase_return_detail(request, return_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase_return = return_services.get_return(company_id, branch_id, return_id)
    if not purchase_return:
        messages.error(request, "Purchase return was not found.")
        return redirect("purchases:returns")
    return render(request, "purchases/purchase_return_detail.html", {"page_title": purchase_return["purchase_return_no"], "purchase_return": purchase_return, "items": return_services.get_return_items(return_id), "can_edit": user_has_permission(request, "purchase_returns", "edit") and purchase_return.get("status") != "Cancelled", "can_cancel": can_cancel_purchase_return(request) and purchase_return.get("status") != "Cancelled"})


@login_required_custom
def cancel_purchase_return(request, return_id):
    if not can_cancel_purchase_return(request):
        return render(request, "errors/403.html", status=403)
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase_return = return_services.get_return(company_id, branch_id, return_id)
    if not purchase_return:
        messages.error(request, "Purchase return was not found.")
        return redirect("purchases:returns")
    if request.method == "POST":
        try:
            return_services.cancel_return(request, purchase_return)
            messages.success(request, "Purchase return cancelled and reversal journal created successfully.")
            return redirect("purchases:return_detail", return_id=return_id)
        except (AccountingError, DatabaseError, ValueError) as exc:
            messages.error(request, str(exc) or "Unable to cancel purchase return.")
            return redirect("purchases:return_detail", return_id=return_id)
    return render(request, "purchases/confirm_cancel_purchase_return.html", {"page_title": "Cancel Purchase Return", "purchase_return": purchase_return})


@permission_required_custom("purchase_returns", "view")
def print_purchase_return(request, return_id):
    company_id, branch_id = require_scope(request)
    if not company_id:
        return redirect("authentication:login")
    purchase_return = return_services.get_return(company_id, branch_id, return_id)
    if not purchase_return:
        messages.error(request, "Purchase return was not found.")
        return redirect("purchases:returns")
    return_services.mark_printed(request, purchase_return)
    context = return_services.get_print_context(company_id, branch_id, return_id)
    context.update(build_print_context(company_id, request, "Debit Note / Purchase Return"))
    return render(request, "purchases/purchase_return_print.html", context)


def require_scope(request):
    company_id, branch_id = services.get_scope(request)
    if not company_id or not branch_id:
        messages.error(request, "Company or branch session is missing. Please login again.")
        return None, None
    return company_id, branch_id


def can_cancel(request):
    return user_has_permission(request, "supplier_purchases", "delete") or user_has_permission(request, "supplier_purchases", "edit")


def can_print(request):
    return user_has_permission(request, "supplier_purchases", "print") or user_has_permission(request, "supplier_purchases", "view")


def can_cancel_payment(request):
    return user_has_permission(request, "supplier_payments", "delete") or user_has_permission(request, "supplier_payments", "edit")


def can_cancel_purchase_return(request):
    return user_has_permission(request, "purchase_returns", "delete") or user_has_permission(request, "purchase_returns", "edit")


def purchase_form_data(purchase):
    data = dict(purchase)
    for key in ["supplier_bill_no", "supplier_bill_date", "confirmation_id", "remarks"]:
        data[key] = data.get(key) or ""
    data["items"] = [
        {
            "item_service_id": item.get("item_service_id") or "",
            "description": item.get("description") or "",
            "quantity": item.get("quantity") or "0",
            "purchase_rate": item.get("purchase_rate") or "0",
            "tax_percent": item.get("tax_percent") or "0",
            "tax_amount": item.get("tax_amount") or "0",
            "line_total": item.get("line_total") or "0",
            "errors": {},
        }
        for item in services.get_purchase_items(purchase["id"])
    ]
    return data


def supplier_payment_form_data(payment):
    return {
        "payment_no": payment.get("payment_no") or "",
        "payment_date": payment.get("payment_date") or "",
        "supplier_id": payment.get("supplier_id") or "",
        "payment_mode": payment.get("payment_mode") or "Cash",
        "cash_bank_account_id": payment.get("cash_bank_account_id") or "",
        "cheque_reference_no": payment.get("cheque_reference_no") or "",
        "amount": payment.get("amount") or "0.00",
        "adjusted_purchase_id": payment.get("adjusted_purchase_id") or "",
        "remarks": payment.get("remarks") or "",
    }


def purchase_return_form_data(purchase_return):
    data = dict(purchase_return)
    for key in ["return_reason", "remarks", "supplier_bill_no"]:
        data[key] = data.get(key) or ""
    data["items"] = [
        {"item_service_id": item.get("item_service_id") or "", "supplier_purchase_item_id": item.get("supplier_purchase_item_id") or "", "description": item.get("description") or "", "quantity": item.get("quantity") or "0", "purchase_rate": item.get("purchase_rate") or "0", "tax_percent": item.get("tax_percent") or "0", "tax_amount": item.get("tax_amount") or "0", "line_total": item.get("line_total") or "0", "errors": {}}
        for item in return_services.get_return_items(purchase_return["id"])
    ]
    return data


def collect_errors(errors):
    summary = []
    for key, value in errors.items():
        if key == "items":
            summary.append(value)
        elif value:
            summary.append(str(value))
    return summary
