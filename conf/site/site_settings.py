import os
import uuid
import requests
import logging
import platform

from network.settings import *

# from network.recipes.settings import *

#from themes.bioconductor.settings import *

from network.forum.settings import *


logger = logging.getLogger("network")

# Debugging flag.
DEBUG = True

# Set your known secret key here.
SECRET_KEY = str(uuid.uuid4())

# Admin users will be created automatically with DEFAULT_ADMIN_PASSWORD.
ADMINS = [
    ("Administrator", "admin@360med.org")
]

# Set the default admin password.
DEFAULT_ADMIN_PASSWORD = SECRET_KEY

# Attempts to detect hostname so that automatic deployment works.
# It is best to set it with known data.
try:
    SITE_DOMAIN = requests.get('https://checkip.amazonaws.com').text.strip()
except Exception as err:
    SITE_DOMAIN = platform.node()


SITE_ID = 1
HTTP_PORT = ''
PROTOCOL = 'http'

ALLOWED_HOSTS = ['test.360med.org','360med.org','127.0.0.1','localhost','157.230.182.244']

DATABASE_NAME = "biostar-database"

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

SESSION_COOKIE_SECURE = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    # Attempts to load site secrets.
    from conf.run.site_secrets import *

    logger.info("Imported settings from .site_secrets")
except ImportError as exc:
    logger.warn(f"No secrets module could be imported: {exc}")

print(SITE_DOMAIN, "DOMAIN")