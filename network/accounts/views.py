import logging
from mistune import markdown
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, login
from django.shortcuts import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied, ImproperlyConfigured

from django.views.decorators.csrf import csrf_exempt
from ratelimit.decorators import ratelimit
from django.core import signing
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.utils.safestring import mark_safe
from ratelimit.decorators import ratelimit


from . import forms, tasks
from .auth import validate_login, send_verification_email
from .const import *
from .models import User, Profile, UserVerification, Message, Logger
from .tokens import account_verification_token
from .util import now, get_uuid


logger = logging.getLogger("engine")

def edit_profile(request):
    if request.user.is_anonymous:
        messages.error(request, "Must be logged in to edit profile")
        return redirect("/")
    user = request.user
    initial = dict(
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        location=user.profile.location,
        gender=user.profile.gender,
        alt_email_a=user.profile.alt_email_a,
        alt_email_b=user.profile.alt_email_b,
        occupation=user.profile.occupation,
        expertise=user.profile.expertise,
        affiliations=user.profile.affiliations,
        phone=user.profile.phone,
        text=user.profile.text,
        qualifications=user.profile.qualifications,
        email_verified=user.profile.email_verified,
    )

    form = forms.EditProfile(user=user, initial=initial)

    if request.method == "POST":
        form = forms.EditProfile(
            data=request.POST, user=user, initial=initial, files=request.FILES
        )

        if form.is_valid():
            # Update the email and username of User object.
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            User.objects.filter(pk=user.pk).update(username=username, email=email, first_name=first_name, last_name=last_name)
            # Update user information in Profile object.
            Profile.objects.filter(user=user).update(
                location=form.cleaned_data["location"],
                phone=form.cleaned_data["phone"],
                alt_email_a=form.cleaned_data["alt_email_a"],
                alt_email_b=form.cleaned_data["alt_email_b"],
                gender=form.cleaned_data["gender"],
                occupation=form.cleaned_data["occupation"],
                qualifications=form.cleaned_data["qualifications"],
                expertise=form.cleaned_data["expertise"],
                affiliations=form.cleaned_data["affiliations"],
                text=form.cleaned_data["text"],
                html=markdown(form.cleaned_data["text"]),
            )

            return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

    context = dict(user=user, form=form)
    return render(request, "accounts/edit_profile.html", context=context)


def edit_notifications(request, pk):

    if request.user.is_anonymous:
        messages.error(request, "Must be logged in to edit profile")
        return redirect("/")

    user = request.user
    target = User.objects.filter(pk=user.pk).first()

    initial = dict(
      message_prefs=user.profile.message_prefs,
      watched_tags=user.profile.watched_tags,
    )

    form = forms.NotificationsForm(user=user, initial=initial)

    if request.method == "POST":
        form = forms.NotificationsForm(
            data=request.POST, user=user, initial=initial
        )
        if form.is_valid():
            message_prefs=form.cleaned_data["message_prefs"]
            watched_tags=form.cleaned_data["watched_tags"]

            profile = Profile.objects.filter(user=target).first()
            profile.message_prefs = message_prefs
            profile.watched_tags = watched_tags
            profile.save()

            messages.success(request, "Notification settings updated.")
        else:
            errs = ",".join([err for err in form.non_field_errors()])
            messages.error(request, errs)

        return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

    context = dict(user=user, form=form)
    
    return render(request, "accounts/edit_notifications.html", context=context)

def edit_subscriptions(request, pk):

    if request.user.is_anonymous:
        messages.error(request, "Must be logged in to edit profile")
        return redirect("/")
    user = request.user
    target = User.objects.filter(pk=user.pk).first()

    initial = dict(
      my_tags=user.profile.my_tags,
    )

    form = forms.SubscriptionsForm(user=user, initial=initial)

    if request.method == "POST":
        form = forms.SubscriptionsForm(
            data=request.POST, user=user, initial=initial
        )
        if form.is_valid():
            my_tags=form.cleaned_data["my_tags"]
            profile = Profile.objects.filter(user=target).first()
            profile.my_tags = my_tags
            profile.save()
            messages.success(request, "Subscription settings updated.")
        
        else:
            errs = ",".join([err for err in form.non_field_errors()])
            messages.error(request, errs)

        return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

    context = dict(form=form, user=user)
    
    return render(request, "accounts/edit_subscriptions.html", context=context)


def listing(request):

    users = User.objects.all()
    context = dict(users=users)
    return render(request, "accounts/listing.html", context=context)


