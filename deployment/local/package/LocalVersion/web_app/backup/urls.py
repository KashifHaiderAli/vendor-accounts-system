from django.urls import path

from . import views


app_name = "backup"

urlpatterns = [
    path("", views.backup_dashboard, name="index"),
    path("backup/", views.backup_dashboard, name="dashboard"),
    path("backup/now/", views.backup_now, name="backup_now"),
    path("backup/history/", views.backup_history, name="history"),
    path("backup/settings/", views.backup_settings, name="settings"),
    path("backup/download/", views.download_backup, name="download"),
    path("backup/verify/", views.verify_backup, name="verify"),
    path("restore/", views.restore_backup, name="restore"),
    path("restore/preview/", views.restore_preview, name="restore_preview"),
    path("restore/confirm/", views.restore_confirm, name="restore_confirm"),
    path("audit-log/", views.audit_log, name="audit_log"),
    path("audit-log/<int:log_id>/", views.audit_log_detail, name="audit_log_detail"),
]
