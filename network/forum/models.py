import logging
from django.utils import timezone

import bleach
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db import models
from django.db.models import Q
from django.shortcuts import reverse
from taggit.managers import TaggableManager
from network.accounts.models import Profile
from . import util

User = get_user_model()

# The maximum length in characters for a typical name and text field.
MAX_NAME_LEN = 256
MAX_FIELD_LEN = 1024
MAX_TEXT_LEN = 10000
MAX_LOG_LEN = 20 * MAX_TEXT_LEN

logger = logging.getLogger("engine")


class PostManager(models.Manager):

    def valid_posts(self, u=None, **kwargs):
        """
        Returns posts that are not closed or marked as spam.
        """
        query = super().get_queryset().filter(**kwargs)
        query = query.exclude(Q(root=None) | Q(parent=None))

        # Moderators get to see all posts by default.
        if u and u.is_authenticated and u.profile.is_moderator:
            return query

        # Filter for open posts that are not spam.
        query = query.filter(status=Post.OPEN, root__status=Post.OPEN)
        query = query.filter(models.Q(spam=Post.NOT_SPAM) | models.Q(spam=Post.DEFAULT) |
                             models.Q(root__spam=Post.NOT_SPAM) | models.Q(root__spam=Post.DEFAULT))

        query = query.exclude(root=None)

        return query

    def old(self, **kwargs):
        """
        Return posts that were transferred over from an older verion of networks
        """
        query = super().get_queryset().exclude(uid__contains='p').filter(**kwargs)
        return query


class AwardManager(models.Manager):

    def valid_awards(self):
        """
        Returns queryset with valid posts.
        """
        query = super().get_queryset()
        # Filter for valid users
        query = query.filter(user__profile__state__in=[Profile.NEW, Profile.TRUSTED])

        # Filter for valid posts
        query = query.filter(models.Q(post__status=Post.OPEN) | models.Q(post__root__status=Post.OPEN))

        return query


class Sync(models.Model):

    last_synced = models.DateTimeField(null=True)


