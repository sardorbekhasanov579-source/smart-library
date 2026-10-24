from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("foydalanuvchilar/", include("apps.users.urls")),
    path("katalog/", include("apps.catalog.urls")),
    path("kitoblar/", include("apps.books.urls")),
    path("kitobxonlar/", include("apps.readers.urls")),
    path("operatsiyalar/", include("apps.loans.urls")),
    path("hisobotlar/", include("apps.reports.urls")),
    path("testlar/", include("apps.quizzes.urls")),
    path("faollik/", include("apps.activity.urls")),

    # --- PWA (telefonga o'rnatiladigan ilova) ---------------------------------
    # Ildizdan beriladi, chunki service worker faqat o'z papkasi va undan
    # pastdagi manzillarni boshqara oladi.
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="pwa/manifest.webmanifest",
            content_type="application/manifest+json",
        ),
        name="manifest",
    ),
    path(
        "sw.js",
        TemplateView.as_view(
            template_name="pwa/sw.js", content_type="application/javascript"
        ),
        name="service_worker",
    ),
    path(
        "offline/",
        TemplateView.as_view(template_name="pwa/offline.html"),
        name="offline",
    ),
]

# Yuklangan fayllar (kitob muqovalari). Kichik loyiha uchun Django o'zi
# tarqatadi; yuklama ortsa nginx yoki bulutli saqlashga o'tkazish kerak.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if not settings.DEBUG:
    from django.views.static import serve as _serve

    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$", _serve, {"document_root": settings.MEDIA_ROOT}
        ),
    ]

admin.site.site_header = "Smart Library - Boshqaruv"
admin.site.site_title = "Smart Library"
admin.site.index_title = "Kutubxona tizimi"
