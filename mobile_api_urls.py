from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView, MeView, BookListView, BookDetailView, MyLoansView,
    MyActivityView, LeaderboardView, MyAssignmentsView,
    StartAttemptView, SubmitAttemptView,
)

app_name = "mobile_api"
urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("me/loans/", MyLoansView.as_view(), name="my_loans"),
    path("me/social-activity/", MyActivityView.as_view(), name="my_activity"),
    path("social-activity/leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("books/", BookListView.as_view(), name="books"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book_detail"),
    path("tests/assignments/", MyAssignmentsView.as_view(), name="assignments"),
    path("tests/assignments/<int:assignment_id>/start/", StartAttemptView.as_view(), name="start_attempt"),
    path("tests/attempts/<int:attempt_id>/submit/", SubmitAttemptView.as_view(), name="submit_attempt"),
]
