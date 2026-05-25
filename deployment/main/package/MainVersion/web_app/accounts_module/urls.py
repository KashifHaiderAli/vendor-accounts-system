from django.urls import path

from . import views


app_name = "accounts_module"

urlpatterns = [
    path("", views.index, name="index"),
    path("chart/", views.chart_of_accounts, name="chart"),
    path("journals/", views.journal_list, name="journals"),
    path("journals/<int:journal_id>/", views.journal_detail, name="journal_detail"),
    path("expenses/", views.expense_vouchers_list, name="expenses"),
    path("expenses/new/", views.expense_voucher_form, name="expense_new"),
    path("expenses/<int:voucher_id>/", views.expense_voucher_detail, name="expense_detail"),
    path("expenses/<int:voucher_id>/edit/", views.expense_voucher_form, name="expense_edit"),
    path("expenses/<int:voucher_id>/cancel/", views.cancel_expense_voucher, name="expense_cancel"),
    path("expenses/<int:voucher_id>/print/", views.print_expense_voucher, name="expense_print"),
]
