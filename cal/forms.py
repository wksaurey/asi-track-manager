"""
Forms for creating and editing Assets and Events.

Both forms inject Bootstrap ``form-control`` classes into their widgets so
they integrate with the project's Bootstrap 4 styling without extra template
markup.
"""

from datetime import timedelta

from django import forms
from django.forms import ModelForm, TextInput, CheckboxSelectMultiple, ValidationError
from cal.models import Event, Asset


class AssetForm(ModelForm):
    """Simple model form for creating / editing an Asset."""

    class Meta:
        model  = Asset
        fields = ['name', 'asset_type', 'description', 'parent']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit parent choices to track assets only
        self.fields['parent'].queryset = Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK,
            parent__isnull=True,
        )
        self.fields['parent'].required = False
        # Apply Bootstrap form-control class to every field widget
        for name, field in self.fields.items():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()


class GroupedAssetCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """
    A CheckboxSelectMultiple subclass that renders assets grouped by type,
    with subtracks nested under their parent track.

    Usage: pass ``grouped_choices`` to __init__ as a list of
    (group_label, [(value, label), ...]) tuples.
    """

    def optgroups(self, name, value, attrs=None):
        # Delegate to the standard implementation; grouping is achieved via
        # the choices structure (list of (group, [(val, label), ...]) tuples).
        return super().optgroups(name, value, attrs)


def _build_grouped_asset_choices():
    """
    Return a grouped choices list for assets, suitable for a grouped checkbox widget.

    Structure:
      [
        ('Tracks', [(pk, display_name), ...]),
        ('Vehicles', [(pk, display_name), ...]),
        ('Operators', [(pk, display_name), ...]),
      ]

    Within Tracks:
      - Parent tracks (no parent) come first, labeled "Name (whole)" if they have subtracks.
      - Their subtracks follow immediately, labeled "Parent – Subtrack".
      - Tracks with no subtracks appear as plain "Name".
    """
    choices = []

    # ── Tracks (with subtrack grouping) ───────────────────────────────────
    track_choices = []
    parent_tracks = list(
        Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK,
            parent__isnull=True,
        ).prefetch_related('subtracks').order_by('name')
    )
    for track in parent_tracks:
        subtracks = list(track.subtracks.order_by('name'))
        if subtracks:
            track_choices.append((track.pk, f'{track.name} (whole)'))
            for sub in subtracks:
                track_choices.append((sub.pk, f'{track.name} \u2013 {sub.name}'))
        else:
            track_choices.append((track.pk, track.name))

    if track_choices:
        choices.append(('Tracks', track_choices))

    # ── Vehicles ───────────────────────────────────────────────────────────
    vehicle_choices = [
        (a.pk, a.name)
        for a in Asset.objects.filter(asset_type=Asset.AssetType.VEHICLE).order_by('name')
    ]
    if vehicle_choices:
        choices.append(('Vehicles', vehicle_choices))

    # ── Operators ──────────────────────────────────────────────────────────
    operator_choices = [
        (a.pk, a.name)
        for a in Asset.objects.filter(asset_type=Asset.AssetType.OPERATOR).order_by('name')
    ]
    if operator_choices:
        choices.append(('Operators', operator_choices))

    return choices


def _get_conflicting_asset_ids(asset):
    """
    Return the set of asset IDs that conflict with booking ``asset``.

    Rules:
    - Booking a parent track conflicts with itself AND all its subtracks.
    - Booking a subtrack conflicts with itself AND its parent track.
    - Sibling subtracks do NOT conflict with each other.
    """
    ids = {asset.pk}
    if asset.asset_type == Asset.AssetType.TRACK:
        if asset.parent_id is None:
            # This is a parent track — conflicts with all its subtracks too
            ids.update(asset.subtracks.values_list('pk', flat=True))
        else:
            # This is a subtrack — conflicts with its parent track too
            ids.add(asset.parent_id)
    return ids


class EventForm(ModelForm):
    """
    Model form for creating / editing an Event.

    Custom behaviour:
    - start_time and end_time use plain TextInput widgets so the Flatpickr
      JavaScript date-picker can attach to them in the template.
    - The assets field renders as a grouped checkbox list.
    - ``clean()`` enforces two rules:
        1. End time must be strictly after start time.
        2. No two events may book the same asset for overlapping time slots
           (the current event is excluded when editing).
        3. Subtrack conflict rules: booking a parent conflicts with its
           subtracks and vice versa; siblings do NOT conflict.
    """

    class Meta:
        model = Event
        widgets = {
            'start_time': TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Pick date & time…'}),
            'end_time':   TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Pick date & time…'}),
            'assets':     GroupedAssetCheckboxSelectMultiple(attrs={'class': 'asset-checklist'}),
        }
        fields = ['title', 'description', 'start_time', 'end_time', 'assets']

    def __init__(self, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        # Flatpickr submits dates in ISO-like format (e.g. '2026-03-12T14:30')
        self.fields['start_time'].input_formats = ('%Y-%m-%dT%H:%M',)
        self.fields['end_time'].input_formats   = ('%Y-%m-%dT%H:%M',)
        # Keep the full queryset so ModelMultipleChoiceField validation works.
        # Override the field's choices to use the grouped structure for display.
        # Django ModelMultipleChoiceField allows setting .choices directly;
        # this is stored as _choices and returned by the choices property,
        # bypassing the default ModelChoiceIterator while keeping queryset intact.
        self.fields['assets'].queryset = Asset.objects.all()
        self.fields['assets'].choices = _build_grouped_asset_choices()
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

        # Conflict check — for each selected asset, check against the set of
        # asset IDs that would conflict (including parent/subtrack relationships).
        if assets and start_time and end_time:
            for asset in assets:
                conflict_ids = _get_conflicting_asset_ids(asset)
                conflicts = Event.objects.filter(
                    assets__in=conflict_ids,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).distinct()
                # When editing an existing event, exclude itself from the query
                if self.instance and self.instance.pk:
                    conflicts = conflicts.exclude(pk=self.instance.pk)

                if conflicts.exists():
                    conflict = conflicts.first()
                    # Find which conflicting asset triggered the error
                    conflict_asset = conflict.assets.filter(pk__in=conflict_ids).first()
                    asset_label = asset.display_name
                    raise ValidationError(
                        f'Scheduling conflict: "{conflict.title}" already has '
                        f'{conflict_asset or asset} booked from '
                        f'{conflict.start_time.strftime("%b %d %I:%M %p")} to '
                        f'{conflict.end_time.strftime("%I:%M %p")}.'
                    )

        return cleaned
