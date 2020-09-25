import logging
from datetime import timedelta
from functools import wraps, lru_cache
import os

from django.db import models, connections
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.db.models import Count, Q
from taggit.models import Tag
from django.shortcuts import render, redirect, reverse
from django.core.cache import cache

from network.accounts.models import Profile
from network.forum import forms, auth, tasks, util, search
from network.forum.const import *
from network.forum.models import Post, Vote, Badge


User = get_user_model()

logger = logging.getLogger("engine")

# Valid post values as they correspond to database post types.
POST_TYPE_MAPPER = dict(
    question=Post.QUESTION,
    job=Post.JOB,
    tutorial=Post.TUTORIAL,
    forum=Post.FORUM,
    blog=Post.BLOG,
    tool=Post.TOOL,
    news=Post.NEWS,
)

LIMIT_MAP = dict(all=0, today=1, week=7, month=30, year=365)
# Valid order values value as they correspond to database ordering fields.
ORDER_MAPPER = dict(
    rank="-rank",
    tagged="-tagged",
    views="-view_count",
    replies="-reply_count",
    votes="-thread_votecount",
    visit="-profile__last_login",
    reputation="-profile__score",
    joined="-profile__date_joined",
    activity="-profile__date_joined",
)


def generate_cache_key(*args):
    # Combine list of values to form a single key
    vals = [str(v).replace(" ", "") for v in args]
    key = "".join(vals)
    return key


def post_exists(func):
    """
    Ensure uid passed to view function exists.
    """

    @wraps(func)
    def _wrapper_(request, **kwargs):
        uid = kwargs.get("uid")
        post = Post.objects.filter(uid=uid).exists()
        if not post:
            messages.error(request, "Post does not exist.")
            return redirect(reverse("post_list"))
        return func(request, **kwargs)

    return _wrapper_


def get_posts(user, show="latest", tag="", order="rank", limit=None):
    """
    Generates a post list on a topic.
    """
    # Topics are case insensitive.
    topic = show.lower()

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
    query = query.select_related("root").prefetch_related(
        "author__profile", "lastedit_user__profile"
    )

    return query


def post_search(request):

    query = request.GET.get("query", "")
    length = len(query.replace(" ", ""))
    page = int(request.GET.get("page", 1))

    if length < settings.SEARCH_CHAR_MIN:
        messages.error(request, "Enter more characters before preforming search.")
        return redirect(reverse("post_list"))

    results = search.preform_whoosh_search(
        query=query, page=page, sortedby=["lastedit_date"]
    )

    # if not len(results):
    #    results = search.SearchResult()

    total = results.total
    template_name = "search/search_results.html"

    question_flag = Post.QUESTION
    context = dict(
        results=results,
        query=query,
        total=total,
        template_name=template_name,
        question_flag=question_flag,
        stop_words=",".join(search.STOP),
    )

    return render(request, template_name=template_name, context=context)


class CachedPaginator(Paginator):
    """
    Paginator that caches the count call.
    """

    # Time to live for the cache, in seconds
    TTL = 300

    LIMIT = 1000

    def __init__(self, count_key="", ttl=None, *args, **kwargs):
        self.count_key = count_key
        self.ttl = ttl or self.TTL
        super(CachedPaginator, self).__init__(*args, **kwargs)

    @property
    def count(self):
        value = 1

        # Return uncached paginator.
        if self.count_key is None:
            return super(CachedPaginator, self).count

        if self.count_key not in cache:
            value = super(CachedPaginator, self).count

            # Small values do not need to be cached.
            if value > self.LIMIT:
                logger.info("Setting paginator count cache")
                cache.set(self.count_key, value, self.ttl)

        # Offset to estimate post counts without missing newly created posts since TTL.
        value = cache.get(self.count_key, value)

        return value


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

    return render(request, "pages.html", context=context)


