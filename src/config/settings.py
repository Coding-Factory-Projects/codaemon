from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent  # .../src

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    ALLOWED_EMAIL_DOMAINS=(list, ["edu.itescia.fr", "edu.esiee-it.fr"]),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    GUNICORN_WORKERS=(int, 2),
)

# Load .env from the repo root if present (local dev). In Docker, env_file injects the vars.
_dotenv = BASE_DIR.parent / ".env"
if _dotenv.exists():
    environ.Env.read_env(_dotenv)

# --- Core ---
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "bot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database (minimal local state only; no roster lives here) ---
DATABASE_PATH = env("DATABASE_PATH", default=str(BASE_DIR.parent / "data" / "db.sqlite3"))
Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
        "OPTIONS": {"timeout": 20},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- i18n ---
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Static files (served by WhiteNoise from the web process) ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR.parent / "staticfiles"  # collectstatic output (baked into the image)
STATICFILES_DIRS = [BASE_DIR.parent / "assets"]  # source assets (logo, favicon, ...)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Plain storage in dev (no collectstatic needed); hashed + compressed in prod.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# --- Email (Mailgun over SMTP) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.eu.mailgun.org")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Coding Factory <bot@codingfactory.tech>")

# --- Discord ---
DISCORD_TOKEN = env("DISCORD_TOKEN", default="")
DISCORD_CLIENT_ID = env("DISCORD_CLIENT_ID", default="")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID", default="")
DISCORD_ADMIN_ROLE_ID = env("DISCORD_ADMIN_ROLE_ID", default="")
DISCORD_BASE_ROLE_ID = env("DISCORD_BASE_ROLE_ID", default="")
DISCORD_GUEST_ROLE_ID = env("DISCORD_GUEST_ROLE_ID", default="")
DISCORD_PRODUCT_OWNERS_ROLE_ID = env("DISCORD_PRODUCT_OWNERS_ROLE_ID", default="")
# In Discord, the @everyone role id is equal to the guild id.
DISCORD_EVERYONE_ROLE_ID = env("DISCORD_EVERYONE_ROLE_ID", default=DISCORD_GUILD_ID)

# --- Integration (learnd, formerly TeachPilot) ---
LEARND_BASE_URL = env("LEARND_BASE_URL", default="")
SHARED_SECRET = env("SHARED_SECRET", default="")
SHARED_SECRET_HEADER = env("SHARED_SECRET_HEADER", default="X-Shared-Secret")

# Public base URL of this service (used to build the onboarding link).
WEBSITE_BASE_URL = env("WEBSITE_BASE_URL", default="http://localhost:8000")

ALLOWED_EMAIL_DOMAINS = env("ALLOWED_EMAIL_DOMAINS")

# --- Logging (stdout; Docker captures it) ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
