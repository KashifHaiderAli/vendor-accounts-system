from django.urls import path

from . import views


app_name = "authentication"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("switch-branch/<int:branch_id>/", views.switch_branch_view, name="switch_branch"),
]
