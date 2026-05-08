from django.shortcuts import render


def index(request):
    return render(request, "placeholder.html", {"page_title": "Purchases"})