@ensure_csrf_cookie
def post_list(request, show=None, cache_key="", extra_context=dict()):
    """
    Post listing. Filters, orders and paginates posts based on GET parameters.
    """
    # The user performing the request.
    user = request.user

    # Parse the GET parameters for filtering information
    page = request.GET.get("page", 1)
    order = request.GET.get("order", "rank")
    tag = request.GET.get("tag", "")
    show = show or request.GET.get("type", "")
    limit = request.GET.get("limit", "all")

    # Pages are enable when showing 'all' ordered by 'rank'
    cond1 = limit == "all" and order == "rank"
    # Pages are also enabled when a page number is provided.
    cond2 = request.GET.get("page") is not None

    enable_pages = cond1 or cond2

    # Get posts available to users.
    posts = get_posts(user=user, show=show, tag=tag, order=order, limit=limit)

    if enable_pages:
        # Show top 100 posts without pages.
        cache_key = cache_key or generate_cache_key(limit, tag, show)
        # Create the paginator
        paginator = CachedPaginator(
            count_key=cache_key, object_list=posts, per_page=settings.POSTS_PER_PAGE
        )
        # Apply the post paging.
        posts = paginator.get_page(page)
    else:
        posts = posts[:100]

    # Set the active tab.
    tab = tag or show or "latest"

    # Fill in context.
    context = dict(
        posts=posts,
        tab=tab,
        enable_pages=enable_pages,
        tag=tag,
        order=order,
        type=show,
        limit=limit,
        avatar=True,
    )
    context.update(extra_context)
    # Render the page.
    return render(request, template_name="post_list.html", context=context)


def latest(request):
    show = request.GET.get("type", "") or LATEST
    return post_list(request, show=show)


def authenticated(func):
    def _wrapper_(request, **kwargs):
        if request.user.is_anonymous:
            messages.error(request, "You need to be logged in to view this page.")
        return func(request, **kwargs)

    return _wrapper_


@authenticated
def myvotes(request):
    """
    Show posts by user that received votes
    """
    page = request.GET.get("page", 1)
    votes = (
        Vote.objects.filter(post__author=request.user)
        .prefetch_related("post", "post__root", "author__profile")
        .order_by("-date")
    )
    # Create the paginator
    paginator = CachedPaginator(
        count_key=MYVOTES_CACHE_KEY, object_list=votes, per_page=settings.POSTS_PER_PAGE
    )

    # Apply the votes paging.
    votes = paginator.get_page(votes)

    context = dict(votes=votes, page=page, tab="myvotes")
    return render(request, template_name="votes_list.html", context=context)


def tags_list(request):
    """
    Show posts by user
    """
    page = request.GET.get("page", 1)
    query = request.GET.get("query", "")

    count = Count("post", filter=Q(post__is_toplevel=True))
    if query:
        db_query = Q(name__in=query) | Q(name__contains=query)
    else:
        db_query = Q()

    tags = Tag.objects.annotate(nitems=count).filter(db_query)
    tags = tags.order_by("-nitems")

    # Create the paginator
    paginator = CachedPaginator(
        count_key=TAGS_CACHE_KEY, object_list=tags, per_page=settings.POSTS_PER_PAGE
    )

    # Apply the votes paging.
    tags = paginator.get_page(page)

    context = dict(tags=tags, tab="tags", query=query)

    return render(request, "tags_list.html", context=context)


@authenticated
def myposts(request):
    """
    Show posts by user
    """
    return post_list(request, show=MYPOSTS)


@authenticated
def following(request):
    """
    Show posts followed by user
    """
    return post_list(request, show=FOLLOWING)


@authenticated
def bookmarks(request):
    """
    Show posts bookmarked by user
    """
    return post_list(request, show=BOOKMARKS)


@authenticated
def mytags(request):

    return post_list(request=request, show=MYTAGS)


