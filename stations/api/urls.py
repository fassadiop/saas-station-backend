from django.urls import include, path

urlpatterns = [
    path("stations/", include("stations.urls")),
]
