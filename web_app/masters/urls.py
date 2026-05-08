from django.urls import path

from . import views


app_name = "masters"

urlpatterns = [
    path("", views.index, name="index"),
]
