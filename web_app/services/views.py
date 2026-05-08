from django.shortcuts import render

from authentication.decorators import permission_required_custom

@permission_required_custom("service_contracts", "view")
def index(request):
    return render(request, "placeholder.html", {"page_title": "Services"})
