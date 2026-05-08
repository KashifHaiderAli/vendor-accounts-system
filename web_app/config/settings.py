import os
import sys
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "local-dev-secret-key")

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "authentication",
    "masters",
    "sales",
    "purchases",
    "services",
    "accounts_module",
    "reports",
    "backup",
    "licensing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "licensing.middleware.LicensePlaceholderMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_DB_PATH = REPO_ROOT / "data" / "vendor_accounts.db"
DATABASE_PATH = os.getenv("VENDOR_ACCOUNTS_DB_PATH", str(DEFAULT_DB_PATH))
DATABASE_FILE = Path(DATABASE_PATH)
DATABASE_MISSING_MESSAGE = (
    "Database file not found. Please create it first using DB App or check "
    "VENDOR_ACCOUNTS_DB_PATH in web_app/.env"
)

if not DATABASE_FILE.parent.exists():
    print(DATABASE_MISSING_MESSAGE, file=sys.stderr)
    raise RuntimeError(DATABASE_MISSING_MESSAGE)

if not DATABASE_FILE.exists():
    print(DATABASE_MISSING_MESSAGE, file=sys.stderr)
    raise RuntimeError(DATABASE_MISSING_MESSAGE)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"