@login_required
def user_moderate(request, uid):

    source = request.user
    target = User.objects.filter(id=uid).first()
    form = forms.UserModerate(
        source=source,
        target=target,
        request=request,
        initial=dict(is_spammer=target.profile.is_spammer, action=target.profile.state),
    )
    if request.method == "POST":

        form = forms.UserModerate(
            source=source,
            data=request.POST,
            target=target,
            request=request,
            initial=dict(
                is_spammer=target.profile.is_spammer, action=target.profile.state
            ),
        )
        if form.is_valid():
            state = form.cleaned_data.get("action", "")
            profile = Profile.objects.filter(user=target).first()
            profile.state = state
            profile.save()
            # Log the moderation action
            log_text = f"Moderated user={target.pk}; state={target.profile.state} ( {target.profile.get_state_display()} )"
            Logger.objects.create(
                user=request.user, log_text=log_text, action=Logger.MODERATING
            )

            messages.success(request, "User moderation complete.")
        else:
            errs = ",".join([err for err in form.non_field_errors()])
            messages.error(request, errs)

        return redirect(reverse("user_profile", kwargs=dict(uid=target.profile.uid)))

    context = dict(form=form, target=target)

    return render(request, "accounts/user_moderate.html", context)


@login_required
def message_list(request):
    """
    Show messages belonging to user.
    """
    user = request.user
    page = request.GET.get("page", 1)
    msgs = Message.objects.filter(recipient=user)
    msgs = msgs.select_related("sender", "body", "sender__profile")
    msgs = msgs.order_by("-sent_date")

    # Get the pagination info
    paginator = Paginator(msgs, settings.MESSAGES_PER_PAGE)
    msgs = paginator.get_page(page)

    counts = request.session.get(COUNT_DATA_KEY, {})
    # Set message count back to 0
    counts["message_count"] = 0
    request.session.update(dict(counts=counts))

    context = dict(tab="messages", all_messages=msgs)
    return render(request, "message_list.html", context)


def user_profile(request, uid):
    profile = Profile.objects.filter(uid=uid).first()

    if not profile:
        messages.error(request, "User does not exist")
        return redirect("/")

    # Get the active tab, defaults to project
    active = request.GET.get("active", "posts")

    # Apply filter to what is shown.
    show = request.GET.get("show", "")

    # User viewing profile is a moderator
    is_mod = request.user.is_authenticated and request.user.profile.is_moderator

    can_moderate = is_mod and request.user != profile.user
    show_info = is_mod or (profile.is_valid and not profile.low_rep)

    context = dict(
        target=profile.user,
        active=active,
        debugging=settings.DEBUG,
        show_info=show_info,
        const_post=POSTS,
        const_project=PROJECT,
        can_moderate=can_moderate,
        show=show,
        tab="profile",
    )

    return render(request, "accounts/user_profile.html", context)


def toggle_notify(request):
    if request.user.is_anonymous:
        messages.error(request, "Must be logged in to edit profile")
        return redirect("/")

    user = request.user
    user.profile.notify = not user.profile.notify
    user.profile.save()

    msg = "Emails notifications disabled."
    if user.profile.notify:
        msg = "Emails notifications enabled."

    messages.success(request, msg)
    return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))


@ratelimit(key="ip", rate="10/m", block=True, method=ratelimit.UNSAFE)
def user_signup(request):

    if request.method == "POST":

        form = forms.SignUpWithCaptcha(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            Profile.objects.filter(user=user).update(last_login=now())
            messages.success(request, "Login successful!")
            msg = mark_safe("Signup successful!")
            tasks.verification_email.spool(user=user)
            messages.info(request, msg)

            # so rather than just send people to the homepage post-reg, we need them to fill another form to validate their info
            return redirect(reverse("verification")) # was "/"

    else:
        form = forms.SignUpWithCaptcha()

    context = dict(
        form=form,
        captcha_site_key=settings.RECAPTCHA_PUBLIC_KEY,
        tab="signup",
    )
    return render(request, "accounts/signup.html", context=context)

def user_verification(request):

    if request.user.is_anonymous:
        messages.error(request, "Must be logged in to edit profile")
        return redirect("/")
    
    user = request.user

    if request.method == "POST":
        form = forms.VerificationForm(user, request.POST, request.FILES)
        if form.is_valid():
            verification = form.save()
            log_text = f"Verification data submitted for user={user.pk}; handle={user.profile.uid} ( {user.profile.name} )"
            Logger.objects.create(
                user=request.user, log_text=log_text, action=Logger.VERIFY
            )
            messages.success(request, "Your details have been uploaded. You will have full access once they have been verified.")

            return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

        else:
            errs = ",".join([err for err in form.non_field_errors()])
            messages.error(request, errs)

    else:
        form = forms.VerificationForm(user=user)

    context = dict(user=user, form=form)
    
    return render(request, "accounts/verify_account.html", context=context)


@login_required
@csrf_exempt
def image_upload_view(request):

    user = request.user

    if not request.method == "POST":
        raise PermissionDenied()

    if not settings.PAGEDOWN_IMAGE_UPLOAD_ENABLED:
        raise ImproperlyConfigured("Image upload is disabled")

    form = forms.ImageUploadForm(data=request.POST, files=request.FILES, user=user)
    if form.is_valid():
        url = form.save()
        return JsonResponse({"success": True, "url": url})

    return JsonResponse({"success": False, "error": form.errors})


@user_passes_test(lambda u: u.is_superuser)
def debug_user(request):
    """
    Allows superusers to log in as a regular user to troubleshoot problems.
    """

    if not settings.DEBUG:
        messages.error(request, "Can only use when in debug mode.")
        redirect("/")

    target = request.GET.get("uid", "")
    profile = Profile.objects.filter(uid=target).first()

    if not profile:
        messages.error(request, "User does not exists.")
        return redirect("/")

    user = profile.user
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Login successful!")

    logger.info(
        f"""uid={request.user.profile.uid} impersonated 
                    uid={profile.uid}."""
    )

    return redirect("/")


def user_logout(request):
    if request.method == "POST":

        form = forms.LogoutForm(request.POST)

        if form.is_valid():
            logout(request)
            messages.info(request, "You have been logged out")
            return redirect("login")

    form = forms.LogoutForm()

    context = dict(form=form, active="logout")

    return render(request, "accounts/logout.html", context=context)


def user_login(request):
    form = forms.LoginForm()
    if request.method == "POST":
        form = forms.LoginForm(data=request.POST)

        if form.is_valid():

            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            next_url = request.POST.get("next", settings.LOGIN_REDIRECT_URL)
            user = User.objects.filter(email__iexact=email).order_by("-id").first()
            message, valid_user = validate_login(email=email, password=password)

            if valid_user:
                login(
                    request, user, backend="django.contrib.auth.backends.ModelBackend"
                )
                messages.success(request, "Login successful!")
                return redirect(next_url)
            else:
                messages.error(request, mark_safe(message))

        messages.error(request, mark_safe(form.errors))

    context = dict(form=form, tab="login")
    return render(request, "accounts/login.html", context=context)


@login_required
def send_email_verify(request):
    "Send one-time valid link to validate email"

    # Sends verification email with a token
    user = request.user

    send_verification_email(user=user)

    messages.success(request, "Verification sent, check your email.")

    return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))


