from django.contrib import admin
from .models import PredictionLog
<<<<<<< HEAD


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "score", "threshold", "flagged", "mode")
    list_filter = ("flagged", "mode", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "score", "threshold", "flagged", "mode")
=======
admin.site.register(PredictionLog)
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
