from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.index, name="index"),
    path("stock-balance/", views.stock_balance, name="stock_balance"),
    path("item-ledger/", views.item_ledger_view, name="item_ledger"),
    path("stock-in/", views.stock_in, name="stock_in"),
    path("stock-out/", views.stock_out, name="stock_out"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("valuation/", views.valuation, name="valuation"),
    path("adjustments/", views.adjustments, name="adjustments"),
    path("adjustments/new/", views.adjustment_form, name="adjustment_new"),
    path("adjustments/<int:adjustment_id>/", views.adjustment_detail, name="adjustment_detail"),
    path("adjustments/<int:adjustment_id>/cancel/", views.cancel_adjustment, name="adjustment_cancel"),
    path("adjustments/<int:adjustment_id>/print/", views.print_adjustment, name="adjustment_print"),
]
