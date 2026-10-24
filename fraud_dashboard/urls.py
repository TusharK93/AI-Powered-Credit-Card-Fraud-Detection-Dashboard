from django.contrib import admin
from django.urls import path
from detector import views

def ready(request):
    """Basic readiness endpoint."""
    return JsonResponse({"status": "ready"}, status=200)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("health/", views.health, name="health"),

    path("ready/", views.ready, name="ready"),
    path("observability/status/", views.observability_status, name="observability-status"),

]
