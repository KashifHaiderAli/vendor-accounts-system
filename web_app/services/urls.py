from django.urls import path

from . import views


app_name = "services"

urlpatterns = [
    path("", views.index, name="index"),
    path("contracts/", views.contracts_list, name="contracts"),
    path("contracts/new/", views.contract_form, name="contract_new"),
    path("contracts/<int:contract_id>/", views.contract_detail, name="contract_detail"),
    path("contracts/<int:contract_id>/edit/", views.contract_form, name="contract_edit"),
    path("contracts/<int:contract_id>/close/", views.close_contract, name="contract_close"),
    path("contracts/<int:contract_id>/print/", views.print_contract, name="contract_print"),
    path("contracts/<int:contract_id>/generate-invoice/", views.generate_contract_invoice, name="contract_generate_invoice"),
]
