from django.contrib import admin
from django.urls import path
from detector import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("health/", views.health, name="health"),
<<<<<<< HEAD
    path("ready/", views.ready, name="ready"),
    path("observability/status/", views.observability_status, name="observability-status"),
=======
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
]
