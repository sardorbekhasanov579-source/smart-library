from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.CatalogHomeView.as_view(), name="home"),
    path("toifa/yangi/", views.CategoryCreateView.as_view(), name="category_create"),
    path("toifa/<int:pk>/", views.CategoryDetailView.as_view(), name="category_detail"),
    path("toifa/<int:pk>/tahrirlash/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("toifa/<int:pk>/ochirish/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("mualliflar/", views.AuthorListView.as_view(), name="author_list"),
    path("muallif/yangi/", views.AuthorCreateView.as_view(), name="author_create"),
    path("muallif/<int:pk>/", views.AuthorDetailView.as_view(), name="author_detail"),
    path("muallif/<int:pk>/tahrirlash/", views.AuthorUpdateView.as_view(), name="author_update"),
    path("muallif/<int:pk>/ochirish/", views.AuthorDeleteView.as_view(), name="author_delete"),
]