class Post(models.Model):
    "Represents a post in a forum"

    # Post statuses.
    PENDING, OPEN, OFFTOPIC, CLOSED, DELETED = range(5)
    STATUS_CHOICES = [(PENDING, "Pending"), (OPEN, "Open"), (OFFTOPIC, "Off topic"), (CLOSED, "Closed"),
                      (DELETED, "Deleted")]

    # Question types. Answers should be listed before comments.
    QUESTION, ANSWER, JOB, FORUM, PAGE, EVENT, BLOG, COMMENT, DATA, TUTORIAL, BOARD, TOOL, NEWS = range(13)

    # Valid post types.
    TYPE_CHOICES = [
        (FORUM, "Forum"), (QUESTION, "Question"), (EVENT, "Event"), (JOB, "Job"),
        (ANSWER, "Answer"), (COMMENT, "Comment"),
    ]
    TOP_LEVEL = {FORUM, EVENT, JOB}

    # Possile spam states.
    SPAM, NOT_SPAM, DEFAULT, SUSPECT = range(4)
    SPAM_CHOICES = [(SPAM, "Spam"), (NOT_SPAM, "Not spam"), (SUSPECT, "Quarantine"), (DEFAULT, "Default")]
    # Spam labeling.
    spam = models.IntegerField(choices=SPAM_CHOICES, default=DEFAULT)

    # Spam score stores relative likely hood this post is spam.
    spam_score = models.FloatField(default=0)

    # Post status: open, closed, deleted.
    status = models.IntegerField(choices=STATUS_CHOICES, default=OPEN, db_index=True)

    # The type of the post: question, answer, comment.
    type = models.IntegerField(choices=TYPE_CHOICES, db_index=True)

    # Post title.
    title = models.CharField(max_length=200, null=False, db_index=True)

    # The user that originally created the post.
    author = models.ForeignKey(User, on_delete=models.CASCADE)

    # The user that edited the post most recently.
    lastedit_user = models.ForeignKey(User, related_name='editor', null=True,
                                      on_delete=models.CASCADE)

    # The user that last contributed to the thread.
    last_contributor = models.ForeignKey(User, related_name='contributor', null=True,
                                         on_delete=models.CASCADE)

    # Store users contributing to the thread as "tags" to preform_search later.
    thread_users = models.ManyToManyField(User, related_name="thread_users")

    # Indicates the information value of the post.
    rank = models.FloatField(default=0, blank=True, db_index=True)

    # This post has been indexed by the search engine.
    indexed = models.BooleanField(default=False)

    # Used for efficiency
    #is_public_toplevel = models.BooleanField(default=False)

    # Show that post is top level
    is_toplevel = models.BooleanField(default=False, db_index=True)

    # Indicates whether the post has accepted answer.
    answer_count = models.IntegerField(default=0, blank=True, db_index=True)

    # The number of accepted answers.
    accept_count = models.IntegerField(default=0, blank=True)

    # The number of replies for  thread.
    reply_count = models.IntegerField(default=0, blank=True, db_index=True)

    # The number of comments that a post has.
    comment_count = models.IntegerField(default=0, blank=True)

    # Number of upvotes for the post
    vote_count = models.IntegerField(default=0, blank=True, db_index=True)

    # The total numbers of votes for a top-level post.
    thread_votecount = models.IntegerField(default=0, db_index=True)

    # The number of views for the post.
    view_count = models.IntegerField(default=0, blank=True, db_index=True)

    # Bookmark count.
    book_count = models.IntegerField(default=0)

    # How many people follow that thread.
    subs_count = models.IntegerField(default=0)

    # Post creation date.
    creation_date = models.DateTimeField(db_index=True)

    # Post last edit date.
    lastedit_date = models.DateTimeField(db_index=True)

    # Sticky posts go on top.
    sticky = models.BooleanField(default=False)

    # This will maintain the ancestor/descendant relationship bewteen posts.
    root = models.ForeignKey('self', related_name="descendants", null=True, blank=True, on_delete=models.SET_NULL)

    # This will maintain parent/child relationships between posts.
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.SET_NULL)

    # This is the text that the user enters.
    content = models.TextField(default='')

    # This is the  HTML that gets displayed.
    html = models.TextField(default='')

    # The tag value is the canonical form of the post's tags
    tag_val = models.CharField(max_length=100, default="", blank=True, verbose_name="Spaces")

    # The tag set is built from the tag string and used only for fast filtering
    tags = TaggableManager()

    # What site does the post belong to.
    site = models.ForeignKey(Site, null=True, on_delete=models.SET_NULL)

    # Unique id for the post.
    uid = models.CharField(max_length=32, unique=True, db_index=True)

    objects = PostManager()

    def parse_tags(self):
        return [tag.lower() for tag in self.tag_val.split(",") if tag]

    @property
    def get_votecount(self):

        if self.is_toplevel:
            return self.thread_votecount
        return self.vote_count

    def title_prefix(self):

        prefix = ""
        if self.is_spam:
            prefix = "Spam:"
        elif self.suspect_spam:
            prefix = "Quarantined: "
        elif not self.is_open or not self.is_question:
            prefix = f"{self.get_type_display()}:" if self.is_open else f"{self.get_status_display()}:"

        return prefix

    @property
    def suspect_spam(self):
        return self.spam == self.SUSPECT


    @property
    def is_open(self):
        return self.status == Post.OPEN and not self.is_spam and not self.suspect_spam

    def recompute_scores(self):
        # Recompute answers count
        if self.type == Post.ANSWER:
            answer_count = Post.objects.filter(root=self.root, type=Post.ANSWER).count()
            Post.objects.filter(pk=self.parent_id).update(answer_count=answer_count)

        reply_count = Post.objects.filter(root=self.root).count()
        Post.objects.filter(pk=self.root.id).update(reply_count=reply_count)

    def json_data(self):
        data = {
            'id': self.id,
            'uid': self.uid,
            'title': self.title,
            'type': self.get_type_display(),
            'type_id': self.type,
            'creation_date': util.datetime_to_iso(self.creation_date),
            'lastedit_date': util.datetime_to_iso(self.lastedit_date),
            'lastedit_user_id': self.lastedit_user.id,
            'author_id': self.author.id,
            'author_uid': self.author.profile.uid,
            'lastedit_user_uid': self.lastedit_user.profile.uid,
            'author': self.author.name,
            'status': self.get_status_display(),
            'status_id': self.status,
            'thread_score': self.thread_votecount,
            'rank': self.rank,
            'vote_count': self.vote_count,
            'view_count': self.view_count,
            'reply_count': self.reply_count,
            'comment_count': self.comment_count,
            'book_count': self.book_count,
            'subs_count': self.subs_count,
            'answer_count': self.root.reply_count,
            'has_accepted': self.has_accepted,
            'parent_id': self.parent.id,
            'root_id': self.root_id,
            'xhtml': self.html,
            'content': self.content,
            'tag_val': self.tag_val,
            'url': f'{settings.PROTOCOL}://{settings.SITE_DOMAIN}{self.get_absolute_url()}',
        }
        return data

    @property
    def is_question(self):
        return self.type == Post.QUESTION

    @property
    def is_job(self):
        return self.type == Post.JOB

    @property
    def is_deleted(self):
        return self.status == Post.DELETED

    @property
    def not_spam(self):
        return self.spam == Post.NOT_SPAM

    @property
    def has_accepted(self):
        return bool(self.accept_count)

    def num_lines(self, offset=0):
        """
        Return number of lines in post content
        """
        return len(self.content.split("\n")) + offset

    @property
    def is_spam(self):
        return self.spam == self.SPAM

    @property
    def is_comment(self):
        return self.type == Post.COMMENT

    @property
    def is_answer(self):
        return self.type == Post.ANSWER

    def get_absolute_url(self):
        url = reverse("post_view", kwargs=dict(uid=self.root.uid))
        return url if self.is_toplevel else "%s#%s" % (url, self.uid)

    def high_spam_score(self, threshold=None):
        threshold = threshold or settings.SPAM_THRESHOLD
        return (self.spam_score > threshold) or self.is_spam or self.author.profile.low_rep

    def save(self, *args, **kwargs):

        # Needs to be imported here to avoid circular imports.
        from network.forum import markdown

        self.lastedit_user = self.lastedit_user or self.author

        self.creation_date = self.creation_date or util.now()
        self.lastedit_date = self.lastedit_date or util.now()
        self.last_contributor = self.lastedit_user

        # Sanitize the post body.
        self.html = markdown.parse(self.content, post=self, clean=True, escape=False)
        self.tag_val = self.tag_val.replace(' ', '')
        # Default tags
        self.tag_val = self.tag_val or "tag1, tag2,"
        # Set the top level state of the post.
        self.is_toplevel = self.type in Post.TOP_LEVEL

        # This will trigger the signals
        super(Post, self).save(*args, **kwargs)

    def __str__(self):
        return "%s: %s (pk=%s)" % (self.get_type_display(), self.title, self.pk)

    def update_parent_counts(self):
        """
        Update the counts for the parent and root
        """

        descendants = Post.objects.filter(root=self.root).exclude(Q(pk=self.root.pk) | Q(status=Post.DELETED)
                                                                  | Q(spam=Post.SPAM))
        answer_count = descendants.filter(type=Post.ANSWER).count()
        comment_count = descendants.filter(type=Post.COMMENT).count()
        reply_count = descendants.count()
        # Update the root reply, answer, and comment counts.
        Post.objects.filter(pk=self.root.pk).update(reply_count=reply_count, answer_count=answer_count,
                                                    comment_count=comment_count)

        children = Post.objects.filter(parent=self.parent).exclude(pk=self.parent.pk)
        com_count = children.filter(type=Post.COMMENT).count()

        # Update parent reply, answer, and comment counts.
        Post.objects.filter(pk=self.parent.pk, is_toplevel=False).update(comment_count=com_count, answer_count=0,
                                                                         reply_count=children.count())

    @property
    def css(self):
        # Used to simplify CSS rendering.
        status = self.get_status_display()
        if self.is_spam:
            return "spam"
        if self.suspect_spam:
            return "quarantine"

        return f"{status}".lower()

    @property
    def accepted_class(self):
        if self.status == Post.DELETED:
            return "deleted"
        if self.has_accepted and not self.is_toplevel:
            return "accepted"
        return ""

    @property
    def age_in_days(self):
        delta = util.now() - self.creation_date
        return delta.days


