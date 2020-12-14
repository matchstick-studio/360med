
from pagedown.widgets import PagedownWidget
from django import forms
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django.shortcuts import reverse
from django.conf import settings
from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget
from network.accounts.models import User
from .models import Post, Event, Job
from network.forum import models, auth
from django.template.loader import render_to_string
from django.core.mail import send_mail

from .const import *

# Share logger with models
logger = models.logger

MIN_CHARS = 5
MAX_CONTENT = 15000
MIN_CONTENT = 5
MAX_TITLE = 400
MAX_TAGS = 5


def english_only(text):
    try:
        text.encode('ascii')
    except Exception:
        raise ValidationError('Text may only contain plain text (ASCII) characters')


def valid_title(text):
    "Validates form input for tags"
    text = text.strip()
    if not text:
        raise ValidationError('Please enter a title')

    text = text.replace(" ", '')
    if len(text) < MIN_CHARS:
        raise ValidationError(f'Too short, please add more than {MIN_CHARS} characters.')
    if len(text) > MAX_TITLE:
        raise ValidationError(f'Too Long, please add less than {MAX_TITLE} characters.')


def valid_tag(text):
    "Validates form input for tags"

    words = text.split(",")
    if len(words) > MAX_TAGS:
        raise ValidationError('You have too many tags (5 allowed)')


def informative_choices(choices):
    """
    Map choices for post types to a more informative description.
    """
    mapper = {
              Post.QUESTION: "Ask a question", Post.TUTORIAL: "Share a tutorial",
              Post.JOB: "Post a job", Post.FORUM: "Start a discussion",
              Post.TOOL: "Share a tool", Post.NEWS: "Announce news", Post.EVENT: "Add an event"
              }
    new_choices = []
    for c in choices:
        new_choices.append((c[0], mapper.get(c[0], c[1])))

    return new_choices


def common_elem(set_a, set_b):
    # Return True if two sets share at least one common element.
    return len(set_a.intersection(set_b)) > 0


def required_tags(lst):
    """
    Ensure at least one tag is present in the
    """

    if not settings.REQUIRED_TAGS:
        return

    # Get the tags file.
    tags = open(settings.REQUIRED_TAGS, 'r').readlines()
    tags = set([x.strip() for x in tags])

    # Create two sets from the source ( input parameter)
    # and target ( file with required tags ) .
    source_set = set(lst)
    target_set = set(tags)

    if not common_elem(source_set, target_set):
        url = settings.REQUIRED_TAGS_URL
        msg = mark_safe(f"At least one package from <a href='{url}' target='_blank'>this list</a> is required.")
        raise forms.ValidationError(msg)

    return


class PostLongForm(forms.Form):

    choices = [opt for opt in Post.TYPE_CHOICES if opt[0] in Post.TOP_LEVEL]

    if settings.ALLOWED_POST_TYPES:
        choices = [opt for opt in choices if opt[1] in settings.ALLOWED_POST_TYPES]

    choices = informative_choices(choices=choices)

    post_type = forms.IntegerField(label="What would you like to do?",
                                   widget=forms.Select(choices=choices, attrs={'class': "ui dropdown"}),
                                   help_text="Select a post type.")
    title = forms.CharField(label="Post Title", max_length=200, min_length=2,
                            validators=[valid_title, english_only],
                            help_text="Enter a descriptive title to encourage better engagement.")
    tag_val = forms.CharField(label="Tags", max_length=50, required=False, validators=[valid_tag],
                              help_text="""
                              Type to search through existing tags or create new tags by typing and adding a comma.
                              You can add more than one tag.
                              """,
                              widget=forms.HiddenInput())

    content = forms.CharField(widget=forms.Textarea,
                              validators=[english_only],
                              min_length=MIN_CONTENT, max_length=MAX_CONTENT, label="Post Content", strip=False)

    def __init__(self, post=None, user=None, *args, **kwargs):
        self.post = post
        self.user = user
        super(PostLongForm, self).__init__(*args, **kwargs)

        not_trusted = self.user.is_authenticated and (not self.user.profile.trusted)

        # Untrusted users get a recaptcha field
        if settings.RECAPTCHA_PRIVATE_KEY and not_trusted:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())

    def edit(self):
        """
        Edit an existing post.
        """
        if self.user != self.post.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit a post.")
        data = self.cleaned_data
        self.post.title = data.get('title')
        self.post.content = data.get("content")
        self.post.type = data.get('post_type')
        self.post.tag_val = data.get('tag_val')
        self.post.lastedit_user = self.user
        self.post.save()
        return self.post

    def clean_tag_val(self):
        """
        Take out duplicates
        """
        tag_val = self.cleaned_data["tag_val"] or 'tag1, tag2 '
        tags = set([x for x in tag_val.split(",") if x])

        required_tags(tags)

        return ",".join(tags)

    def clean_content(self):
        content = self.cleaned_data["content"]
        length = len(content.replace(" ", ""))

        if length < MIN_CHARS:
            raise forms.ValidationError(f"Too short, place add more than {MIN_CHARS}")

        return content


