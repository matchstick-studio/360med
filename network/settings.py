"""
Common settings that are applicable to all network apps.
"""

import os

# The logging configuration
from network.logconf import LOGGING

# Helper function for building absolute paths.
def join(*args):
    return os.path.abspath(os.path.join(*args))


# Run tasks in multi threaded mode when UWSGI is not installed.
MULTI_THREAD = True

# A setting to disable tasks altoghether.
DISABLE_TASKS = False

# Pagedown
PAGEDOWN_IMAGE_UPLOAD_ENABLED = True

# Set the home page to the engine or forum
INTERNAL_IPS = ["127.0.0.1"]

# Admin users will be created automatically with DEFAULT_ADMIN_PASSWORD.
ADMINS = [("Collin Rukundo", "support@matchstick.ug")]

DEFAULT_ADMIN_PASSWORD = "ultimate012"

# Allowed CORS websites
CORS_ORIGIN_WHITELIST = []

POSTGRES_HOST = os.environ.setdefault("POSTGRES_HOST", "")

# Shortcut to first admin information.
ADMIN_NAME, ADMIN_EMAIL = ADMINS[0]

# The default sender name on emails.
DEFAULT_FROM_EMAIL = f"{ADMIN_NAME} <{ADMIN_EMAIL}>"

# Show debug toolbar
DEBUG_TOOLBAR = False

# The current directory path.
__CURR_DIR = os.path.dirname(join(__file__))

# The directory relative to which all content is stored.
BASE_DIR = join(__CURR_DIR, "..")

# Django debug flag.
DEBUG = True

# Default installed apps.
DEFAULT_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "mailer",
    "compressor",
    "taggit",
    "snowpenguin.django.recaptcha2",
    "phonenumber_field",
    "widget_tweaks",
    "network.invitations",  # app to support invitations linked to allauth
]

# Enabled apps.
INSTALLED_APPS = DEFAULT_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Site specific information
SITE_ID = 1
SITE_DOMAIN = "localhost"
SITE_NAME = "360Med Network"

# INVITATIONS config
INVITATIONS_INVITATION_ONLY = True
INVITATIONS_EMAIL_SUBJECT_PREFIX = "[Welcome to 360Med]"

# Deployment specific parameters.
PROTOCOL = "http"
HTTP_PORT = "8000"
BASE_URL = f"{PROTOCOL}://{SITE_DOMAIN}:{HTTP_PORT}"

# Change this in production!
SECRET_KEY = "secret-key"

# Change this in production!
API_KEY = "api-key"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "string_if_invalid": "**MISSING**",
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.media",
                "django.contrib.messages.context_processors.messages",
                "network.context.main",
            ],
        },
    },
]

# Authentication backend.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# The WSGI application.
WSGI_APPLICATION = "network.wsgi.application"

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
]

# Database settings.
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases
""" DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "network_prod",
        "USER": "postgres",
        "PASSWORD": "ultimate012",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    },
} """
DATABASE_DIR = os.path.join(BASE_DIR, 'export', 'db')
os.makedirs(DATABASE_DIR, exist_ok=True)

DATABASE_NAME = os.environ.setdefault("DATABASE_NAME", "database.db")
# Ensure database is inside database directory.
DATABASE_NAME = os.path.join(DATABASE_DIR, DATABASE_NAME)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATABASE_NAME,
    }
}
ALLOWED_HOSTS = ["www.360med.org", "localhost", "127.0.0.1"]


# The URL configuration.
ROOT_URLCONF = "network.urls"

# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/
LANGUAGE_CODE = "en-us"

TIME_ZONE = "Africa/Kampala"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Configure language detection
LANGUAGE_DETECTION = ["en"]

# The static URL start.
STATIC_URL = "/static/"

# The static root directory.
STATIC_ROOT = join(BASE_DIR, "export", "static")

# Global directories for static files.
STATICFILES_DIRS = [
    join(BASE_DIR, "network", "static"),
]


# The media URL start.
MEDIA_URL = "/media/"

# The media root directory.
MEDIA_ROOT = join(BASE_DIR, "export", "media")

# The root for all docs
DOCS_ROOT = join(BASE_DIR, "docs")

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
]

# Apply default logger setting.
LOGGER_NAME = "network"

# The email delivery engine.
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# EMAIL_BACKEND = 'sparkpost.django.email_backend.SparkPostEmailBackend'

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Session engine.
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Session key name.
SESSION_KEY = "session"
