import logging
from datetime import timedelta
from functools import wraps, lru_cache
import os
from django.utils import timezone

from django.db import models, connections
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, reverse
from django.core.cache import cache
from ratelimit.decorators import ratelimit
from taggit.models import Tag

from network.accounts.models import Profile
from network.forum import forms, auth, tasks, util, search
from network.forum.const import *
from network.forum.models import Post, Event, Job, Vote, Badge


User = get_user_model()

logger = logging.getLogger('engine')

RATELIMIT_KEY = settings.RATELIMIT_KEY

# Valid post values as they correspond to database post types.
POST_TYPE_MAPPER = dict(
    forum=Post.FORUM,
    event=Post.EVENT,
    news=Post.NEWS,
    job=Post.JOB,
    blog=Post.BLOG,
    tool=Post.TOOL,
    question=Post.QUESTION,
    tutorial=Post.TUTORIAL
)

LIMIT_MAP = dict(
    all=0,
    today=1,
    week=7,
    month=30,
    year=365
)

def post_exists(func):
    """
    Ensure uid passed to view function exists.
    """
    @wraps(func)
    def _wrapper_(request, **kwargs):
        uid = kwargs.get('uid')
        post = Post.objects.filter(uid=uid).exists()
        if not post:
            messages.error(request, "Post does not exist.")
            return redirect(reverse("post_list"))
        return func(request, **kwargs)
    return _wrapper_


class CachedPaginator(Paginator):
    """
    Paginator that caches the count call.
    """

    # Time to live for the cache, in seconds
    TTL = 300

    def __init__(self, cache_key='', ttl=None, *args, **kwargs):
        self.cache_key = cache_key
        self.ttl = ttl or self.TTL
        super(CachedPaginator, self).__init__(*args, **kwargs)

    @property
    def count(self):

        if self.cache_key:
            value = cache.get(self.cache_key) or super(CachedPaginator, self).count
            cache.add(self.cache_key, value, self.ttl)
        else:
            value = super(CachedPaginator, self).count

        return value


def get_posts(user, topic="", tag="", order="", limit=None):
    """
    Generates a post list on a topic.
    """
    # Topics are case insensitive.
    topic = topic or LATEST
    topic = topic.lower()

    # Detect known post types.
    post_type = POST_TYPE_MAPPER.get(topic)
    query = Post.objects.valid_posts(u=user, is_toplevel=True)

    # Determines how to start the preform_search.
    if post_type:
        query = query.filter(type=post_type)
    elif topic == OPEN:
        query = query.filter(type=Post.QUESTION, answer_count=0)
    elif topic == BOOKMARKS and user.is_authenticated:
        query = query.filter(votes__author=user, votes__type=Vote.BOOKMARK)
    elif topic == FOLLOWING and user.is_authenticated:
        query = query.filter(subs__user=user)
    elif topic == MYPOSTS and user.is_authenticated:
        query = query.filter(author=user)
    elif topic == MYVOTES and user.is_authenticated:
        query = query.filter(votes__post__author=user)
    elif topic == MYTAGS and user.is_authenticated:
        tags = user.profile.my_tags.split(",")
        query = query.filter(tags__name__in=tags)

    if user.is_anonymous or not user.profile.is_moderator:
        query = query.exclude(Q(spam=Post.SPAM) | Q(status=Post.DELETED))
    # Filter by tags if specified.
    if tag:
        query = query.filter(tags__name=tag.lower())

    # Apply post ordering.
    if ORDER_MAPPER.get(order):
        ordering = ORDER_MAPPER.get(order)
        query = query.order_by(ordering)
    else:
        query = query.order_by("-rank")

    days = LIMIT_MAP.get(limit, 0)
    # Apply time limit if required.
    if days:
        delta = util.now() - timedelta(days=days)
        query = query.filter(lastedit_date__gt=delta)

    # Select related information used during rendering.
    query = query.select_related("root").select_related("author__profile", "lastedit_user__profile")

    return query

def get_events(user, tag="", order="", limit=None):
    """
    Generates a post list on a topic.
    """
    query = Event.objects.all()

    if tag:
        query = query.filter(tags__name=tag.lower())

    # Apply post ordering.
    if ORDER_MAPPER.get(order):
        ordering = ORDER_MAPPER.get(order)
        query = query.order_by(ordering)
    else:
        query = query.order_by("-creation_date")

    days = LIMIT_MAP.get(limit, 0)
    # Apply time limit if required.
    if days:
        delta = util.now() - timedelta(days=days)
        query = query.filter(lastedit_date__gt=delta)

    # Select related information used during rendering.
    query = query.select_related("author__profile", "lastedit_user__profile")

    return query

