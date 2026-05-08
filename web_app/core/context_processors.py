from datetime import date


def app_context(request):
    today = date.today()
    return {
        "system_name": "Corporate Supplier Accounts System",
        "app_version": "0.1.0",
        "current_year": today.year,
        "current_date": today,
        "current_company_name": "Your Company Name",
        "current_branch_name": "Main Branch",
    }
