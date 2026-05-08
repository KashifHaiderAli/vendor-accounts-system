from django.shortcuts import render


def index(request):
    return render(request, "placeholder.html", {"page_title": "License Status"})


def expired(request):
    return render(request, "licensing/license_expired.html")