def community_list(request):
    users = User.objects.select_related("profile")
    page = request.GET.get("page", 1)
    ordering = request.GET.get("order", "visit")
    limit_to = request.GET.get("limit", "time")
    query = request.GET.get("query", "")
    days = LIMIT_MAP.get(limit_to, 0)

    if days:
        delta = util.now() - timedelta(days=days)
        users = users.filter(profile__last_login__gt=delta)

    if query and len(query) > 2:
        db_query = (
            Q(email__in=query)
            | Q(profile__name__contains=query)
            | Q(profile__uid__contains=query)
            | Q(username__contains=query)
            | Q(profile__name__in=query)
            | Q(email=query)
            | Q(email__contains=query)
            | Q(profile__uid__contains=query)
        )
        users = users.filter(db_query)

    order = ORDER_MAPPER.get(ordering, "visit")
    users = users.filter(profile__state__in=[Profile.NEW, Profile.TRUSTED])
    users = users.order_by(order)

    # Create the paginator
    paginator = CachedPaginator(
        count_key="USERS", object_list=users, per_page=settings.POSTS_PER_PAGE
    )
    users = paginator.get_page(page)
    context = dict(
        tab="community", users=users, query=query, order=ordering, limit=limit_to
    )

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
    post = Post.objects.filter(uid=uid).select_related("root").first()

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
            answer = auth.create_post(
                title=post.title,
                parent=post,
                author=author,
                content=content,
                ptype=Post.ANSWER,
                root=post.root,
            )
            return redirect(answer.get_absolute_url())
        messages.error(request, form.errors)

    # Build the comment tree .
    root, comment_tree, answers, thread = auth.post_tree(
        user=request.user, root=post.root
    )
    # user string
    users_str = auth.get_users_str()

    context = dict(
        post=root, tree=comment_tree, form=form, answers=answers, users_str=users_str
    )

    return render(request, "post_view.html", context=context)


@login_required
def new_post(request):
    """
    Creates a new post
    """

    form = forms.PostLongForm(user=request.user)
    author = request.user
    tag_val = content = ""
    if request.method == "POST":

        form = forms.PostLongForm(data=request.POST, user=request.user)
        tag_val = form.data.get("tag_val")
        content = form.data.get("content", "")
        if form.is_valid():
            # Create a new post by user
            title = form.cleaned_data.get("title")
            content = form.cleaned_data.get("content")
            ptype = form.cleaned_data.get("post_type")
            tag_val = form.cleaned_data.get("tag_val")
            post = auth.create_post(
                title=title,
                content=content,
                ptype=ptype,
                tag_val=tag_val,
                author=author,
            )

            tasks.created_post.spool(pid=post.id)

            return redirect(post.get_absolute_url())

    # Action url for the form is the current view
    action_url = reverse("post_create")
    users_str = auth.get_users_str()
    context = dict(
        form=form,
        tab="new",
        tag_val=tag_val,
        action_url=action_url,
        content=content,
        users_str=users_str,
    )

    return render(request, "new_post.html", context=context)


@post_exists
@login_required
def post_moderate(request, uid):
    """Used to make display post moderate form given a post request."""

    user = request.user
    post = Post.objects.filter(uid=uid).first()

    if request.method == "POST":
        form = forms.PostModForm(
            post=post, data=request.POST, user=user, request=request
        )

        if form.is_valid():
            action = form.cleaned_data.get("action")
            comment = form.cleaned_data.get("comment")
            mod = auth.Moderate(user=user, post=post, action=action, comment=comment)
            messages.success(request=request, message=mod.msg)
            auth.log_action(user=user, log_text=f"{mod.msg} ; post.uid={post.uid}.")
            return redirect(mod.url)
        else:
            errors = ",".join([err for err in form.non_field_errors()])
            messages.error(request, errors)
            return redirect(reverse("post_view", kwargs=dict(uid=post.root.uid)))
    else:
        form = forms.PostModForm(post=post, user=user, request=request)

    context = dict(form=form, post=post)
    return render(request, "forms/form_moderate.html", context)
