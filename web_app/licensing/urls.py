from django.urls import path

from . import views


app_name = "licensing"

urlpatterns = [
    path("", views.index, name="index"),
    path("expired/", views.expired, name="expired"),
]
