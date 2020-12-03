from network.settings import *
from network.emailer.settings import *
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# Django debug flag.
DEBUG = True

# Should the site allow signup.
ALLOW_SIGNUP = False

# Private key used to validate external logins. Must be changed in production
LOGIN_PRIVATE_KEY = "private-key"

ADMINS = [
    ("Administrator", "admin@360med.org")
]

PAGEDOWN_APP = ['pagedown.apps.PagedownConfig']

PAGEDOWN_IMAGE_UPLOAD_ENABLED = True

# Maximum size per image uploaded, in mb.
MAX_IMAGE_SIZE_MB = 2

# Maximum number of images allowed.
MAX_IMAGES = 100


# User above this score do not get a reCAPTCHA
RECAPTCHA_THRESHOLD_USER_SCORE = 1

# The password for admin users. Must be changed in production.
DEFAULT_ADMIN_PASSWORD = "ultimate012"

# Shortcut to first admin information.
ADMIN_NAME, ADMIN_EMAIL = ADMINS[0]

# The default sender name on emails.
DEFAULT_FROM_EMAIL = f"{ADMIN_NAME} <{ADMIN_EMAIL}>"

# User score threshold to be considered low reputation.
LOW_REP_THRESHOLD = 0

# Users below this threshold are considered to have recently joined.
RECENTLY_JOINED_DAYS = 30

# In MB
MAX_UPLOAD_SIZE = 10

# Trusted users upload limit in MB.
TRUSTED_UPLOAD_SIZE = 500

# Admin users upload limit in MB
ADMIN_UPLOAD_SIZE = 1000

MESSAGES_PER_PAGE = 5

# Set RECAPTCH keys here.
RECAPTCHA_PUBLIC_KEY = ""
RECAPTCHA_PRIVATE_KEY = ""


# Other settings
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[360Med Network] "
ACCOUNT_PASSWORD_MIN_LENGHT = 6
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"

LOGIN_REDIRECT_URL = "/"
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True

ACCOUNTS_APPS = [

    # Accounts configuration.
    'network.accounts.apps.AccountsConfig',

    # Allauth templates come last.
    'allauth',
    'allauth.account',
    'widget_tweaks',
]

# Should the server look up locations in a task.
LOCATION_LOOKUP = False

INSTALLED_APPS = DEFAULT_APPS + ACCOUNTS_APPS + EMAILER_APP + PAGEDOWN_APP

AUTHENTICATION_BACKENDS += ["allauth.account.auth_backends.AuthenticationBackend"]

ROOT_URLCONF = 'network.accounts.urls'