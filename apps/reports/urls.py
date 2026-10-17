from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportHomeView.as_view(), name="home"),
    path("excel/", views.ExportExcelView.as_view(), name="excel"),
    path("pdf/", views.ExportPdfView.as_view(), name="pdf"),
]
