"""
Forms for creating and editing Assets and Events.

Both forms inject Bootstrap ``form-control`` classes into their widgets so
they integrate with the project's Bootstrap 4 styling without extra template
markup.
"""

from datetime import timedelta

from django import forms
from django.forms import ModelForm, TextInput, CheckboxSelectMultiple, ValidationError
from django.utils.timezone import localtime
from cal.models import Event, Asset


class AssetForm(ModelForm):
    """Simple model form for creating / editing an Asset."""

    class Meta:
        model   = Asset
        fields  = ['name', 'asset_type', 'description', 'parent', 'color']
        widgets = {'color': forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit parent choices to track assets only
        self.fields['parent'].queryset = Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK,
            parent__isnull=True,
        )
        self.fields['parent'].required = False
        self.fields['parent'].label = 'Subtrack of'
        self.fields['parent'].help_text = 'Select a parent track if this is a subtrack.'
        # Apply Bootstrap form-control class to all visible fields
        for name, field in self.fields.items():
            if name == 'color':
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean_color(self):
        import re
        color = self.cleaned_data.get('color', '').strip()
        asset_type = self.data.get('asset_type', '')
        if asset_type == Asset.AssetType.TRACK and color:
            if not re.match(r'^#[0-9A-Fa-f]{6}$', color):
                raise forms.ValidationError('Color must be a valid hex code like #3b82f6.')
        return color


def get_asset_tree():
    """
    Return a dict with all assets organised by type, queried in three hits.

    Structure::

        {
            'tracks':    [{'id': pk, 'name': str, 'subtracks': [{'id': pk, 'name': str}, ...]}, ...],
            'vehicles':  [{'id': pk, 'name': str}, ...],
            'operators': [{'id': pk, 'name': str}, ...],
        }

    Parent tracks come first (no parent), subtracks ordered by name beneath
    each parent.  Used both by ``_build_grouped_asset_choices()`` (for the
    hidden checkbox widget) and the event view (for the JS asset picker JSON).
    """
    parent_tracks = (
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK, parent__isnull=True)
        .prefetch_related('subtracks')
        .order_by('name')
    )
    return {
        'tracks': [
            {
                'id':       t.pk,
                'name':     t.name,
                'subtracks': [{'id': s.pk, 'name': s.name} for s in t.subtracks.order_by('name')],
            }
            for t in parent_tracks
        ],
        'vehicles':  [{'id': a.pk, 'name': a.name} for a in Asset.objects.filter(asset_type=Asset.AssetType.VEHICLE).order_by('name')],
        'operators': [{'id': a.pk, 'name': a.name} for a in Asset.objects.filter(asset_type=Asset.AssetType.OPERATOR).order_by('name')],
    }


def _build_grouped_asset_choices():
    """
    Return a grouped choices list for the assets checkbox widget.

    Derives from ``get_asset_tree()``.  Tracks are grouped with subtracks
    nested immediately after their parent; parent tracks with subtracks are
    labelled "Name (whole)".
    """
    tree = get_asset_tree()
    choices = []

    track_choices = []
    for t in tree['tracks']:
        if t['subtracks']:
            track_choices.append((t['id'], f"{t['name']} (whole)"))
            for s in t['subtracks']:
                track_choices.append((s['id'], f"{t['name']} \u2013 {s['name']}"))
        else:
            track_choices.append((t['id'], t['name']))
    if track_choices:
        choices.append(('Tracks', track_choices))

    if tree['vehicles']:
        choices.append(('Vehicles', [(a['id'], a['name']) for a in tree['vehicles']]))
    if tree['operators']:
        choices.append(('Operators', [(a['id'], a['name']) for a in tree['operators']]))

    return choices



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
            'assets':     CheckboxSelectMultiple(attrs={'class': 'asset-checklist'}),
        }
        fields = ['title', 'description', 'start_time', 'end_time', 'assets', 'radio_channel']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        # Configure radio_channel dropdown with a "Use track default" empty label
        self.fields['radio_channel'].choices = [('', 'Use track default')] + Event.RADIO_CHANNEL_CHOICES
        self.fields['radio_channel'].label = 'Radio Channel'
        self.fields['radio_channel'].required = False
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

        # Only one track group per reservation: multiple subtracks of the same
        # parent are OK, but mixing different parent tracks is not.
        if assets:
            track_assets = [a for a in assets if a.asset_type == Asset.AssetType.TRACK]
            if len(track_assets) > 1:
                parents = set()
                for t in track_assets:
                    parents.add(t.parent_id if t.parent_id else t.pk)
                if len(parents) > 1:
                    self.add_error('assets', 'Only one track group may be selected per reservation.')

        # End must come after start
        if start_time and end_time and start_time >= end_time:
            raise ValidationError('End time must be after start time.')

        # Minimum duration of 1 hour
        if start_time and end_time and (end_time - start_time) < timedelta(hours=1):
            raise ValidationError('Reservations must be at least 1 hour long.')

        # Conflict check — delegates to Asset.conflicting_asset_ids() for
        # parent/subtrack rules.
        if assets and start_time and end_time:
            for asset in assets:
                conflict_ids = asset.conflicting_asset_ids()
                conflicts = Event.objects.filter(
                    assets__in=conflict_ids,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).distinct()
                if self.instance and self.instance.pk:
                    conflicts = conflicts.exclude(pk=self.instance.pk)
                if conflicts.exists():
                    conflict = conflicts.first()
                    conflict_asset = conflict.assets.filter(pk__in=conflict_ids).first()
                    raise ValidationError(
                        f'Scheduling conflict: "{conflict.title}" already has '
                        f'{conflict_asset or asset} booked from '
                        f'{localtime(conflict.start_time).strftime("%b %d %I:%M %p")} to '
                        f'{localtime(conflict.end_time).strftime("%I:%M %p")}.'
                    )

        return cleaned
