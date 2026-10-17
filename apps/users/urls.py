from django.urls import path

from apps.users import views

app_name = "users"

urlpatterns = [
    path("kirish/", views.LoginView.as_view(), name="login"),
    path("chiqish/", views.LogoutView.as_view(), name="logout"),
    path("", views.UserListView.as_view(), name="list"),
    path("yangi/", views.UserCreateView.as_view(), name="create"),
    path("<int:pk>/tahrirlash/", views.UserUpdateView.as_view(), name="update"),
    path("<int:pk>/ochirish/", views.UserDeleteView.as_view(), name="delete"),
    path("<int:pk>/holat/", views.UserToggleStatusView.as_view(), name="toggle_status"),
    path("profil/", views.ProfileView.as_view(), name="profile"),
    path("parol/", views.PasswordChangeView.as_view(), name="password_change"),
]