class PostShortForm(forms.Form):
    MIN_LEN, MAX_LEN = 10, 10000
    parent_uid = forms.CharField(widget=forms.HiddenInput(), min_length=2, max_length=32)
    content = forms.CharField(widget=forms.Textarea,
                              min_length=MIN_LEN, max_length=MAX_LEN, strip=False)

    def __init__(self, user=None, post=None, recaptcha=True, *args, **kwargs):
        self.user = user
        self.post = post
        super().__init__(*args, **kwargs)
        self.fields['content'].strip = False

        not_trusted = self.user.is_authenticated and (not self.user.profile.trusted)

        # Untrusted users get a recaptcha field
        if recaptcha and settings.RECAPTCHA_PRIVATE_KEY and not_trusted:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())

    def clean_content(self):
        content = self.cleaned_data["content"]
        return content

    def clean(self):
        cleaned_data = super(PostShortForm, self).clean()
        if self.user.is_anonymous:
            raise forms.ValidationError("You need to be logged in.")
        return cleaned_data


class PostModForm(forms.Form):

    def __init__(self, post, request, user, *args, **kwargs):
        self.post = post
        self.user = user
        self.request = request

        super(PostModForm, self).__init__(*args, **kwargs)

        choices = [
            (OPEN_POST, "Open post"),
            (DELETE, "Delete post."),
            (REPORT_SPAM, "Mark as spam."),

        ]

        # Options for top level posts.
        if post.is_toplevel:
            suffix = [(CLOSE, "Close post ( reason required ). "),
                      (DUPLICATE, "Duplicated post ( links required ).")]
            choices = [(BUMP_POST, "Bump post.")] + choices + suffix
            self.fields['comment'] = forms.CharField(required=False, max_length=1000, widget=forms.Textarea,
                                                     strip=True)

        self.fields['action'] = forms.IntegerField(widget=forms.RadioSelect(choices=choices), required=True)

    def clean(self):
        action = self.cleaned_data.get("action")
        comment = self.cleaned_data.get("comment")

        if not self.user.profile.is_moderator:
            raise forms.ValidationError("You need to be a moderator to preform that action.")

        if (action == CLOSE or action == DUPLICATE) and not comment:
            raise forms.ValidationError("Closing a post requires a reason.")

        return self.cleaned_data

