from django.contrib import admin

from apps.quizzes.models import (
    Answer,
    Assignment,
    Attempt,
    Choice,
    OtpCode,
    Question,
    Quiz,
    TelegramAccount,
)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = ("order", "text", "explanation")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "book", "source", "questions_count", "pass_percent", "is_active")
    list_filter = ("source", "is_active")
    search_fields = ("title", "book__title")
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order")
    search_fields = ("text",)
    list_filter = ("quiz__book",)
    inlines = [ChoiceInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "reader", "quiz", "status", "best_percent", "pass_percent", "deadline", "sent_at",
    )
    list_filter = ("status",)
    search_fields = ("reader__full_name", "quiz__book__title", "token")
    readonly_fields = ("token",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("assignment", "percent", "correct_count", "total_questions", "passed",
                    "finished_at")
    list_filter = ("passed",)


@admin.register(TelegramAccount)
class TelegramAccountAdmin(admin.ModelAdmin):
    list_display = ("reader", "chat_id", "username", "phone", "is_verified", "created_at")
    search_fields = ("reader__full_name", "username", "phone", "chat_id")
    list_filter = ("is_verified",)


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ("phone", "code", "purpose", "is_used", "tries", "created_at", "expires_at")
    search_fields = ("phone",)
    list_filter = ("purpose", "is_used")


admin.site.register(Answer)