class Vote(models.Model):
    # Post statuses.

    UP, DOWN, BOOKMARK, ACCEPT, EMPTY = range(5)

    TYPE_CHOICES = [(UP, "Upvote"), (EMPTY, "Empty"),
                    (DOWN, "DownVote"), (BOOKMARK, "Bookmark"), (ACCEPT, "Accept")]

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='votes', on_delete=models.CASCADE)
    type = models.IntegerField(choices=TYPE_CHOICES, default=EMPTY, db_index=True)
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    uid = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return u"Vote: %s, %s, %s" % (self.post_id, self.author_id, self.get_type_display())

    def save(self, *args, **kwargs):
        self.uid = self.uid or util.get_uuid(limit=16)

        super(Vote, self).save(*args, **kwargs)


class PostView(models.Model):
    """
    Keeps track of post views based on IP address.
    """
    ip = models.GenericIPAddressField(default='', null=True, blank=True)
    post = models.ForeignKey(Post, related_name="post_views", on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)


class Subscription(models.Model):
    "Connects a post to a user"

    LOCAL_MESSAGE, EMAIL_MESSAGE, NO_MESSAGES = range(3)
    SUB_CHOICES = [(LOCAL_MESSAGE, "Local messages"), (EMAIL_MESSAGE, "Email message"), (NO_MESSAGES, "Not subscribed")]
    TYPE_MAP = {Profile.NO_MESSAGES: NO_MESSAGES,
                Profile.EMAIL_MESSAGE: EMAIL_MESSAGE,
                Profile.LOCAL_MESSAGE: LOCAL_MESSAGE,
                Profile.DEFAULT_MESSAGES: LOCAL_MESSAGE}
    class Meta:
        unique_together = (("user", "post"))

    uid = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name="subs", on_delete=models.CASCADE)
    type = models.IntegerField(choices=SUB_CHOICES, null=True, default=LOCAL_MESSAGE)
    date = models.DateTimeField()

    def __str__(self):
        return f"{self.user.profile.name} to {self.post.title}"

    def save(self, *args, **kwargs):
        # Set the date to current time if missing.
        self.date = self.date or util.now()
        self.uid = self.uid or util.get_uuid(limit=16)

        if self.type is None:
            self.type = self.TYPE_MAP.get(self.user.profile.message_prefs, self.NO_MESSAGES)

        super(Subscription, self).save(*args, **kwargs)

    def profile_type_mapper(self):
        type_map = {Profile.NO_MESSAGES: self.NO_MESSAGES,
                    Profile.EMAIL_MESSAGE: self.EMAIL_MESSAGE,
                    Profile.LOCAL_MESSAGE: self.LOCAL_MESSAGE,
                    Profile.DEFAULT_MESSAGES: self.LOCAL_MESSAGE}
        return type_map

    @staticmethod
    def get_sub(post, user):
        sub = Subscription.objects.filter(post=post, user=user).first()
        return None if user.is_anonymous else sub


