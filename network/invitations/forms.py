from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import ugettext_lazy as _

from .adapters import get_invitations_adapter
from .exceptions import AlreadyAccepted, AlreadyInvited, UserRegisteredEmail
from .utils import get_invitation_model

Invitation = get_invitation_model()


class CleanEmailMixin(object):
    def validate_invitation(self, email):
        if Invitation.objects.all_valid().filter(email__iexact=email, accepted=False):
            raise AlreadyInvited
        elif Invitation.objects.filter(email__iexact=email, accepted=True):
            raise AlreadyAccepted
        elif get_user_model().objects.filter(email__iexact=email):
            raise UserRegisteredEmail
        else:
            return True

    def clean_email(self):
        email = self.cleaned_data["email"]
        email = get_invitations_adapter().clean_email(email)

        errors = {
            "already_invited": _("This e-mail address has already been" " invited."),
            "already_accepted": _(
                "This e-mail address has already" " accepted an invite."
            ),
            "email_in_use": _("An active user is using this e-mail address"),
        }
        try:
            self.validate_invitation(email)
        except (AlreadyInvited):
            raise forms.ValidationError(errors["already_invited"])
        except (AlreadyAccepted):
            raise forms.ValidationError(errors["already_accepted"])
        except (UserRegisteredEmail):
            raise forms.ValidationError(errors["email_in_use"])
        return email


class InviteForm(forms.Form, CleanEmailMixin):
    def __init__(self, *args, **kwargs):
        super(InviteForm, self).__init__(*args, **kwargs)
        self.fields["full_name"] = forms.CharField(
            required=True, widget=forms.TextInput(attrs={"placeholder": "Full name"})
        )

        self.fields["email"] = forms.EmailField(
            label=_("E-mail"),
            required=True,
            widget=forms.TextInput(attrs={"type": "email", "size": "30"}),
            initial="",
        )

    def save(self, *args, **kwargs):
        full_name = self.cleaned_data["full_name"]
        email = self.cleaned_data["email"]

        params = {}
        params["full_name"] = full_name
        params["email"] = email

        instance = Invitation.create(**params)
        return instance


class InvitationAdminAddForm(InviteForm):
    """email = forms.EmailField(
    label=_("E-mail"),
    required=True,
    widget=forms.TextInput(attrs={"type": "email", "size": "30"}))"""

    def save(self, *args, **kwargs):
        cleaned_data = super(InvitationAdminAddForm, self).clean()
        full_name = self.cleaned_data["full_name"]
        email = self.cleaned_data["email"]

        return Invitation.create(full_name=full_name, email=email)

        params = {}
        params["full_name"] = full_name
        params["email"] = email

        if cleaned_data.get("inviter"):
            params["inviter"] = cleaned_data.get("inviter")
        instance = Invitation.create(**params)
        super(InvitationAdminAddForm, self).save(*args, **kwargs)
        return instance

    class Meta:
        model = Invitation
        fields = "inviter"


class InvitationAdminChangeForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = "__all__"