def get_jobs(user, tag="", order="", limit=None):
    """
    Generates a post list on a topic.
    """
    query = Job.objects.all()

    if tag:
        query = query.filter(tags__name=tag.lower())

    # Apply post ordering.
    if ORDER_MAPPER.get(order):
        ordering = ORDER_MAPPER.get(order)
        query = query.order_by(ordering)
    else:
        query = query.order_by("-creation_date")

    days = LIMIT_MAP.get(limit, 0)
    # Apply time limit if required.
    if days:
        delta = util.now() - timedelta(days=days)
        query = query.filter(lastedit_date__gt=delta)

    # Select related information used during rendering.
    query = query.select_related("author__profile")

    return query

def post_search(request):

    query = request.GET.get('query', '')
    length = len(query.replace(" ", ""))
    page = int(request.GET.get('page', 1))

    if length < settings.SEARCH_CHAR_MIN:
        messages.error(request, "Enter more characters before preforming search.")
        return redirect(reverse('post_list'))

    results = search.preform_whoosh_search(query=query, page=page, sortedby=["lastedit_date"])

    total = results.total
    template_name = "search/search_results.html"

    question_flag = Post.QUESTION
    context = dict(results=results, query=query, total=total, template_name=template_name,
                   question_flag=question_flag, stop_words=','.join(search.STOP))

    return render(request, template_name=template_name, context=context)


def pages(request, fname):

    # Add markdown file extension to markdown
    infile = f"{fname}.md"
    # Look for this file in static root.
    doc = os.path.join(settings.STATIC_ROOT, "forum", infile)

    if not os.path.exists(doc):
        messages.error(request, "File does not exist.")
        return redirect("post_list")

    admins = User.objects.filter(is_superuser=True)
    mods = User.objects.filter(profile__role=Profile.MODERATOR).exclude(id__in=admins)
    admins = admins.prefetch_related("profile").order_by("-profile__score")
    mods = mods.prefetch_related("profile").order_by("-profile__score")
    context = dict(file_path=doc, tab=fname, admins=admins, mods=mods)

    return render(request, 'pages.html', context=context)

@login_required # hack to ensure post_list view is locked so users need accounts first
@ensure_csrf_cookie
def post_list(request, topic=None, cache_key='', extra_context=dict()):
    """
    Post listing. Filters, orders and paginates posts based on GET parameters.
    """
    # The user performing the request.
    user = request.user

    # Parse the GET parameters for filtering information
    page = request.GET.get('page', 1)
    order = request.GET.get("order", "")
    tag = request.GET.get("tag", "")
    topic = topic or request.GET.get("type", "")
    limit = request.GET.get("limit", "")

    # Get posts available to users.
    posts = get_posts(user=user, topic=topic, tag=tag, order=order, limit=limit)

    # Create the paginator.
    paginator = CachedPaginator(cache_key=cache_key, object_list=posts, per_page=settings.POSTS_PER_PAGE)

    # Apply the post paging.
    posts = paginator.get_page(page)

    # Set the active tab.
    tab = tag or topic or LATEST

    # Fill in context.
    context = dict(posts=posts, tab=tab, tag=tag, order=order, type=topic, limit=limit, avatar=True)
    context.update(extra_context)
    # Render the page.
    return render(request, template_name="post_list.html", context=context)


@login_required # hack to ensure post_list view is locked so users need accounts first
@ensure_csrf_cookie
def event_list(request, cache_key='', extra_context=dict()):
    """
    Post listing. Filters, orders and paginates posts based on GET parameters.
    """
    # The user performing the request.
    user = request.user

    # Parse the GET parameters for filtering information
    page = request.GET.get('page', 1)
    order = request.GET.get("order", "")
    tag = request.GET.get("tag", "")
    limit = request.GET.get("limit", "")

    # Get posts available to users.
    events = get_events(user=user, tag=tag, order=order, limit=limit)

    # Create the paginator.
    paginator = CachedPaginator(cache_key=cache_key, object_list=events, per_page=settings.POSTS_PER_PAGE)

    # Apply the post paging.
    events = paginator.get_page(page)

    # Set the active tab.
    tab = tag

    # Fill in context.
    context = dict(events=events, tab=tab, tag=tag, order=order, limit=limit, avatar=True)
    context.update(extra_context)
    # Render the page.
    return render(request, template_name="event_list.html", context=context)