def email_verify_account(request, uidb64, token):
    "Verify one time link sent to a users email"

    uid = force_text(urlsafe_base64_decode(uidb64))
    user = User.objects.filter(pk=uid).first()

    if user and account_verification_token.check_token(user, token):
        Profile.objects.filter(user=user).update(email_verified=True)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Email verified!")
        return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

    messages.error(request, "Link is expired.")
    return redirect("/")


def external_login(request):
    """Login or signup a user."""
    payload = request.GET.get("payload", "")

    try:
        signer = signing.Signer(settings.LOGIN_PRIVATE_KEY)
        user_email = signer.unsign(payload)
        user = User.objects.filter(email=user_email).first()

        if not user:
            name = user_email.split("@")[0]
            user = User.objects.create(
                email=user_email, first_name=name, password=str(get_uuid(16))
            )
            user.username = name.split()[0] + str(get_uuid(8))
            user.save()
            msg = f"Signed up, <a href={reverse('password_reset')}><b> Please reset your password.</b></a>"
            messages.success(request, mark_safe(msg))

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Logged in!")
        return redirect("/")

    except Exception as exc:
        logger.error(f"Error:{exc}")
        messages.error(request, "Error unsigning.")

    return redirect("/")


@ratelimit(key="ip", rate="500/h")
@ratelimit(key="ip", rate="25/m")
def password_reset(request):

    # if request.method == "POST":
    #     email = request.POST.get('email', '')
    #     user = User.objects.filter(email=email).first()
    #     if not user:
    #         messages.error(request, "Email does not exist.")
    #         return redirect(reverse('password_reset'))
    # The email template instance
    # email = sender.EmailTemplate(template_name)
    #
    # # Default context added to each template.
    # context = dict(domain=settings.SITE_DOMAIN, protocol=settings.PROTOCOL,
    #                port=settings.HTTP_PORT, name=settings.SITE_NAME, subject=subject)
    #
    # # Additional context added to the template.
    # context.update(extra_context)
    #
    # # Generate and send the email.
    # email.render()
    return PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        subject_template_name="accounts/password_reset_subject.txt",
        email_template_name="accounts/password_reset_email.html",
    )(request=request)


@ratelimit(key="ip", rate="500/h")
@ratelimit(key="ip", rate="25/m")
def password_reset_done(request):
    context = dict()

    return PasswordResetDoneView.as_view(
        extra_context=context, template_name="accounts/password_reset_done.html"
    )(request=request)


@ratelimit(key="ip", rate="500/h")
@ratelimit(key="ip", rate="25/m")
def pass_reset_confirm(request, uidb64, token):
    context = dict()

    return PasswordResetConfirmView.as_view(
        extra_context=context, template_name="accounts/password_reset_confirm.html"
    )(request=request, uidb64=uidb64, token=token)


def password_reset_complete(request):
    context = dict()

    return PasswordResetCompleteView.as_view(
        extra_context=context, template_name="accounts/password_reset_complete.html"
    )(request=request)
