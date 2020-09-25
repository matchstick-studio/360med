# Used when testing all apps at once

from network.settings import *
from network.accounts.settings import *
from network.emailer.settings import *
from network.forum.settings import *

INSTALLED_APPS = DEFAULT_APPS + FORUM_APPS + PAGEDOWN_APP + ACCOUNTS_APPS + EMAILER_APP

ROOT_URLCONF = "network.server.urls"
