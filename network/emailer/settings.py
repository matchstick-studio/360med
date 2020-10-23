# Import all common settings.
from network.settings import *

# Additional apps enabled.
EMAILER_APP = [
    'network.emailer.apps.EmailerConfig'
]

INSTALLED_APPS = DEFAULT_APPS + EMAILER_APP

# The url specification.
ROOT_URLCONF = 'network.emailer.urls'

# This flag is used flag situation where a data migration is in progress.
# Allows us to turn off certain type of actions (for example sending emails).
DATA_MIGRATION = False