class Badge(models.Model):
    BRONZE, SILVER, GOLD = range(3)
    CHOICES = ((BRONZE, 'Bronze'), (SILVER, 'Silver'), (GOLD, 'Gold'))

    # The name of the badge.
    name = models.CharField(max_length=50)

    # The description of the badge.
    desc = models.CharField(max_length=200, default='')

    # The rarity of the badge.
    type = models.IntegerField(choices=CHOICES, default=BRONZE)

    # The icon to display for the badge.
    icon = models.CharField(default='', max_length=250)

    uid = models.CharField(max_length=32, unique=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Set the date to current time if missing.
        self.uid = self.uid or util.get_uuid(limit=8)
        super(Badge, self).save(*args, **kwargs)


class Award(models.Model):
    '''
    A badge being awarded to a user.Cannot be ManyToManyField
    because some may be earned multiple times
    '''
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, null=True, on_delete=models.SET_NULL)
    date = models.DateTimeField()
    # context = models.CharField(max_length=1000, default='')
    uid = models.CharField(max_length=32, unique=True)

    objects = AwardManager()

    def save(self, *args, **kwargs):
        # Set the date to current time if missing.
        self.uid = self.uid or util.get_uuid(limit=16)
        super(Award, self).save(*args, **kwargs)

class Space(models.Model):
    """ Creates spaces that users can subscribe to """
    # Space name.
    name = models.CharField(max_length=200, null=False, db_index=True)
    # Space description
    description = models.TextField()
    # The user that originally created the space.
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    # Users following this space or contributing to it
    users_following = models.ManyToManyField(User, related_name="following_users")
    # Space creation date.
    creation_date = models.DateTimeField(db_index=True)
    # Posts assigned to space
    posts = models.ManyToManyField(Post, related_name="space_posts")

    def json_data(self):
        data = {
            "id": self.id,
            "uid": self.uid,
            "name": self.name,
            "description": self.description,
            "creator": self.creator,
            "posts": self.posts,
            "creation_date": self.creation_date,
        }
        return data

    def get_absolute_url(self):
        url = reverse("space_view", kwargs=dict(uid=self.root.uid))
        return url if self.is_toplevel else "%s#%s" % (url, self.uid)

