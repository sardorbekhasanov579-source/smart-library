
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import api_status, book_list, profile

app_name = "mobile_api"

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("status/", api_status, name="status"),
    path("profile/", profile, name="profile"),
    path("books/", book_list, name="books"),
]
