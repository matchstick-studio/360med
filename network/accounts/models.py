import uuid
import os
import io
from datetime import datetime, timedelta
from django.utils import timezone
import pyavagen
from django.core.files.base import ContentFile
import mistune
from django.conf import settings
from django.shortcuts import reverse
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import utc
from network.accounts import util
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField
from django.utils.translation import ugettext_lazy as _


def fixcase(name):
    return name.upper() if len(name) == 1 else name.lower()


def now():
    return datetime.utcnow().replace(tzinfo=utc)


MAX_UID_LEN = 255
MAX_NAME_LEN = 255
MAX_TEXT_LEN = 10000
MAX_FIELD_LEN = 1024


class ProfileManager(models.Manager):
    def valid_users(self):
        """
        Return valid user queryset, filtering new and trusted users.
        """

        # Filter for new or trusted users.
        query = (
            super()
            .get_queryset()
            .filter(models.Q(state=Profile.TRUSTED) | models.Q(state=Profile.NEW))
        )

        return query


def image_path(instance, filename):
    # Name the data by the filename.
    imgpath = os.path.join(settings.PAGEDOWN_IMAGE_UPLOAD_PATH, filename)

    return imgpath


class UserImage(models.Model):

    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)

    # Image file path, relative to MEDIA_ROOT
    image = models.ImageField(
        default=None, blank=True, upload_to=image_path, max_length=MAX_FIELD_LEN
    )

def get_avatar_full_path(instance, filename):
    ext = filename.split('.')[-1]
    path = f'{settings.MEDIA_PUBLIC_ROOT}/avatars'
    name = f'{instance.uid}_{instance.avatar_version:04d}'
    return f'{path}/{name}.{ext}'

