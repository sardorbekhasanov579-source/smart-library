from django.urls import path

from apps.readers import views

app_name = "readers"

urlpatterns = [
    path("", views.ReaderListView.as_view(), name="list"),
    path("yangi/", views.ReaderCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ReaderDetailView.as_view(), name="detail"),
    path("<int:pk>/tahrirlash/", views.ReaderUpdateView.as_view(), name="update"),
    path("<int:pk>/ochirish/", views.ReaderDeleteView.as_view(), name="delete"),
    path("<int:pk>/holat/", views.ReaderToggleStatusView.as_view(), name="toggle_status"),
]
