
from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok"}, status=200)


def ready(request):
    return JsonResponse({"status": "ready"}, status=200)
