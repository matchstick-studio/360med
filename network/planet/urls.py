
from django.urls import path, include
from network.planet import views


planet_patterns = [
    path('', views.blog_list, name="blog_list"),
]
urlpatterns = [

    # Get the reset/ urls
    path(r'', include(planet_patterns)),

]
