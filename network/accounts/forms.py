import logging
from django import forms
from django.core.validators import FileExtensionValidator
from django.contrib import messages
from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget
from django.contrib.auth.models import User
from django.conf import settings
from .models import Profile, UserImage, generate_avatar
from . import auth, util
from django.utils.translation import ugettext_lazy as _

from .widgets import PhoneNumberPrefixWidget, XDSoftDateTimePickerInput
from django_countries.fields import CountryField

logger = logging.getLogger("engine")

MAX_TAGS = 50
IMG_EXTENTIONS = ["jpg", "jpeg", "png", "webp"]


def check_size(fobj, maxsize=0.3, field=None):
    # maxsize in megabytes!
    error_msg = ""
    try:
        if fobj and fobj.size > maxsize * 1024 * 1024.0:
            curr_size = fobj.size / 1024 / 1024.0
            prefix = f"{field} field : ".capitalize() if field else ""
            error_msg = (
                prefix
                + f"file too large, {curr_size:0.1f}MB should be < {maxsize:0.1f}MB"
            )

    except Exception as exc:
        error_msg = f"File size validation error: {exc}"

    if error_msg:
        raise forms.ValidationError(error_msg)

    return fobj


class SignUpForm(forms.Form):

    first_name = forms.CharField(
        max_length=30, 
        label="First Name",
    )

    last_name = forms.CharField(
        max_length=30, 
        label="Last Name"
    )

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput,
        max_length=254,
        min_length=2,
    )

    password2 = forms.CharField(
        label="Password confirmation",
        widget=forms.PasswordInput,
        strip=False,
        help_text="Enter the same password as before, for verification.",
    )

    email = forms.EmailField(
        label="Email",
        max_length=254,
        min_length=2,
    )

    def clean_password2(self):

        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords given do not match.")
        return password2

    def clean_email(self):

        data = self.cleaned_data["email"]
        if User.objects.filter(email=data).exists():
            raise forms.ValidationError("This email is already being used.")
        return data

    def save(self):

        email = self.cleaned_data.get("email")
        password = self.cleaned_data.get("password1")
        first_name = self.cleaned_data.get("first_name")
        last_name = self.cleaned_data.get("last_name")
        name = self.cleaned_data.get("first_name") + ' ' + self.cleaned_data.get("last_name")
        user = User.objects.create(email=email, first_name=first_name, last_name=last_name)
        user.set_password(password)
        user.save()

        logger.info(f"Signed up user.id={user.id}, user.email={user.email}")

        return user


class SignUpWithCaptcha(SignUpForm):
    def __init__(self, *args, **kwargs):
        super(SignUpWithCaptcha, self).__init__(*args, **kwargs)

        if settings.RECAPTCHA_PRIVATE_KEY:
            self.fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())

class PersonalForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('country','location','phone','gender', 'dob')
        widgets = {
            'country': forms.Select(attrs={"class": "ui search dropdown"}),
            'phone': PhoneNumberPrefixWidget(attrs={"placeholder": "Mobile number"}),
            'gender': forms.Select(attrs={"class": "ui dropdown"}),
            'dob': XDSoftDateTimePickerInput(attrs={"placeholder": "Enter date of birth"})
        }

class ProfessionalForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('degree', 'position', 'institution', 'occupation', 'expertise', 'affiliations', 'licence')
        widgets = {
            'degree': forms.Select(attrs={"class": "ui dropdown"}),
            'occupation': forms.Select(attrs={"class": "ui dropdown"}),
            'expertise': forms.HiddenInput(),
            'affiliations': forms.HiddenInput()
        }

    def clean_expert_areas(self):
        expertise = self.cleaned_data["expertise"]
        expertise = ",".join(list(set(expertise.split(","))))
        return validate_tags(tags=expertise)

    def clean_affiliations(self):
        affiliations = self.cleaned_data["affiliations"]
        affiliations = ",".join(list(set(affiliations.split(","))))
        return validate_tags(tags=affiliations)


class NotificationsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ('message_prefs', 'watched_tags', 'my_tags')
        widgets = {
            'message_prefs': forms.Select(attrs={"class": "ui dropdown"}),
            'watched_tags': forms.HiddenInput(),
            'my_tags': forms.HiddenInput()

        }

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(NotificationsForm, self).__init__(*args, **kwargs)

    def clean_watched_tags(self):
        watched_tags = self.cleaned_data["watched_tags"]
        watched_tags = ",".join(list(set(watched_tags.split(","))))
        return validate_tags(tags=watched_tags)

    def clean_my_tags(self):
        my_tags = self.cleaned_data["my_tags"]
        my_tags = ",".join(list(set(my_tags.split(","))))
        return validate_tags(tags=my_tags)

class SubscriptionsForm(forms.Form):

    """ subscribe to groups """

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(SubscriptionsForm, self).__init__(*args, **kwargs)  

class LogoutForm(forms.Form):
    pass

class PasswordProtectedForm(forms.Form):
    password = forms.CharField(
        strip=False,
        label=_('Enter password to confirm'),
        widget=forms.PasswordInput(attrs={'placeholder': _('Password')})
    )

    def clean_password(self):
        """Validate that the entered password is correct.
        """
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError(
                _("The password is incorrect"),
                code='password_incorrect'
            )
        return password

