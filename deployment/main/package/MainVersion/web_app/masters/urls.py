from django.urls import path

from . import views


app_name = "masters"

urlpatterns = [
    path("", views.index, name="index"),
    path("customers/", views.customers, name="customers"),
    path("customers/new/", views.customer_form, name="customer_new"),
    path("customers/<int:record_id>/edit/", views.customer_form, name="customer_edit"),
    path("customers/<int:record_id>/toggle-active/", views.customer_toggle, name="customer_toggle"),
    path("suppliers/", views.suppliers, name="suppliers"),
    path("suppliers/new/", views.supplier_form, name="supplier_new"),
    path("suppliers/<int:record_id>/edit/", views.supplier_form, name="supplier_edit"),
    path("suppliers/<int:record_id>/toggle-active/", views.supplier_toggle, name="supplier_toggle"),
    path("items/", views.items, name="items"),
    path("items/new/", views.item_form, name="item_new"),
    path("items/<int:record_id>/edit/", views.item_form, name="item_edit"),
    path("items/<int:record_id>/toggle-active/", views.item_toggle, name="item_toggle"),
    path("cash-bank/", views.cash_bank, name="cash_bank"),
    path("cash-bank/new/", views.cash_bank_form, name="cash_bank_new"),
    path("cash-bank/<int:record_id>/edit/", views.cash_bank_form, name="cash_bank_edit"),
    path("cash-bank/<int:record_id>/toggle-active/", views.cash_bank_toggle, name="cash_bank_toggle"),
    path("expense-heads/", views.expense_heads, name="expense_heads"),
    path("expense-heads/new/", views.expense_head_form, name="expense_head_new"),
    path("expense-heads/<int:record_id>/edit/", views.expense_head_form, name="expense_head_edit"),
    path("expense-heads/<int:record_id>/toggle-active/", views.expense_head_toggle, name="expense_head_toggle"),
    path("payment-terms/", views.payment_terms, name="payment_terms"),
    path("payment-terms/new/", views.payment_term_form, name="payment_term_new"),
    path("payment-terms/<int:record_id>/edit/", views.payment_term_form, name="payment_term_edit"),
    path("payment-terms/<int:record_id>/toggle-active/", views.payment_term_toggle, name="payment_term_toggle"),
]
