
from django.contrib import admin
from .models import PredictionLog


@admin.register(PredictionLog)
class PredictionLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "reconstruction_error",
        "threshold",
        "flagged",
        "mode",
    )
    list_filter = ("flagged", "mode", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "reconstruction_error",
        "threshold",
        "flagged",
        "mode",
    )
