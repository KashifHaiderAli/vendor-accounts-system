from django.urls import path

from . import views


app_name = "purchases"

urlpatterns = [
    path("", views.index, name="index"),
    path("supplier-purchases/", views.purchases_list, name="supplier_purchases"),
    path("supplier-purchases/new/", views.purchase_form, name="supplier_purchase_new"),
    path("supplier-purchases/<int:purchase_id>/", views.purchase_detail, name="supplier_purchase_detail"),
    path("supplier-purchases/<int:purchase_id>/edit/", views.purchase_form, name="supplier_purchase_edit"),
    path("supplier-purchases/<int:purchase_id>/cancel/", views.cancel_purchase, name="supplier_purchase_cancel"),
    path("supplier-purchases/<int:purchase_id>/print/", views.print_purchase, name="supplier_purchase_print"),
    path("supplier-payments/", views.supplier_payments_list, name="supplier_payments"),
    path("supplier-payments/new/", views.supplier_payment_form, name="supplier_payment_new"),
    path("supplier-payments/from-purchase/<int:purchase_id>/", views.supplier_payment_form, name="supplier_payment_from_purchase"),
    path("supplier-payments/<int:payment_id>/", views.supplier_payment_detail, name="supplier_payment_detail"),
    path("supplier-payments/<int:payment_id>/edit/", views.supplier_payment_form, name="supplier_payment_edit"),
    path("supplier-payments/<int:payment_id>/cancel/", views.cancel_supplier_payment, name="supplier_payment_cancel"),
    path("supplier-payments/<int:payment_id>/print/", views.print_supplier_payment, name="supplier_payment_print"),
]
