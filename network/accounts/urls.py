from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from network.accounts import views
from django.views.generic import RedirectView


account_patterns = [
    # Get the reset/ urls
    path('', views.listing, name="accounts_index"),
    path('admin/', admin.site.urls, name='django_admin'),

    path(r'password/reset/', views.password_reset, name='password_reset'),
    path(r'password/reset/done/', views.password_reset_done, name='password_reset_done'),

    path(r'verify/<uidb64>/<token>/', views.email_verify_account, name='email_verify_account'),

    path(r'reset/<uidb64>/<token>/', views.pass_reset_confirm, name='password_reset_confirm'),

    path(r'verify/', views.send_email_verify, name="send_email_verify"),

    path(r'reset/done/', views.password_reset_complete, name='password_reset_complete'),
    path(r'moderate/<int:uid>/', views.user_moderate, name="user_moderate"),
    path(r'login/', views.user_login, name="login"),
    path(r'signup/', views.user_signup, name="signup"),
    path(r'profile/<str:uid>/', views.user_profile, name="user_profile"),

    path(r'edit/profile/', views.edit_profile, name='edit_profile'),
    path(r'edit/account/', views.edit_account, name='edit_account'),
    path(r'email/update/', views.update_email, name='update-email'),
    path(r'password/update/', views.update_password, name='update-password'),
    path(r'avatar/update/', views.update_avatar, name='update_avatar'),
    path(r'avatar/delete/', views.delete_avatar, name='delete_avatar'),
    path(r'edit/notifications/<int:pk>/', views.edit_notifications, name='edit_notifications'),
     path(r'edit/subscriptions/<int:pk>/', views.edit_subscriptions, name='edit_subscriptions'),
    path(r'toggle/notify/', views.toggle_notify, name='toggle_notify'),
    path(r'logout/', views.user_logout, name="logout"),

    path('delete/', views.delete_account, name='delete'),

    path(r'debug/user/', views.debug_user, name="debug_user"),

    # Message urls
    path(r'inbox/', views.message_list, name='inbox'),

    # External url login
    path(r'external/', views.external_login, name="external"),

    # onboarding
    path('onboarding/', RedirectView.as_view(pattern_name='register-personal'),
         name='onboarding'),
    path('onboarding/personal/', views.personal, name='register-personal'),
    path('onboarding/professional/', views.professional, name='register-professional'),
    path('onboarding/subscriptions/', views.subscriptions, name='register-subscriptions'),

]


urlpatterns = [

    path("", include(account_patterns)),
]

if settings.PAGEDOWN_IMAGE_UPLOAD_ENABLED:

    urlpatterns += [
        # Pagedown image upload url.
        path('pagedown/image-upload/', views.image_upload_view, name="pagedown-image-upload")
    ]
