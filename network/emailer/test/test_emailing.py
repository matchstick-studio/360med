import logging
from django.core import management
from network.emailer import tasks, auth
from django.test import TestCase
from network.emailer import models

logger = logging.getLogger("engine")


class SendMailTest(TestCase):
    def setUp(self):
        logger.setLevel(logging.WARNING)

    def test_send_mail(self):
        "Test email sending using auth."

        context = dict(target_email="2@lvh.me")
        from_mail = "mailer@360med.org"
        template_name = "test_email.html"
        successful = tasks.send_email(
            recipient_list=["2@lvh.me"],
            extra_context=context,
            template_name=template_name,
            from_email=from_mail,
        )

        self.assertTrue(successful, "Error sending mail")

    def test_add_subs(self):
        "Test adding subscription using auth"

        group = models.EmailGroup()
        group.save()
        auth.add_subscription(email="Test@tested.com", group=group, name="tested")

    def test_mailing(self):
        "Test sending email using manage commands."
        management.call_command("test_email")


class ModelTests(TestCase):
    def setUp(self):
        logger.setLevel(logging.WARNING)

    def test_email_group(self):
        from network.emailer.models import EmailGroup

        test = EmailGroup(name="tested", uid="tested")
        test.save()

        print(test)

    def test_email_address(self):
        from network.emailer.models import EmailAddress

        test = EmailAddress(name="tested", uid="tested")
        test.save()

        print(test)
        pass
