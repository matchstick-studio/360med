
from django.conf import settings
from django.urls import path, include
import debug_toolbar
from django.conf.urls.static import static
from network.forum.urls import forum_patterns
from network.accounts.views import image_upload_view
import network.accounts.urls as accounts_urls
from network.planet.urls import planet_patterns


urlpatterns = [

    # Mount forum urls on root.
    path(r'', include(forum_patterns)),

    # Include planets urls
    path(r'planet/', include(planet_patterns)),

    # Include the accounts urls
    path(r'accounts/', include(accounts_urls)),

]

if settings.PAGEDOWN_IMAGE_UPLOAD_ENABLED:

    urlpatterns += [
        # Pagedown image upload url.
        path('pagedown/image-upload/', image_upload_view, name="pagedown-image-upload")
    ]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT, show_indexes=True)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT, show_indexes=True)