class DeleteUserForm(PasswordProtectedForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def save(self):
        self.user.delete()


class UpdateEmailForm(PasswordProtectedForm):
    email = forms.EmailField(label=_('Enter your new email'))

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def save(self):
        self.user.email = self.cleaned_data['email']
        self.user.save()


class DeleteAvatarForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ()

    def save(self, commit=True):
        if self.instance.avatar:
            self.instance.avatar.delete()
            self.instance.avatar_version += 1
            self.instance.avatar = generate_avatar(self.instance)

        # regenerate a new text-based avatar when profile is deleted.
        self.instance.avatar = generate_avatar(self.instance)
        return super().save(commit)



class EditProfile(forms.Form):
    first_name = forms.CharField(label="First Name", max_length=100, required=True)
    last_name = forms.CharField(label="Last Name", max_length=100, required=True)
    email = forms.CharField(label="Email", max_length=100, required=True, disabled=True)
    username = forms.CharField(label="Handle", max_length=100, required=True)
    country = CountryField(_('Country')).formfield(initial='UG', widget=forms.Select(attrs={"class": "ui search dropdown"}),)
    location = forms.CharField(label="Location", max_length=100, required=False)

    text = forms.CharField(
        widget=forms.Textarea(),
        min_length=2,
        max_length=5000,
        required=False,
        help_text="Say a few words about who you are, what you're working on, or why you're here!",
    )

    gender = forms.ChoiceField(
        required=True,
        label="Gender",
        choices=Profile.GENDER_CHOICES,
        widget=forms.Select(attrs={"class": "ui dropdown"}),
        help_text="""Choose your gender""",
    )

    qualifications = forms.CharField(
        label="Qualifications",
        max_length=100,
        required=False,
        help_text="""e.g MBChB, M MED OBS & GYN""",
    )

    occupation = forms.ChoiceField(
        required=True,
        label="Occupation",
        choices=Profile.OCCUPATION_CHOICES,
        widget=forms.Select(attrs={"class": "ui dropdown"}),
        help_text="""What do you do?""",
    )

    phone = forms.CharField(
        required=False,
        initial="+256",
        widget=PhoneNumberPrefixWidget(attrs={"placeholder": "Mobile number"}),
        label="Phone Number",
        help_text="If you would like to be reached by phone",
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(EditProfile, self).__init__(*args, **kwargs)

    def clean_username(self):

        data = self.cleaned_data["username"]
        username = User.objects.exclude(pk=self.user.pk).filter(username=data)

        if len(data.split()) > 1:
            raise forms.ValidationError("No spaces allowed in username/handlers.")
        if username.exists():
            raise forms.ValidationError("This handler is already being used.")

        return data

    def clean_email(self):
        cleaned_data = self.cleaned_data["email"]
        email = User.objects.filter(email=cleaned_data).exclude(pk=self.user.pk).first()

        if email:
            raise forms.ValidationError("Email already exists.")

        if self.user.is_superuser and cleaned_data != self.user.email:
            raise forms.ValidationError(
                "Admins are required to change emails using the Django Admin Interface."
            )

        return cleaned_data

    def clean_affiliations(self):
        affiliations = self.cleaned_data["affiliations"]
        affiliations = ",".join(list(set(affiliations.split(","))))
        return validate_tags(tags=affiliations)


class LoginForm(forms.Form):

    email = forms.CharField(
        label="Email", 
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Email'})
    )
    password = forms.CharField(
        label="Password", 
        max_length=100, 
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'})
    )


class UserModerate(forms.Form):

    CHOICES = [
        (Profile.SPAMMER, "Report as spammer"),
        (Profile.BANNED, "Ban user"),
        (Profile.SUSPENDED, "Suspend user"),
        (Profile.NEW, "Reinstate as new user"),
        (Profile.TRUSTED, "Reinstate as trusted user"),
    ]

    action = forms.IntegerField(
        widget=forms.RadioSelect(choices=CHOICES), required=False, label="Select Action"
    )

    def __init__(self, source, target, request, *args, **kwargs):
        self.source = source
        self.target = target
        self.request = request

        super(UserModerate, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(UserModerate, self).clean()
        action = cleaned_data["action"]

        if not self.source.profile.is_moderator:
            raise forms.ValidationError(
                "You need to be a moderator to perform that action"
            )

        if action == Profile.BANNED and not self.source.is_superuser:
            raise forms.ValidationError("You need to be an admin to ban users.")

        if self.target.profile.is_moderator and not self.source.is_superuser:
            raise forms.ValidationError(
                "You need to be an admin to moderator other moderators."
            )

        if self.target == self.source:
            raise forms.ValidationError("You can not moderate yourself.")


class ImageUploadForm(forms.Form):
    def __init__(self, user=None, *args, **kwargs):

        self.user = user
        super(ImageUploadForm, self).__init__(*args, **kwargs)

    image = forms.ImageField(
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=IMG_EXTENTIONS)],
    )

    def clean_image(self):

        img = self.cleaned_data["image"]

        # Get all images this user has uploaded so far.
        userimg = UserImage.objects.filter(user=self.user)

        # Check for current image size being uploaded.
        check_size(fobj=img, maxsize=settings.MAX_IMAGE_SIZE_MB)

        # Moderators get no limit on images.
        if self.user.is_authenticated and self.user.profile.is_moderator:
            return img

        if userimg.count() >= settings.MAX_IMAGES:
            raise forms.ValidationError(
                "Exceeded the maximum amount of images you can upload."
            )

        return img

    def save(self):

        # Store the file
        image = self.cleaned_data["image"]

        # Create user image object
        userimg = UserImage.objects.create(user=self.user)

        # Save image to database.
        userimg.image.save(image.name, image, save=True)

        return userimg.image.url

def validate_tags(tags):
    my_tags = tags.split(",")
    if len(my_tags) > MAX_TAGS:
        return forms.ValidationError("Maximum number of tags reached.")
    return tags

class SecondaryEmailsForm(forms.Form):

    alt_email_a = forms.CharField(
        label="Alternative Email A", max_length=255, required=False
    )

    alt_email_b = forms.CharField(
        label="Alternative Email B", max_length=255, required=False
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(SecondaryEmailsForm, self).__init__(*args, **kwargs)