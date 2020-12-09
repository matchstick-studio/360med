import os
import uuid
import requests
import logging
import platform

from network.settings import *

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
""" try:
    SITE_DOMAIN = requests.get('https://checkip.amazonaws.com').text.strip()
except Exception as err:
    SITE_DOMAIN = platform.node() """

SITE_DOMAIN = "157.230.182.244"
SITE_ID = 1
HTTP_PORT = ''
PROTOCOL = 'http'

ALLOWED_HOSTS = [SITE_DOMAIN, 'test.360med.org', '127.0.0.1','localhost']

DATABASE_NAME = "network-database"
DATABASE_USER = 'network_admin'
DATABASE_PASSWORD = 'vtta170e0lvbq3ea'
DATABASE_HOST = 'network-database-do-user-8310054-0.b.db.ondigitalocean.com'
DATABASE_PORT ='25060'

DATABASES = {

    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': DATABASE_NAME,
        'USER': DATABASE_USER,
        'PASSWORD': DATABASE_PASSWORD,
        'HOST': DATABASE_HOST,
        'PORT': DATABASE_PORT,
    },
}

WSGI_APPLICATION = 'conf.run.site_wsgi.application'

SESSION_COOKIE_SECURE = True

INSTALLED_APPS += ["anymail"]

EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

try:
    # Attempts to load site secrets.
    from conf.run.site_secrets import *

    logger.info("Imported settings from .site_secrets")
except ImportError as exc:
    logger.warn(f"No secrets module could be imported: {exc}")

print(SITE_DOMAIN, "DOMAIN")