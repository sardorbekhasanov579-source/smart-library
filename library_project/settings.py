"""
Django sozlamalari - Kutubxona boshqaruv tizimi (Smart Library).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-key-almashtiring-ishlab-chiqarishda",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()
]

# Render / Railway kabi xizmatlar domenni muhit o'zgaruvchisida beradi
for _env_host in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN"):
    _host = os.environ.get(_env_host, "").strip()
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

# HTTPS orqali forma yuborish uchun (Django 4+ talab qiladi)
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]
for _env_host in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN"):
    _host = os.environ.get(_env_host, "").strip()
    if _host:
        _origin = f"https://{_host}"
        if _origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Loyiha ilovalari
    "apps.core",
    "apps.users",
    "apps.catalog",
    "apps.books",
    "apps.readers",
    "apps.loans",
    "apps.reports",
    "apps.quizzes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise - serverda statik fayllarni (CSS, JS) tarqatadi.
    # O'rnatilmagan bo'lsa (lokal muhitda) ro'yxatdan chiqarib tashlanadi.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.CurrentUserMiddleware",
]

try:  # whitenoise o'rnatilmagan bo'lsa loyiha baribir ishga tushsin
    import whitenoise  # noqa: F401
except ImportError:
    MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

ROOT_URLCONF = "library_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "library_project.wsgi.application"
ASGI_APPLICATION = "library_project.asgi.application"

# ---------------------------------------------------------------------------
# Ma'lumotlar bazasi
# DB_ENGINE=postgres bo'lsa PostgreSQL, aks holda SQLite ishlatiladi.
# ---------------------------------------------------------------------------
def _database_from_url(url):
    """DATABASE_URL ni Django sozlamasiga aylantiradi (qo'shimcha kutubxonasiz).

    Masalan: postgres://foydalanuvchi:parol@host:5432/baza?sslmode=require
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    engines = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "postgis": "django.contrib.gis.db.backends.postgis",
        "mysql": "django.db.backends.mysql",
        "sqlite": "django.db.backends.sqlite3",
    }
    engine = engines.get(parsed.scheme.split("+")[0])
    if not engine:
        raise ValueError(f"DATABASE_URL da noma'lum turi: {parsed.scheme}")

    config = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 600,
    }
    if "sslmode" in (parsed.query or "") and engine.endswith("postgresql"):
        mode = dict(
            pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair
        ).get("sslmode")
        if mode:
            config["OPTIONS"] = {"sslmode": mode}
    return config


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    # Serverga joylashtirilgan holat (Render, Railway, Neon va h.k.)
    DATABASES = {"default": _database_from_url(DATABASE_URL)}
elif os.environ.get("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "library_db"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise statik fayllarni siqib, keshlab tarqatadi
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG and "whitenoise.middleware.WhiteNoiseMiddleware" in MIDDLEWARE
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

# ---------------------------------------------------------------------------
# Xavfsizlik (faqat DEBUG=0 bo'lganda, ya'ni serverda)
# ---------------------------------------------------------------------------
if not DEBUG:
    # Render/Railway HTTPS ni o'zi yakunlaydi va shu sarlavhani yuboradi
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    # HSTS ni o'z domeningiz bo'lgandan keyin yoqish tavsiya etiladi
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
    if SECURE_HSTS_SECONDS:
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {asctime} {name}: {message}",
                              "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "users:login"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Biznes qoidalari uchun standart qiymatlar (Sozlamalar modulidan o'zgartiriladi)
DEFAULT_LOAN_DAYS = 14
DEFAULT_MAX_BOOKS_PER_READER = 5

# ---------------------------------------------------------------------------
# Testlar moduli (apps.quizzes)
# Bu qiymatlar faqat standart - haqiqiy sozlamalar bazadagi `settings`
# jadvalidan (Sozlamalar bo'limi) olinadi.
# ---------------------------------------------------------------------------
DEFAULT_QUIZ_QUESTION_COUNT = 30      # har bir kitob uchun savollar soni
DEFAULT_QUIZ_PASS_PERCENT = 70        # "kitob o'qilgan" deb hisoblash chegarasi (%)
DEFAULT_QUIZ_DAYS_BEFORE_DUE = 1      # muddatdan necha kun oldin test yuborilsin

# Telegram bot tokeni va AI kalitini muhit o'zgaruvchisi orqali ham berish mumkin:
#   TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, ANTHROPIC_API_KEY / OPENAI_API_KEY
# Tavsiya: ularni Sozlamalar bo'limidan kiritish.
