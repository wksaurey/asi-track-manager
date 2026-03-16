"""
Forms for creating and editing Assets and Events.

Both forms inject Bootstrap ``form-control`` classes into their widgets so
they integrate with the project's Bootstrap 4 styling without extra template
markup.
"""

from datetime import timedelta

from django.forms import ModelForm, TextInput, CheckboxSelectMultiple, ValidationError
from cal.models import Event, Asset


class AssetForm(ModelForm):
    """Simple model form for creating / editing an Asset."""

    class Meta:
        model  = Asset
        fields = ['name', 'asset_type', 'description']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply Bootstrap form-control class to every field widget
        for name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()


class EventForm(ModelForm):
    """
    Model form for creating / editing an Event.

    Custom behaviour:
    - start_time and end_time use plain TextInput widgets so the Flatpickr
      JavaScript date-picker can attach to them in the template.
    - The assets field renders as a checkbox list.
    - ``clean()`` enforces two rules:
        1. End time must be strictly after start time.
        2. No two events may book the same asset for overlapping time slots
           (the current event is excluded when editing).
    """

    class Meta:
        model = Event
        widgets = {
            'start_time': TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Pick date & time…'}),
            'end_time':   TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Pick date & time…'}),
            'assets':     CheckboxSelectMultiple(attrs={'class': 'asset-checklist'}),
        }
        fields = ['title', 'description', 'start_time', 'end_time', 'assets']

    def __init__(self, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        # Flatpickr submits dates in ISO-like format (e.g. '2026-03-12T14:30')
        self.fields['start_time'].input_formats = ('%Y-%m-%dT%H:%M',)
        self.fields['end_time'].input_formats   = ('%Y-%m-%dT%H:%M',)
        # Show all assets in the checklist
        self.fields['assets'].queryset = Asset.objects.all()
        # Add Bootstrap form-control to all fields except the checkbox group
        for name, field in self.fields.items():
            if name == 'assets':
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean(self):
        """Validate time ordering and check for asset scheduling conflicts."""
        cleaned    = super().clean()
        assets     = cleaned.get('assets')      # QuerySet of selected Asset objects
        start_time = cleaned.get('start_time')
        end_time   = cleaned.get('end_time')

        # At least one asset must be selected
        if 'assets' in cleaned and not assets:
            self.add_error('assets', 'At least one asset (track, vehicle, or operator) must be selected.')

        # End must come after start
        if start_time and end_time and start_time >= end_time:
            raise ValidationError('End time must be after start time.')

        # Minimum duration of 1 hour
        if start_time and end_time and (end_time - start_time) < timedelta(hours=1):
            raise ValidationError('Reservations must be at least 1 hour long.')

        # Conflict check — for each selected asset, ensure no other event
        # occupies an overlapping time window (start < other_end AND end > other_start).
        if assets and start_time and end_time:
            for asset in assets:
                conflicts = Event.objects.filter(
                    assets=asset,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                )
                # When editing an existing event, exclude itself from the query
                if self.instance and self.instance.pk:
                    conflicts = conflicts.exclude(pk=self.instance.pk)

                if conflicts.exists():
                    conflict = conflicts.first()
                    raise ValidationError(
                        f'Scheduling conflict: "{conflict.title}" already has '
                        f'{asset} booked from '
                        f'{conflict.start_time.strftime("%b %d %I:%M %p")} to '
                        f'{conflict.end_time.strftime("%I:%M %p")}.'
                    )

        return cleaned