class Profile(models.Model):

    NEW, TRUSTED, SUSPENDED, BANNED, SPAMMER = range(5)
    STATE_CHOICES = [
        (NEW, "New"),
        (TRUSTED, "Active"),
        (SPAMMER, "Spammer"),
        (SUSPENDED, "Suspended"),
        (BANNED, "Banned"),
    ]
    state = models.IntegerField(default=NEW, choices=STATE_CHOICES, db_index=True)

    READER, MODERATOR, MANAGER, BLOGGER = range(4)
    ROLE_CHOICES = [
        (READER, "Reader"),
        (MODERATOR, "Moderator"),
        (MANAGER, "Admin"),
        (BLOGGER, "Blog User"),
    ]

    NO_DIGEST, DAILY_DIGEST, WEEKLY_DIGEST, MONTHLY_DIGEST, ALL_MESSAGES = range(5)

    DIGEST_CHOICES = [
        (NO_DIGEST, "Never"),
        (DAILY_DIGEST, "Daily"),
        (WEEKLY_DIGEST, "Weekly"),
        (MONTHLY_DIGEST, "Monthly"),
        (ALL_MESSAGES, "Email for every new thread (mailing list mode)"),
    ]
    # Subscription to daily and weekly digests.
    digest_prefs = models.IntegerField(choices=DIGEST_CHOICES, default=WEEKLY_DIGEST)

    LOCAL_MESSAGE, EMAIL_MESSAGE, NO_MESSAGES, DEFAULT_MESSAGES = range(4)
    MESSAGING_TYPE_CHOICES = [
        (DEFAULT_MESSAGES, "Default"),
        (EMAIL_MESSAGE, "Email"),
        (LOCAL_MESSAGE, "Local Messages"),
        (NO_MESSAGES, "No messages"),
    ]
    # Default subscriptions inherit from this
    message_prefs = models.IntegerField(
        choices=MESSAGING_TYPE_CHOICES, default=DEFAULT_MESSAGES
    )

    # Gender choices
    MALE, FEMALE, OTHER = range(3)
    GENDER_CHOICES = [(MALE, "Male"), (FEMALE, "Female"), (OTHER, "Other")]

    # Occupations
    (
        MEDICAL_DOCTOR,
        NURSE,
        DENTIST,
        CLINICAL_OFFICER,
        PHARMACIST,
        LABORATORY_SCIENTIST,
    ) = range(6)
    OCCUPATION_CHOICES = [
        (MEDICAL_DOCTOR, "Medical Doctor"),
        (NURSE, "Nurse"),
        (DENTIST, "Dentist"),
        (CLINICAL_OFFICER, "Clinical Officer"),
        (PHARMACIST, "Pharmacist"),
        (LABORATORY_SCIENTIST, "Laboratory Scientist"),
    ]

    DEGREE = (
        (None, "Select your degree"),
        ('Undergraduate', "Undergraduate"),
        ('Bachelor', "Bachelor"),
        ('Master', "Master"),
        ('PhD', "PhD"),
        ('Doctor of Sciences', "Doctor of Sciences"),
    )

    STUDENT_ROLES = ('Student', 'PhD Student')

    # Connection to the user.
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # User unique id (handle)
    uid = models.CharField(max_length=MAX_UID_LEN, unique=True)

    # User diplay name.
    name = models.CharField(max_length=MAX_NAME_LEN, default="", db_index=True)

    # Maximum amount of uploaded files a user is allowed to aggregate, in mega-bytes.
    max_upload_size = models.IntegerField(default=0)

    # The role of the user.
    role = models.IntegerField(default=READER, choices=ROLE_CHOICES)

    # The role of the user.
    gender = models.IntegerField(default=MALE, choices=GENDER_CHOICES, blank=False)

    # DOB
    dob = models.DateTimeField(default=timezone.now, db_index=True, null=True, blank=False)

    # Alt email addresses (up to two)
    alt_email_a = models.EmailField(max_length=MAX_TEXT_LEN, null=True, blank=True)

    alt_email_b = models.EmailField(max_length=MAX_TEXT_LEN, null=True, blank=True)

    # degree type
    degree = models.CharField(
        choices=DEGREE, max_length=30, null=True, blank=False
    )

    # The main occupation of the user.
    occupation = models.IntegerField(default=MEDICAL_DOCTOR, choices=OCCUPATION_CHOICES, blank=False)

    position = models.CharField(max_length=MAX_NAME_LEN, null=True)

    institution = models.CharField(max_length=MAX_NAME_LEN, null=True)

    qualifications = models.CharField(blank=True, null=True, max_length=100)

    # User can specify their professional focus
    expertise = models.CharField(default="", max_length=MAX_TEXT_LEN, blank=True)

    # Users select those institutions they are affiliated with
    affiliations = models.CharField(default="", max_length=MAX_TEXT_LEN, blank=True)

    # licence number of medical body
    licence = models.CharField(max_length=100, blank=False, null=True)

    # The date the user last logged in.
    last_login = models.DateTimeField(null=True, max_length=255, db_index=True)

    # The number of new messages for the user.
    new_messages = models.IntegerField(default=0, db_index=True)

    # The date the user joined.
    date_joined = models.DateTimeField(auto_now_add=True, max_length=255)

    # user's country
    country = CountryField(null=True, blank=False)

    # User provided location.
    location = models.CharField(default="", max_length=255, blank=True, db_index=True)

    # User's mobile number
    phone = PhoneNumberField(blank=True)

    # User reputation score.
    score = models.IntegerField(default=0, db_index=True)

    # This field is used to select content for the user.
    my_tags = models.CharField(default="", max_length=MAX_TEXT_LEN, blank=True)

    # The tag value is the canonical form of the post's tags
    watched_tags = models.CharField(max_length=MAX_TEXT_LEN, default="", blank=True)

    # Description provided by the user html.
    text = models.TextField(
        default="No bio available yet", null=True, max_length=MAX_TEXT_LEN, blank=True
    )

    # The html version of the user information.
    html = models.TextField(null=True, max_length=MAX_TEXT_LEN, blank=True)

    # The state of the user email verfication.
    email_verified = models.BooleanField(default=False)

    # Automatic notification
    notify = models.BooleanField(default=False)

    # Opt-in to all messages from the site
    opt_in = models.BooleanField(default=False)

    has_finished_registration = models.BooleanField(default=False, null=True)

    # avatar stuff
    avatar = models.ImageField(upload_to=get_avatar_full_path, blank=True)
    avatar_version = models.IntegerField(default=0, blank=True, editable=False)

    objects = ProfileManager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.uid = self.uid or util.get_uuid(8)
        self.html = self.html or mistune.markdown(self.text)
        self.max_upload_size = self.max_upload_size or self.set_upload_size()
        """ self.name = self.name or self.user.first_name or self.user.email.split("@")[0] """
        self.date_joined = self.date_joined or now()
        self.last_login = self.last_login or now()  # - timedelta(days=1)
        super(Profile, self).save(*args, **kwargs)

    @property
    def state_dict(self):
        return dict(self.STATE_CHOICES)

    @property
    def upload_size(self):

        # Give staff higher limits.
        if self.user.is_staff or self.user.is_superuser:
            return self.max_upload_size * 100
        return self.max_upload_size

    def set_upload_size(self):
        """
        Used to set the inital value
        """

        # Admin users upload limit
        if self.user.is_superuser or self.user.is_staff:
            return settings.ADMIN_UPLOAD_SIZE
        # Trusted users upload limit
        if self.user.profile.trusted:
            return settings.TRUSTED_UPLOAD_SIZE

        # Get the default upload limit
        return settings.MAX_UPLOAD_SIZE

    def require_recaptcha(self):
        """Check to see if this user requires reCAPTCHA"""
        is_required = not (
            self.trusted or self.score > settings.RECAPTCHA_THRESHOLD_USER_SCORE
        )
        return is_required

    def get_score(self):
        """"""
        score = self.score * 10
        return score

    @property
    def is_moderator(self):
        # Managers can moderate as well.
        return (
            self.role == self.MODERATOR
            or self.role == self.MANAGER
            or self.user.is_staff
            or self.user.is_superuser
        )

    @property
    def trusted(self):
        return (
            self.user.is_staff
            or self.state == self.TRUSTED
            or self.role == self.MODERATOR
            or self.role == self.MANAGER
            or self.user.is_superuser
        )

    @property
    def is_manager(self):
        return self.role == self.MANAGER

    def get_absolute_url(self):

        return reverse("user_profile", kwargs=dict(uid=self.uid))

    @property
    def is_suspended(self):
        return self.state == self.SUSPENDED

    @property
    def is_banned(self):
        return self.state == self.BANNED

    @property
    def is_spammer(self):
        return self.state == self.SPAMMER

    @property
    def is_valid(self):
        """
        User is not banned, suspended, or banned
        """
        return not self.is_spammer and not self.is_suspended and not self.is_banned

    @property
    def recently_joined(self):
        """
        User that joined X amount of days are considered new.
        """
        recent = (util.now() - self.date_joined).days > settings.RECENTLY_JOINED_DAYS
        return recent

    def bump_over_threshold(self):

        # Bump the score by smallest values to get over the low rep threshold.
        score = self.score
        score += 1 + (settings.LOW_REP_THRESHOLD - self.score)

        Profile.objects.filter(id=self.id).update(score=score)

    @property
    def low_rep(self):
        """
        User has a low score
        """
        return self.score <= settings.LOW_REP_THRESHOLD and not self.is_moderator

