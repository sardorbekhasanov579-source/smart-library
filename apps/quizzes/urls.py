from django.urls import path

from apps.quizzes import views, webhooks

app_name = "quizzes"

urlpatterns = [
    # --- Kutubxonachi / admin -------------------------------------------------
    path("", views.QuizListView.as_view(), name="quiz_list"),
    path("yaratish/", views.QuizGenerateView.as_view(), name="quiz_generate"),
    path("<int:pk>/", views.QuizDetailView.as_view(), name="quiz_detail"),
    path("<int:pk>/ochirish/", views.QuizDeleteView.as_view(), name="quiz_delete"),
    path("savol/<int:pk>/tahrirlash/", views.QuestionEditView.as_view(), name="question_edit"),
    path("savol/<int:pk>/ochirish/", views.QuestionDeleteView.as_view(), name="question_delete"),

    path("topshiriqlar/", views.AssignmentListView.as_view(), name="assignment_list"),
    path("topshiriqlar/yangi/", views.AssignmentCreateView.as_view(), name="assignment_create"),
    path("topshiriqlar/<int:pk>/", views.AssignmentDetailView.as_view(), name="assignment_detail"),
    path(
        "topshiriqlar/<int:pk>/yuborish/",
        views.AssignmentSendView.as_view(),
        name="assignment_send",
    ),
    path("urinish/<int:pk>/", views.AttemptDetailView.as_view(), name="attempt_detail"),
    path("telegram/", views.TelegramPanelView.as_view(), name="telegram_panel"),
    path("holat/<int:book_id>/", views.BookQuizStatusView.as_view(), name="book_quiz_status"),

    # --- Kitobxon -------------------------------------------------------------
    path("kirish/", views.ReaderLoginView.as_view(), name="login"),
    path("chiqish/", views.ReaderLogoutView.as_view(), name="logout"),
    # Kitobxon ilovasining 4 bo'limi
    path("kabinet/", views.ReaderPortalView.as_view(), name="portal"),
    path("kabinet/kitoblar/", views.ReaderBooksView.as_view(), name="reader_books"),
    path("kabinet/testlar/", views.ReaderQuizzesView.as_view(), name="reader_quizzes"),
    path(
        "kabinet/sozlamalar/",
        views.ReaderSettingsView.as_view(),
        name="reader_settings",
    ),
    path("t/<str:token>/", views.TakeQuizView.as_view(), name="take"),
    path("t/<str:token>/natija/", views.QuizResultView.as_view(), name="result"),

    # --- Tashqi xizmatlar (login talab qilmaydi, maxfiy kalit bilan) ----------
    path(
        "telegram/webhook/<str:secret>/",
        webhooks.TelegramWebhookView.as_view(),
        name="telegram_webhook",
    ),
    path("cron/<str:secret>/", webhooks.CronRunView.as_view(), name="cron_run"),
]
