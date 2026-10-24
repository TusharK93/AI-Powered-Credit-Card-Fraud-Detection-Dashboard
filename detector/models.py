
"""Minimal operational history for demo scoring events; no raw inputs are stored."""
from django.db import models


class PredictionLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField()
    threshold = models.FloatField()
    flagged = models.BooleanField()
    mode = models.CharField(max_length=80, default="heuristic_demo")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="predlog_created_desc_idx")]

    def __str__(self):
        outcome = "flagged" if self.flagged else "not flagged"
        return f"{self.created_at:%Y-%m-%d %H:%M} - {outcome}"

from django.db import models
class PredictionLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    reconstruction_error = models.FloatField()
    threshold = models.FloatField()
    flagged = models.BooleanField()
    mode = models.CharField(max_length=30, default="demo")
    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {'flagged' if self.flagged else 'normal'}"

