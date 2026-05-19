from django.urls import path

from . import views


app_name = "settings_module"

urlpatterns = [
    path("company/", views.company_settings_view, name="company"),
    path("branches/", views.branches_list_view, name="branches"),
    path("branches/new/", views.branch_form_view, name="branch_new"),
    path("branches/<int:branch_id>/edit/", views.branch_form_view, name="branch_edit"),
    path("branches/<int:branch_id>/toggle-active/", views.branch_toggle_active_view, name="branch_toggle_active"),
    path("branches/<int:branch_id>/make-head-office/", views.branch_make_head_office_view, name="branch_make_head_office"),
    path("numbering/", views.numbering_settings_view, name="numbering"),
    path("tax/", views.tax_settings_view, name="tax"),
    path("inventory/", views.inventory_settings_view, name="inventory"),
]
