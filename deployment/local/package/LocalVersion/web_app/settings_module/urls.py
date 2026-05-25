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
    path("users-roles/", views.users_roles_placeholder_view, name="users_roles"),
    path("users-roles/new/", views.user_form_view, name="user_new"),
    path("users-roles/<int:user_id>/edit/", views.user_form_view, name="user_edit"),
    path("users-roles/<int:user_id>/toggle-active/", views.user_toggle_active_view, name="user_toggle_active"),
    path("users-roles/<int:user_id>/reset-password/", views.reset_user_password_view, name="user_reset_password"),
    path("role-management/", views.role_management_placeholder_view, name="role_management"),
    path("role-management/new/", views.role_form_view, name="role_new"),
    path("role-management/<int:role_id>/edit/", views.role_form_view, name="role_edit"),
    path("role-management/<int:role_id>/toggle-active/", views.role_toggle_active_view, name="role_toggle_active"),
    path("role-management/<int:role_id>/permissions/", views.role_permissions_view, name="role_permissions"),
    path("numbering/", views.numbering_settings_view, name="numbering"),
    path("tax/", views.tax_settings_view, name="tax"),
    path("inventory/", views.inventory_settings_view, name="inventory"),
]