class Event(models.Model):
    "Represents an event"

    # Event title.
    title = models.CharField(max_length=200, null=False, db_index=True)

    # The user that originally created the event.
    author = models.ForeignKey(User, on_delete=models.CASCADE)

    # The user that last edited the event 
    lastedit_user = models.ForeignKey(User, related_name='event_editor', null=True,
                                      on_delete=models.CASCADE)

    # This is the text that the user enters.
    content = models.TextField(default='')

    # This is the  HTML that gets displayed.
    html = models.TextField(default='')

    # Location of the event
    location = models.CharField(max_length=200, null=False, default='', db_index=True)

    # day of the event
    event_date = models.DateTimeField(default=timezone.now, db_index=True)

    # external link to the event
    external_link = models.URLField(default='', null=True, blank=True)

    # The tag value is the canonical form of the event's tags
    tag_val = models.CharField(max_length=100, default="", blank=True, verbose_name="tags")

    # The tag set is built from the tag string and used only for fast filtering
    tags = TaggableManager()

    # Event creation date.
    creation_date = models.DateTimeField(db_index=True)

    # Unique id for the event.
    uid = models.CharField(max_length=32, unique=True, db_index=True)

    def parse_tags(self):
        return [tag.lower() for tag in self.tag_val.split(",") if tag]

    def json_data(self):
        data = {
            'id': self.id,
            'uid': self.uid,
            'title': self.title,
            'creation_date': util.datetime_to_iso(self.creation_date),
            'lastedit_user_id': self.lastedit_user.id,
            'author_id': self.author.id,
            'author_uid': self.author.profile.uid,
            'lastedit_user_uid': self.lastedit_user.profile.uid,
            'author': self.author.name,
            'xhtml': self.html,
            'content': self.content,
            'location': self.location,
            'external_link': self.external_link,
            'event_date': self.event_date,
            'tag_val': self.tag_val,
            'url': f'{settings.PROTOCOL}://{settings.SITE_DOMAIN}{self.get_absolute_url()}',
        }
        return data

    def num_lines(self, offset=0):
        """
        Return number of lines in event content
        """
        return len(self.content.split("\n")) + offset

    def get_absolute_url(self):
        url = reverse("event_view", kwargs=dict(uid=self.uid))
        return "%s#%s" % (url, self.uid)

    def save(self, *args, **kwargs):

        # Needs to be imported here to avoid circular imports.
        from network.forum import markdown

        self.lastedit_user = self.lastedit_user or self.author
        self.creation_date = self.creation_date or util.now()
        self.uid = self.uid or util.get_uuid(limit=16)
        self.location = self.location
        self.external_link = self.external_link

        # Sanitize the event body.
        self.html = markdown.parse(self.content, event=self, clean=True, escape=False)
        self.tag_val = self.tag_val.replace(' ', '')
        # Default tags
        self.tag_val = self.tag_val or "workshop, tutorial,"

        # This will trigger the signals
        super(Event, self).save(*args, **kwargs)

    def __str__(self):
        return "%s (pk=%s)" % (self.title, self.pk)

    @property
    def age_in_days(self):
        delta = util.now() - self.creation_date
        return delta.days

class Job(models.Model):
    "Represents a job"

    # Job title.
    title = models.CharField(max_length=200, null=False, db_index=True)

    # The user that originally created the job.
    author = models.ForeignKey(User, on_delete=models.CASCADE)

    # This is the text that the user enters.
    content = models.TextField(default='')

    # This is the  HTML that gets displayed.
    html = models.TextField(default='')

    # Hiring institution
    institution = models.CharField(max_length=200, null=False, default='', db_index=True)

    # deadline
    apply_before = models.DateTimeField(default=timezone.now, db_index=True)

    # external link to the job
    external_link = models.URLField(default='',null=True, blank=True)

    # Job creation date.
    creation_date = models.DateTimeField(db_index=True)

    # Unique id for the job.
    uid = models.CharField(max_length=32, unique=True, db_index=True)

    def json_data(self):
        data = {
            'id': self.id,
            'uid': self.uid,
            'title': self.title,
            'creation_date': util.datetime_to_iso(self.creation_date),
            'author_id': self.author.id,
            'author_uid': self.author.profile.uid,
            'author': self.author.name,
            'xhtml': self.html,
            'content': self.content,
            'institution': self.institution,
            'external_link': self.external_link,
            'apply_before': self.apply_before,
            'url': f'{settings.PROTOCOL}://{settings.SITE_DOMAIN}{self.get_absolute_url()}',
        }
        return data

    def num_lines(self, offset=0):
        """
        Return number of lines in job description
        """
        return len(self.content.split("\n")) + offset

    def get_absolute_url(self):
        url = reverse("job_view", kwargs=dict(uid=self.uid))
        return "%s#%s" % (url, self.uid)

    def save(self, *args, **kwargs):

        # Needs to be imported here to avoid circular imports.
        from network.forum import markdown

        self.creation_date = self.creation_date or util.now()

        # Sanitize the job body.
        self.html = markdown.parse(self.content, job=self, clean=True, escape=False)

        # This will trigger the signals
        super(Job, self).save(*args, **kwargs)

    def __str__(self):
        return "%s (pk=%s)" % (self.title, self.pk)

    @property
    def age_in_days(self):
        delta = util.now() - self.creation_date
        return delta.days