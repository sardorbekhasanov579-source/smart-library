from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("qidiruv/", views.GlobalSearchView.as_view(), name="search"),
    path("sozlamalar/", views.SettingsView.as_view(), name="settings"),
    path("jurnal/", views.AuditLogView.as_view(), name="audit_log"),
]
