from django.urls import path

from . import views


app_name = "sales"

urlpatterns = [
    path("", views.index, name="index"),
    path("quotations/", views.quotations_list, name="quotations"),
    path("quotations/new/", views.quotation_form, name="quotation_new"),
    path("quotations/<int:quotation_id>/", views.quotation_detail, name="quotation_detail"),
    path("quotations/<int:quotation_id>/edit/", views.quotation_form, name="quotation_edit"),
    path("quotations/<int:quotation_id>/duplicate/", views.duplicate_quotation, name="quotation_duplicate"),
    path("quotations/<int:quotation_id>/add-as-customer/", views.add_as_customer, name="quotation_add_as_customer"),
    path("quotations/<int:quotation_id>/cancel/", views.cancel_quotation, name="quotation_cancel"),
    path("quotations/<int:quotation_id>/print/", views.print_quotation, name="quotation_print"),
    path("quotations/<int:quotation_id>/pdf/", views.pdf_quotation, name="quotation_pdf"),
    path("quotations/<int:quotation_id>/convert-to-confirmation/", views.convert_to_confirmation, name="quotation_convert"),
]
