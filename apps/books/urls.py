from django.urls import path

from apps.books import views

app_name = "books"

urlpatterns = [
    path("", views.BookListView.as_view(), name="list"),
    path("yangi/", views.BookCreateView.as_view(), name="create"),
    path("<int:pk>/", views.BookDetailView.as_view(), name="detail"),
    path("<int:pk>/tahrirlash/", views.BookUpdateView.as_view(), name="update"),
    path("<int:pk>/ochirish/", views.BookDeleteView.as_view(), name="delete"),
    path("<int:pk>/nusxa-qoshish/", views.BookCopyCreateView.as_view(), name="copy_create"),
    path("<int:pk>/nusxa-koplab/", views.BookCopyBulkCreateView.as_view(), name="copy_bulk"),
    path("nusxa/<int:pk>/tahrirlash/", views.BookCopyUpdateView.as_view(), name="copy_update"),
    path("nusxa/<int:pk>/ochirish/", views.BookCopyDeleteView.as_view(), name="copy_delete"),
]
