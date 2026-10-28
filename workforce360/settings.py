"""Local Django settings; application records remain in the existing SQLite file."""
from pathlib import Path
from sqlalchemy.engine import make_url
from backend.config import ROOT, settings as legacy_settings

BASE_DIR = ROOT
SECRET_KEY = legacy_settings.session_secret or "development-only-secret-configure-WIR_SESSION_SECRET"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
ROOT_URLCONF = "workforce360.urls"
WSGI_APPLICATION = "workforce360.wsgi.application"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "webapp",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.template.context_processors.csrf",
    ]},
}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(make_url(legacy_settings.database_url).database)}}
LANGUAGE_CODE = "en-us"
TIME_ZONE = legacy_settings.site_timezone
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "webapp" / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = legacy_settings.cookie_secure
SESSION_COOKIE_AGE = 8 * 60 * 60
# Session contents are only operator id/name/role; signed cookies avoid adding
# framework session tables to the pre-existing Workforce360 SQLite schema.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SECURE = legacy_settings.cookie_secure
X_FRAME_OPTIONS = "DENY"
MEDIA_ROOT = legacy_settings.upload_dir.parent
