"""
Django settings for fileshare project.
Simple file-upload site + admin dashboard, built for free deployment on Render.com
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------
# On Render, set SECRET_KEY as an environment variable (Dashboard -> Environment).
# Locally it falls back to a dev-only key so you can run it without extra setup.
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "dev-only-insecure-key-change-me-before-deploying"
)

# DEBUG must be "False" in production. Set DEBUG=False in Render's environment vars.
DEBUG = os.environ.get("DEBUG", "True") == "True"

# Render gives your service a URL like: your-app.onrender.com
# RENDER_EXTERNAL_HOSTNAME is auto-provided by Render at runtime.
ALLOWED_HOSTS = []
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
ALLOWED_HOSTS += os.environ.get("EXTRA_ALLOWED_HOSTS", "").split(",") if os.environ.get("EXTRA_ALLOWED_HOSTS") else []
if DEBUG:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = []
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# ---------------------------------------------------------------------------
# APPLICATION DEFINITION
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "uploader",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves static files in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "fileshare.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "fileshare.wsgi.application"

# ---------------------------------------------------------------------------
# DATABASE
# NOTE: On Render's free web-service plan the filesystem is EPHEMERAL -
# it resets on every deploy/restart. That means both this SQLite DB and
# any uploaded files in MEDIA_ROOT can be wiped. See README.md for how to
# add a small persistent disk on Render, or swap file storage to Cloudinary
# (free tier) if you need uploads to survive restarts.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# STATIC & MEDIA FILES
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# UPLOAD LIMITS
# ---------------------------------------------------------------------------
# Reject uploads bigger than 25 MB to protect the free-tier server.
# Change this number (in bytes) if you need a different limit.
MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