@login_required # hack to ensure post_list view is locked so users need accounts first
@ensure_csrf_cookie
def job_list(request, cache_key='', extra_context=dict()):
    """
    Job listing. Filters, orders and paginates jobs based on GET parameters.
    """
    # The user performing the request.
    user = request.user

    # Parse the GET parameters for filtering information
    page = request.GET.get('page', 1)
    order = request.GET.get("order", "")
    tag = request.GET.get("tag", "")
    limit = request.GET.get("limit", "")

    # Get posts available to users.
    jobs = get_jobs(user=user, tag=tag, order=order, limit=limit)

    # Create the paginator.
    paginator = CachedPaginator(cache_key=cache_key, object_list=jobs, per_page=settings.POSTS_PER_PAGE)

    # Apply the post paging.
    jobs = paginator.get_page(page)

    # Set the active tab.
    tab = tag

    # Fill in context.
    context = dict(jobs=jobs, tab=tab, tag=tag, order=order, limit=limit, avatar=True)
    context.update(extra_context)
    # Render the page.
    return render(request, template_name="job_list.html", context=context)


@ratelimit(key=RATELIMIT_KEY,  rate='100/m')
def latest(request):
    """
    Show latest post listing.
    """
    # first check if user is logged in and has finished registration
    if not request.user.is_authenticated:
        return redirect('login')
    elif not request.user.profile.has_finished_registration:
        return redirect('onboarding')

    order = request.GET.get("order", "")
    tag = request.GET.get("tag", "")
    topic = request.GET.get("type", "")
    limit = request.GET.get("limit", "")

    # Only cache unfiltered posts.
    cache_off = (order or limit or tag or topic)
    cache_key = None if cache_off else LATEST_CACHE_KEY

    return post_list(request, cache_key=cache_key)


def authenticated(func):
    def _wrapper_(request, **kwargs):
        if request.user.is_anonymous:
            messages.error(request, "You need to be logged in to view this page.")
            return reverse('post_list')
        return func(request, **kwargs)
    return _wrapper_


@authenticated
def myvotes(request):
    """
    Show posts by user that received votes
    """
    page = request.GET.get('page', 1)
    votes = Vote.objects.filter(post__author=request.user).prefetch_related('post', 'post__root',
                                                                            'author__profile').order_by("-date")
    # Create the paginator
    paginator = CachedPaginator(object_list=votes, per_page=settings.POSTS_PER_PAGE)

    # Apply the votes paging.
    votes = paginator.get_page(votes)

    context = dict(votes=votes, page=page, tab='myvotes')
    return render(request, template_name="votes_list.html", context=context)


def tags_list(request):
    """
    Show posts by user
    """
    page = request.GET.get('page', 1)
    query = request.GET.get('query', '')

    count = Count('post', filter=Q(post__is_toplevel=True))

    db_query = Q(name__icontains=query) if query else Q()
    cache_key = None if query else TAGS_CACHE_KEY

    tags = Tag.objects.annotate(nitems=count).filter(db_query)
    tags = tags.order_by('-nitems')

    # Create the paginator
    paginator = CachedPaginator(cache_key=cache_key, object_list=tags,
                                per_page=settings.POSTS_PER_PAGE)

    # Apply the votes paging.
    tags = paginator.get_page(page)

    context = dict(tags=tags, tab='tags', query=query)

    return render(request, 'tags_list.html', context=context)


@authenticated
def myposts(request):
    """
    Show posts by user
    """

    return post_list(request, topic=MYPOSTS)


@authenticated
def following(request):
    """
    Show posts followed by user
    """
    return post_list(request, topic=FOLLOWING)


@authenticated
def bookmarks(request):
    """
    Show posts bookmarked by user
    """
    return post_list(request, topic=BOOKMARKS)


@authenticated
def mytags(request):

    return post_list(request=request, topic=MYTAGS)


