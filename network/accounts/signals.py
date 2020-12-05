from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from network.accounts.models import Profile, User, generate_avatar
from network.accounts import util, tasks

def get_full_name(self):
        return f'{self.first_name} {self.last_name}'


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, raw, using, **kwargs):
    if created:
        # Set the username to a simpler form.
        username = f"{instance.first_name}-{instance.pk}" if instance.first_name else f'user-{instance.pk}'
        if User.objects.filter(username=username).exclude(id=instance.pk).exists():
            username = util.get_uuid(6)

        User.objects.filter(pk=instance.pk).update(username=username)

        # Make sure staff users are also moderators.
        role = Profile.MANAGER if instance.is_staff else Profile.READER
        full_name = f'{instance.first_name} {instance.last_name}'
        Profile.objects.using(using).create(user=instance, uid=username, name=full_name, role=role)
        profile = instance.profile
        profile.avatar = generate_avatar(profile)
        tasks.create_messages.spool(rec_list=[instance], template="messages/welcome.md")

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

@receiver(pre_save, sender=User)
def create_uuid(sender, instance, *args, **kwargs):
    instance.username = instance.username or util.get_uuid(8)

