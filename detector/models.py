from django.db import models
class PredictionLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    reconstruction_error = models.FloatField()
    threshold = models.FloatField()
    flagged = models.BooleanField()
    mode = models.CharField(max_length=30, default="demo")
    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {'flagged' if self.flagged else 'normal'}"
