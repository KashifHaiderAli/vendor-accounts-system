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
    path("returns/", views.purchase_returns_list, name="returns"),
    path("returns/new/", views.purchase_return_form, name="return_new"),
    path("returns/from-purchase/<int:purchase_id>/", views.purchase_return_form, name="return_from_purchase"),
    path("returns/supplier/<int:supplier_id>/purchases/", views.purchase_return_supplier_purchases, name="return_supplier_purchases"),
    path("returns/purchase/<int:purchase_id>/items/", views.purchase_return_purchase_items, name="return_purchase_items_detail"),
    path("returns/purchase-items/<int:purchase_id>/", views.purchase_return_purchase_items, name="return_purchase_items"),
    path("returns/<int:return_id>/", views.purchase_return_detail, name="return_detail"),
    path("returns/<int:return_id>/edit/", views.purchase_return_form, name="return_edit"),
    path("returns/<int:return_id>/cancel/", views.cancel_purchase_return, name="return_cancel"),
    path("returns/<int:return_id>/print/", views.print_purchase_return, name="return_print"),
]
