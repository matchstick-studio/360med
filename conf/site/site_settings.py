import os
import uuid

from network.settings import *

# from biostar.recipes.settings import *

from network.forum.settings import *

import logging
import platform

logger = logging.getLogger("network")

# Debugging flag.
DEBUG = True

# Set your known secret key here.
SECRET_KEY = str(uuid.uuid4())

# Admin users will be created automatically with DEFAULT_ADMIN_PASSWORD.
ADMINS = [
    ("Admin User", "admin@localhost")
]

# Set the default admin password.
DEFAULT_ADMIN_PASSWORD = SECRET_KEY

# Attempts to detect hostname so that automatic deployment works. It is best to set it with known data.
SITE_DOMAIN = platform.node()

SITE_ID = 1
SITE_NAME = "360Med Network"
HTTP_PORT = ''
PROTOCOL = 'http'

ALLOWED_HOSTS = [SITE_DOMAIN]

DATABASE_NAME = "network_prod"

DATABASES = {

    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': DATABASE_NAME,
        'USER': '',
        'PASSWORD': '',
        'HOST': '/var/run/postgresql/',
        'PORT': '',
    },
}

WSGI_APPLICATION = 'conf.run.site_wsgi.application'


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    # Attempts to load site secrets.
    from .site_secrets import *

    logger.info("Imported settings from .site_secrets")
except ImportError as exc:
    logger.warn(f"No secrets module could be imported: {exc}")
