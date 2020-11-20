
from django.contrib import admin
from network.forum.models import Post, Subscription, Vote, Space


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('uid', 'title', 'type', 'author', 'lastedit_date')
    ordering = ['type', 'rank']
    fieldsets = (
        (None, {'fields': ('title',)}),
        ('Attributes', {'fields': ('type', 'status', 'sticky',)}),
        ('Content', {'fields': ('content', )}),
    )
    search_fields = ('title', 'author__profile__name', 'uid')


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('author', 'post', 'type', 'date')
    ordering = ['-date']
    search_fields = ('post__title', 'author__profile__name', 'uid')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    search_fields = ('user__profile__name', 'user__email', 'uid')
    list_select_related = ["user", "post"]

@admin.register(Space)
class SpaceAdmin(admin.ModelAdmin):
    list_display = ('name', )
    ordering = ['-name']
    search_fields = ('name', 'creator__profile_name')



