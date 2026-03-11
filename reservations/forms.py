from django import forms
from django.core.exceptions import ValidationError

from .models import Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ('tracks', 'vehicles', 'start_time', 'end_time')
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        tracks = cleaned_data.get('tracks')
        vehicles = cleaned_data.get('vehicles')

        if start_time and end_time:
            if end_time <= start_time:
                raise ValidationError("End time must be after start time.")
            duration = end_time - start_time
            if duration.total_seconds() < 3600:
                raise ValidationError("Reservation must be at least 1 hour.")

        if not tracks and not vehicles:
            raise ValidationError("A reservation must include at least one track or vehicle.")

        # Double-booking check
        if start_time and end_time:
            overlapping = Reservation.objects.filter(
                start_time__lt=end_time,
                end_time__gt=start_time,
            )
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)

            if tracks:
                track_conflict = overlapping.filter(tracks__in=tracks).exists()
                if track_conflict:
                    raise ValidationError("One or more selected tracks are already reserved during this time.")

            if vehicles:
                vehicle_conflict = overlapping.filter(vehicles__in=vehicles).exists()
                if vehicle_conflict:
                    raise ValidationError("One or more selected vehicles are already reserved during this time.")

        return cleaned_data
