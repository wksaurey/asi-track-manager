from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from asi_assets.models import Track, Vehicle


class Reservation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tracks = models.ManyToManyField(Track, blank=True)
    vehicles = models.ManyToManyField(Vehicle, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError("End time must be after start time.")
            duration = self.end_time - self.start_time
            if duration.total_seconds() < 3600:
                raise ValidationError("Reservation must be at least 1 hour.")

    def __str__(self):
        return f"Reservation by {self.user} from {self.start_time} to {self.end_time}"
