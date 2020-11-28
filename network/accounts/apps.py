import logging
import bleach

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate

logger = logging.getLogger('engine')


class AccountsConfig(AppConfig):
    name = 'network.accounts'

    def ready(self):
        from . import signals
        # Triggered after a migration command.
        post_migrate.connect(init_app, sender=self)


def init_app(sender, **kwargs):
    init_site()
    init_users()


def init_users():
    """
    Creates admin users if needed.
    """
    from .models import User, Profile

    for name, email in settings.ADMINS:
        user = User.objects.filter(email=email).first()
        if not user:
            user = User.objects.create(first_name=name, email=email, is_superuser=True, is_staff=True)
            User.objects.filter(pk=user.pk).update(username=f'admin-{user.pk}')
            # Reload to update state that signals may change.
            user = User.objects.filter(pk=user.pk).first()
            user.set_password(settings.DEFAULT_ADMIN_PASSWORD)

            user.save()

            text = "Admin user created automatically on startup."
            Profile.objects.filter(user=user).update(location="Server Farm", name=name, text=text, html=text)
            logger.info(f"Creating admin user: {user.email}")
        else:
            # You might want to reapply the default ADMIN password on migration.
            # This will destroy existing admin sessions.
            #user.set_password(settings.DEFAULT_ADMIN_PASSWORD)
            #user.save()
            #logger.info(f"Resetting password for admin user: {user.email}, {user.username}")
            logger.info(f"Admin user: {user.email} already exists")
            pass


def init_site():
    """
    Updates site domain and name.
    """
    from django.contrib.sites.models import Site

    # Print information on the database.
    db = settings.DATABASES['default']
    logger.info(f"db.name={db['NAME']}, db.engine={db['ENGINE']}")
    logger.info(f"email.backend={settings.EMAIL_BACKEND}, email.sender={settings.DEFAULT_FROM_EMAIL}")

    # Create the default site if necessary.
    Site.objects.get_or_create(id=settings.SITE_ID)

    # Update the default site domain and name.
    Site.objects.filter(id=settings.SITE_ID).update(domain=settings.SITE_DOMAIN, name=settings.SITE_NAME)

    # Get the current site
    site = Site.objects.get(id=settings.SITE_ID)
    logger.info("site.name={}, site.domain={}".format(site.name, site.domain))