def community_list(request):

    users = User.objects.select_related("profile")

    page = request.GET.get("page", 1)
    ordering = request.GET.get("order", "visit")
    limit_to = request.GET.get("limit", "time")
    query = request.GET.get('query', '')
    query = query.replace("'", "").replace('"', '').strip()

    days = LIMIT_MAP.get(limit_to, 0)

    if days:
        delta = util.now() - timedelta(days=days)
        users = users.filter(profile__last_login__gt=delta)

    if query and len(query) > 2:
        db_query = Q(profile__name__icontains=query) | Q(profile__uid__icontains=query) | \
                   Q(username__icontains=query) | Q(email__icontains=query)
        users = users.filter(db_query)

    # Remove the cache when filters are given.
    no_cache = days or (query and len(query) > 2) or ordering
    cache_key = None if no_cache else USERS_LIST_KEY

    order = ORDER_MAPPER.get(ordering, "visit")
    users = users.filter(profile__state__in=[Profile.NEW, Profile.TRUSTED])
    users = users.order_by(order)

    # Create the paginator
    paginator = CachedPaginator(cache_key=cache_key, object_list=users,
                                per_page=settings.POSTS_PER_PAGE)
    users = paginator.get_page(page)
    context = dict(tab="community", users=users, query=query, order=ordering, limit=limit_to)

    return render(request, "community_list.html", context=context)


def badge_list(request):
    badges = Badge.objects.annotate(count=Count("award"))
    context = dict(badges=badges)
    return render(request, "badge_list.html", context=context)


def badge_view(request, uid):
    badge = Badge.objects.filter(uid=uid).annotate(count=Count("award")).first()

    if not badge:
        messages.error(request, f"Badge with id={uid} does not exist.")
        return redirect(reverse("badge_list"))

    awards = badge.award_set.valid_awards().order_by("-pk")[:100]

    awards = awards.prefetch_related("user", "user__profile", "post", "post__root")
    context = dict(awards=awards, badge=badge)

    return render(request, "badge_view.html", context=context)


@ensure_csrf_cookie
def post_view(request, uid):
    "Return a detailed view for specific post"

    # Get the post.
    post = Post.objects.filter(uid=uid).select_related('root').first()

    if not post:
        messages.error(request, "Post does not exist.")
        return redirect("post_list")

    auth.update_post_views(post=post, request=request)
    if not post.is_toplevel:
        return redirect(post.get_absolute_url())

    # Form used for answers
    form = forms.PostShortForm(user=request.user, post=post)

    if request.method == "POST":

        form = forms.PostShortForm(data=request.POST, user=request.user, post=post)
        if form.is_valid():
            author = request.user
            content = form.cleaned_data.get("content")
            answer = auth.create_post(title=post.title, parent=post, author=author,
                                      content=content, ptype=Post.ANSWER, root=post.root)
            return redirect(answer.get_absolute_url())
        messages.error(request, form.errors)

    # Build the comment tree .
    root, comment_tree, answers, thread = auth.post_tree(user=request.user, root=post.root)
    # user string
    users_str = auth.get_users_str()

    context = dict(post=root, tree=comment_tree, form=form, answers=answers, users_str=users_str)

    return render(request, "post_view.html", context=context)

def activity_feed(request):
    return render(request, "activity_feed.html")

@ensure_csrf_cookie
def event_view(request, uid):
    "Return a detailed view for specific post"

    # Get the post.
    event = Event.objects.filter(uid=uid).first()

    if not event:
        messages.error(request, "Event does not exist.")
        return redirect("event_list")

    # user string
    users_str = auth.get_users_str()

    context = dict(event=event, users_str=users_str)

    return render(request, "event_view.html", context=context)

@ensure_csrf_cookie
def job_view(request, uid):
    "Return a detailed view for specific post"

    # Get the post.
    job = Job.objects.filter(uid=uid).first()

    if not job:
        messages.error(request, "Job does not exist.")
        return redirect("job_list")

    # user string
    users_str = auth.get_users_str()

    context = dict(job=job, users_str=users_str)

    return render(request, "job_view.html", context=context)