class EventForm(forms.Form):

    title = forms.CharField(label="Event Title", max_length=200, min_length=4,
                            validators=[valid_title, english_only],
                            help_text="Enter a descriptive title")

    location = forms.CharField(label="Location", max_length=200, min_length=4,
                            required=True,
                            help_text="Where will the event take place?")

    event_date = forms.DateTimeField(label="Event Date",
                            required=True,
                            help_text="When is the event?",
                            input_formats=['%d/%m/%Y %H:%M']
                            )

    tag_val = forms.CharField(label="Event tags (optional)", max_length=50, required=False, validators=[valid_tag],
                              help_text="""
                              Pick a tag for your event or type and hit ENTER to create one.
                              """,
                              widget=forms.HiddenInput())

    content = forms.CharField(widget=forms.Textarea,
                              validators=[english_only],
                              min_length=MIN_CONTENT, max_length=MAX_CONTENT, label="Event Description", strip=False)

    external_link = forms.URLField(label="External Link", required=False, help_text="Optional link with more information")

    def __init__(self, event=None, user=None, *args, **kwargs):
        self.event = event
        self.user = user
        super(EventForm, self).__init__(*args, **kwargs)

        not_trusted = self.user.is_authenticated and (not self.user.profile.trusted)

        # Untrusted users get a recaptcha field
        if settings.RECAPTCHA_PRIVATE_KEY and not_trusted:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())

    def edit(self):
        """
        Edit an existing event.
        """
        if self.user != self.event.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit an event.")
        data = self.cleaned_data
        self.event.title = data.get('title')
        self.event.content = data.get("content")
        self.event.event_date = data.get('event_date')
        self.event.location = data.get('location')
        self.event.external_link = data.get('external_link')
        self.event.tag_val = data.get('tag_val')
        self.event.lastedit_user = self.user
        self.event.save()
        return self.event

    def clean_tag_val(self):
        """
        Take out duplicates
        """
        tag_val = self.cleaned_data["tag_val"]
        tags = set([x for x in tag_val.split(",") if x])

        required_tags(tags)

        return ",".join(tags)

    def clean_content(self):
        content = self.cleaned_data["content"]
        length = len(content.replace(" ", ""))

        if length < MIN_CHARS:
            raise forms.ValidationError(f"Too short, place add more than {MIN_CHARS}")

        return content

class JobForm(forms.Form):

    title = forms.CharField(label="Job Title", max_length=200, min_length=4,
                            validators=[valid_title, english_only],
                            help_text="Enter title of the position")

    institution = forms.CharField(label="Institution", max_length=200, min_length=4,
                            required=True,
                            help_text="Specify who is hiring")

    apply_before = forms.DateTimeField(label="Apply Before",
                            required=True,
                            help_text="When is the deadline?",
                            input_formats=['%d/%m/%Y %H:%M']
                            )

    content = forms.CharField(widget=forms.Textarea,
                              validators=[english_only],
                              min_length=MIN_CONTENT, max_length=MAX_CONTENT, label="Job Description", strip=False)

    external_link = forms.URLField(label="External Link", required=False, help_text="Optional link with more information")

    def __init__(self, job=None, user=None, *args, **kwargs):
        self.job = job
        self.user = user
        super(JobForm, self).__init__(*args, **kwargs)

        not_trusted = self.user.is_authenticated and (not self.user.profile.trusted)

        # Untrusted users get a recaptcha field
        if settings.RECAPTCHA_PRIVATE_KEY and not_trusted:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())

    def edit(self):
        """
        Edit an existing job.
        """
        if self.user != self.job.author and not self.user.profile.is_moderator:
            raise forms.ValidationError("Only the author or a moderator can edit a job.")
        data = self.cleaned_data
        self.job.title = data.get('title')
        self.job.content = data.get("content")
        self.job.apply_before = data.get('apply_before')
        self.job.institution = data.get('institution')
        self.job.external_link = data.get('external_link')
        self.job.save()
        return self.job

    def clean_content(self):
        content = self.cleaned_data["content"]
        length = len(content.replace(" ", ""))

        if length < MIN_CHARS:
            raise forms.ValidationError(f"Too short, place add more than {MIN_CHARS}")

        return content

class InvitePeersForm(forms.Form):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    def save(self, request):
        context = {
            'email': self.cleaned_data['email'],
            'sender': request.user,
            'first_name': self.cleaned_data['first_name'],
            'last_name': self.cleaned_data['last_name'],
            'protocol': 'https' if request.is_secure() else "http",
            'domain': request.get_host(),
        }
        html = render_to_string('invitations/invite.html', context)
        text = render_to_string('invitations/invite.txt', context)
        send_mail(
            'Invitation to 360Med Network',
            message=text,
            html_message=html,
            recipient_list=[self.cleaned_data['email']],
            from_email=settings.DEFAULT_FROM_EMAIL,
            fail_silently=False,
        )
