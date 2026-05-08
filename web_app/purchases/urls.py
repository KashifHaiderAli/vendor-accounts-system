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
]
