from django.conf.urls import url
from django.urls import include, path, re_path

from . import views

app_name = 'invitations'
urlpatterns = [
    url(r'^send-invite/$', views.SendInvite.as_view(),
        name='send-invite'),

    url(r'^send-json-invite/$', views.SendJSONInvite.as_view(),
        name='send-json-invite'),

    url(r'^accept-invite/(?P<key>\w+)/?$', views.AcceptInvite.as_view(),
        name='accept-invite'),
]