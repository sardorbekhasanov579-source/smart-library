from django.urls import path

from apps.activity import views

app_name = "activity"

urlpatterns = [
    path("", views.LeaderboardView.as_view(), name="leaderboard"),
    path("eksport/", views.ExportView.as_view(), name="export"),
    path("hisoblash/", views.RecalcView.as_view(), name="recalc"),
    path("ball-qoshish/", views.ManualAwardView.as_view(), name="award"),
    path("yozuv/<int:pk>/ochirish/", views.DeleteRecordView.as_view(), name="delete_record"),
    path("<int:pk>/", views.ReaderActivityView.as_view(), name="reader"),
]
