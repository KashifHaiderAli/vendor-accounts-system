from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from core import views as core_views
from licensing import views as licensing_views


handler403 = "core.views.permission_denied_view"
handler404 = "core.views.page_not_found_view"

urlpatterns = [
    path("", core_views.dashboard, name="dashboard"),
    path("", include("authentication.urls")),
    path("masters/", include("masters.urls")),
    path("sales/", include("sales.urls")),
    path("purchases/", include("purchases.urls")),
    path("services/", include("services.urls")),
    path("accounts/", include("accounts_module.urls")),
    path("reports/", include("reports.urls")),
    path("backup/", include("backup.urls")),
    path("license-expired/", licensing_views.expired, name="license_expired"),
    path("license/", include("licensing.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
