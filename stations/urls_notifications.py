from django.urls import path
from .views import list_notifications, mark_as_read

urlpatterns = [
    path("", list_notifications),
    path("<int:pk>/read/", mark_as_read),
]