def generate_avatar(profile):
    img_io = io.BytesIO()
    avatar = pyavagen.Avatar(
        pyavagen.CHAR_SQUARE_AVATAR,
        size=500,
        string=profile.name,
        blur_radius=100
    )
    avatar.generate().save(img_io, format='PNG', quality=100)
    img_content = ContentFile(img_io.getvalue(), f'{profile.uid}.png')
    return img_content


def change_avatar(profile, image_file):
    if profile.avatar:
        profile.avatar.delete()
    profile.avatar_version += 1
    profile.avatar = image_file
    profile.save()
    return profile


class Logger(models.Model):
    # Put in delte
    MODERATING, VERIFY, CREATION, EDIT, LOGIN, LOGOUT, BROWSING = range(7)

    ACTIONS_CHOICES = [
        (MODERATING, "Preformed a moderation action."),
        (VERIFY, "Added verification data"),
        (CREATION, "Created an object."),
        (EDIT, "Edited an object."),
        (LOGIN, "Logged in to the site."),
        (LOGOUT, "Logged out of the site."),
        (BROWSING, "Browsing the site."),
    ]

    # User that preformed this action
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    # Action this user is took.
    action = models.IntegerField(choices=ACTIONS_CHOICES, default=BROWSING)

    # Stores the specific log text
    log_text = models.TextField(default="")

    # Date this log was created
    date = models.DateTimeField(auto_now_add=True)


# Connects user to message bodies
class MessageBody(models.Model):
    """
    A message that may be shared across all users.
    """

    body = models.TextField(max_length=MAX_TEXT_LEN)
    html = models.TextField(default="", max_length=MAX_TEXT_LEN * 10)

    def save(self, *args, **kwargs):
        self.html = self.html or mistune.markdown(self.body)
        super(MessageBody, self).save(**kwargs)


# Connects user to message bodies
class Message(models.Model):
    """
    Connects recipients to sent messages
    """

    SPAM, VALID, UNKNOWN = range(3)
    SPAM_CHOICES = [(SPAM, "Spam"), (VALID, "Not spam"), (UNKNOWN, "Unknown")]
    spam = models.IntegerField(choices=SPAM_CHOICES, default=UNKNOWN)

    uid = models.CharField(max_length=32, unique=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="author", on_delete=models.CASCADE
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    subject = models.CharField(max_length=120)
    body = models.ForeignKey(MessageBody, on_delete=models.CASCADE)

    unread = models.BooleanField(default=True)
    sent_date = models.DateTimeField(db_index=True, null=True)

    def save(self, *args, **kwargs):
        self.uid = self.uid or util.get_uuid(10)
        self.sent_date = self.sent_date or util.now()
        super(Message, self).save(**kwargs)

    def __str__(self):
        return f"Message {self.sender}, {self.recipient}"

    def css(self):
        return "new" if self.unread else ""
