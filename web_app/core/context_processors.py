from datetime import date


def app_context(request):
    return {
        "system_name": "Corporate Supplier Accounts System",
        "app_version": "0.1.0",
        "current_year": date.today().year,
        "current_company_name": "Your Company Name",
    }
