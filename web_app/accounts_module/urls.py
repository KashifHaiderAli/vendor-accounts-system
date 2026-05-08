from django.urls import path

from . import views


app_name = "accounts_module"

urlpatterns = [
    path("", views.index, name="index"),
    path("chart/", views.chart_of_accounts, name="chart"),
    path("journals/", views.journal_list, name="journals"),
    path("journals/<int:journal_id>/", views.journal_detail, name="journal_detail"),
]
