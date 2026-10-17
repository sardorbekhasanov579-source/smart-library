from django.urls import path

from apps.loans import views

app_name = "loans"

urlpatterns = [
    path("", views.LoanListView.as_view(), name="list"),
    path("berish/", views.IssueBookView.as_view(), name="issue"),
    path("qaytarish/", views.ReturnBookView.as_view(), name="return"),
    path("muddati-otgan/", views.OverdueListView.as_view(), name="overdue"),
    path("nusxa-qidirish/", views.CopyLookupView.as_view(), name="copy_lookup"),
    path("<int:pk>/", views.LoanDetailView.as_view(), name="detail"),
    path("<int:pk>/uzaytirish/", views.ExtendLoanView.as_view(), name="extend"),
]