@login_required
def new_post(request):
    """
    Creates a new post
    """

    form = forms.PostLongForm(user=request.user)
    author = request.user
    tag_val = content = ''
    if request.method == "POST":

        form = forms.PostLongForm(data=request.POST, user=request.user)
        tag_val = form.data.get('tag_val')
        content = form.data.get('content', '')
        if form.is_valid():
            # Create a new post by user
            title = form.cleaned_data.get('title')
            content = form.cleaned_data.get("content")
            ptype = form.cleaned_data.get('post_type')
            tag_val = form.cleaned_data.get('tag_val')
            post = auth.create_post(title=title, content=content, ptype=ptype, tag_val=tag_val, author=author)

            tasks.created_post.spool(pid=post.id)

            return redirect(post.get_absolute_url())

    # Action url for the form is the current view
    action_url = reverse("post_create")
    users_str = auth.get_users_str()
    context = dict(form=form, tab="new", tag_val=tag_val, action_url=action_url,
                   content=content, users_str=users_str)

    return render(request, "new_post.html", context=context)

@login_required
def new_event(request):
    """
    Creates a new event
    """

    form = forms.EventForm(user=request.user)
    author = request.user
    tag_val = content = location = external_link = ''
    event_date = timezone.now()
    if request.method == "POST":

        form = forms.EventForm(data=request.POST, user=request.user)
        tag_val = form.data.get('tag_val')
        content = form.data.get('content', '')
        if form.is_valid():
            # Create a new post by user
            title = form.cleaned_data.get('title')
            content = form.cleaned_data.get("content")
            tag_val = form.cleaned_data.get('tag_val')
            location = form.cleaned_data.get('location','')
            external_link = form.cleaned_data.get('external_link','')
            event_date = form.cleaned_data.get('event_date')
            event = auth.create_event(title=title, content=content, tag_val=tag_val, author=author,
                    location=location, event_date=event_date, external_link=external_link)

            tasks.created_event.spool(eid=event.id)

            return redirect('event_list')

    # Action url for the form is the current view
    action_url = reverse("event_create")
    users_str = auth.get_users_str()
    context = dict(form=form, tab="new", tag_val=tag_val, action_url=action_url,
                   content=content, users_str=users_str)

    return render(request, "new_event.html", context=context)

@login_required
def new_job(request):
    """
    Creates a new job
    """

    form = forms.JobForm(user=request.user)
    author = request.user
    content = ''
    apply_before = timezone.now()

    if request.method == "POST":

        form = forms.JobForm(data=request.POST, user=request.user)
        content = form.data.get('content', '')
        if form.is_valid():
            # Create a new post by user
            title = form.cleaned_data.get('title')
            content = form.cleaned_data.get("content")
            institution = form.cleaned_data.get('institution','')
            apply_before = form.cleaned_data.get('apply_before')
            job = auth.create_job(title=title, content=content, author=author, institution=institution, apply_before=apply_before)

            tasks.created_job.spool(jid=job.id)

            return redirect('job_list')

    # Action url for the form is the current view
    action_url = reverse("job_create")
    context = dict(form=form, tab="new", action_url=action_url, content=content)

    return render(request, "new_job.html", context=context)


@post_exists
@login_required
def post_moderate(request, uid):
    """Used to make display post moderate form given a post request."""

    user = request.user
    post = Post.objects.filter(uid=uid).first()

    if request.method == "POST":
        form = forms.PostModForm(post=post, data=request.POST, user=user, request=request)

        if form.is_valid():
            action = form.cleaned_data.get('action')
            comment = form.cleaned_data.get('comment')
            mod = auth.Moderate(user=user, post=post, action=action, comment=comment)
            messages.success(request=request, message=mod.msg)
            auth.log_action(user=user, log_text=f"{mod.msg} ; post.uid={post.uid}.")
            return redirect(mod.url)
        else:
            errors = ','.join([err for err in form.non_field_errors()])
            messages.error(request, errors)
            return redirect(reverse("post_view", kwargs=dict(uid=post.root.uid)))
    else:
        form = forms.PostModForm(post=post, user=user, request=request)

    context = dict(form=form, post=post)
    return render(request, "forms/form_moderate.html", context)


@login_required
def send_invites(request):

    if request.method == "POST":
        form = forms.InvitePeersForm(request.POST)
        if form.is_valid():
            form.save(request)
            messages.success(request, "Invitation sent")
        else:
            messages.warning(request, "Errors while sending invitation")
        return redirect('/')

    else:
        form = forms.InvitePeersForm()

    context = dict(form=form)
    return render(request, "invitations/invite_form.html", context)