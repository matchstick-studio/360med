import logging
import base64
import io
import pyavagen
from django.core.files.base import ContentFile
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
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from ratelimit.decorators import ratelimit
from django.core import signing
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.utils.safestring import mark_safe
from ratelimit.decorators import ratelimit

from django.contrib.auth.forms import PasswordChangeForm

from . import forms, tasks
from .auth import validate_login, send_verification_email
from .const import *
from .models import User, Profile, Message, Logger, change_avatar
from .tokens import account_verification_token
from .util import now, get_uuid


logger = logging.getLogger("engine")

@login_required
@require_POST
def update_avatar(request):
    profile = request.user.profile
    # Received base64 string starts with 'data:image/jpeg;base64,........'
    # We need to use 'jpeg' as an extension and everything after base64,
    # as the image itself:
    fmt, imgstr = request.POST['avatar'].split(';base64')
    ext = fmt.split('/')[-1]
    if ext == 'svg+xml':
        ext = 'svg'
    img = ContentFile(base64.b64decode(imgstr), name=f'{profile.uid}.{ext}')
    change_avatar(profile, img)
    return redirect(reverse("user_profile", kwargs=dict(uid=profile.uid)))

@login_required
@require_POST
def delete_avatar(request):
    user = request.user
    form = forms.DeleteAvatarForm(request.POST, instance=user.profile)
    form.save()
    return redirect(reverse("edit_account"))

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
        country=user.profile.country,
        location=user.profile.location,
        gender=user.profile.gender,
        occupation=user.profile.occupation,
        phone=user.profile.phone,
        text=user.profile.text,
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
                country=form.cleaned_data["country"],
                location=form.cleaned_data["location"],
                phone=form.cleaned_data["phone"],
                gender=form.cleaned_data["gender"],
                occupation=form.cleaned_data["occupation"],
                text=form.cleaned_data["text"],
                html=markdown(form.cleaned_data["text"]),
            )

            return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

    context = dict(user=user, form=form)
    return render(request, "accounts/edit_profile.html", context=context)

@login_required
def edit_professional(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = forms.ProfessionalForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()

            return redirect('')
            

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
            msg = mark_safe("Signup successful. Also, we sent you an email. Verify your account now.")
            tasks.verification_email.spool(user=user) # send email verification email
    
            # so rather than just send people to the homepage post-reg, we need them to fill another form to validate their info
            return redirect('onboarding') # was "/"

            messages.info(request, msg)

    else:
        form = forms.SignUpWithCaptcha()

    context = dict(
        form=form,
        captcha_site_key=settings.RECAPTCHA_PUBLIC_KEY,
        tab="signup",
    )
    return render(request, "accounts/signup.html", context=context)


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

# update account info

def edit_account(request):
    user = request.user
    profile = Profile.objects.filter(uid=user.profile.uid).first()
    target=profile.user
    emails_form = forms.SecondaryEmailsForm(user=user)
    delete_user_form = forms.DeleteUserForm(user=user)

    if request.method == "POST":

        if emails_form.is_valid():
            emails_form.save()
            messages.success(request, _('Secondary emails were updated'))
        else:
            messages.error(request, _('Failed to update emails'))
        return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))
    
    
    return render(request, 'accounts/edit_account.html', {
        'delete_user_form': delete_user_form,
        'emails_form': emails_form,
        'target': target
    })

# Update main email
@login_required
@require_POST
def update_email(request):
    form = forms.UpdateEmailForm(request.user, request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, _('Email was updated'))
    else:
        messages.error(request, _('Failed to update email'))
    return redirect('user_profile')

# Update password in profile section
@login_required
@require_POST
def update_password(request):
    user = request.user

    form = PasswordChangeForm(request.user, request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, _('Password was updated'))
    else:
        messages.error(request, _('Failed to update password'))
    return redirect(reverse("user_profile", kwargs=dict(uid=user.profile.uid)))

# delete user account 
@login_required
@require_POST
def delete_account(request):
    form = forms.DeleteUserForm(request.user, request.POST)
    if form.is_valid():
        form.save()
        return redirect('/')

    messages.error(request, _('Failed to delete account'))
    return redirect('user_profile')

"""" Onboarding views """
@login_required
def personal(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = forms.PersonalForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            """ profile.avatar = generate_avatar(profile)
            profile.save() """
            return redirect('register-professional')
    else:
        form = forms.PersonalForm(instance=profile)
    return render(request, 'onboarding/personal.html', {
        'form': form
    })

@login_required
def professional(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = forms.ProfessionalForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            # we need to update registrations status
            profile.has_finished_registration = True
            profile.save()
            return redirect('/')
    else:
        form = forms.ProfessionalForm(instance=profile)
    return render(request, 'onboarding/professional.html', {
        'form': form
    })