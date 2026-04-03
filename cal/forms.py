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
from cal.models import Event, Asset, Feedback, RADIO_CHANNEL_CHOICES


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

    Uses three explicit fields — event_date, start_time_only, end_time_only —
    instead of the model's start_time/end_time DateTimeFields. The clean()
    method combines date + time into start_time/end_time on the server side,
    eliminating any JS sync bugs.
    """

    # Explicit date and time fields (not on the model)
    event_date      = forms.DateField(
        required=False,
        widget=TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Pick a date...', 'id': 'event-date'}),
        input_formats=['%Y-%m-%d'],
    )
    start_time_only = forms.TimeField(
        required=False,
        widget=TextInput(attrs={'autocomplete': 'off', 'placeholder': 'Start time', 'id': 'event-start-time'}),
        input_formats=['%H:%M'],
    )
    end_time_only   = forms.TimeField(
        required=False,
        widget=TextInput(attrs={'autocomplete': 'off', 'placeholder': 'End time', 'id': 'event-end-time'}),
        input_formats=['%H:%M'],
    )

    class Meta:
        model = Event
        widgets = {
            'assets': CheckboxSelectMultiple(attrs={'class': 'asset-checklist'}),
        }
        fields = ['title', 'description', 'assets', 'radio_channel']

    field_order = ['title', 'description', 'event_date', 'start_time_only', 'end_time_only', 'assets', 'radio_channel']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate date/time fields from existing instance
        if self.instance and self.instance.pk:
            if self.instance.start_time:
                lt = localtime(self.instance.start_time)
                self.fields['event_date'].initial = lt.date()
                self.fields['start_time_only'].initial = lt.time()
            if self.instance.end_time:
                self.fields['end_time_only'].initial = localtime(self.instance.end_time).time()

        self.fields['assets'].queryset = Asset.objects.all()
        self.fields['assets'].choices = _build_grouped_asset_choices()
        self.fields['radio_channel'].choices = [('', 'Use track default')] + RADIO_CHANNEL_CHOICES
        self.fields['radio_channel'].label = 'Radio Channel'
        self.fields['radio_channel'].required = False
        # Bootstrap form-control on all fields except checkboxes
        for name, field in self.fields.items():
            if name == 'assets':
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean(self):
        """Combine date + time fields, validate ordering and conflicts."""
        cleaned = super().clean()
        assets  = cleaned.get('assets')

        event_date = cleaned.get('event_date')
        start_time_only = cleaned.get('start_time_only')
        end_time_only = cleaned.get('end_time_only')

        # Combine date + time into model's start_time/end_time
        if event_date and start_time_only:
            from django.utils.timezone import make_aware
            from datetime import datetime as dt
            naive_start = dt.combine(event_date, start_time_only)
            cleaned['start_time'] = make_aware(naive_start)
        else:
            cleaned['start_time'] = None

        if event_date and end_time_only:
            from django.utils.timezone import make_aware
            from datetime import datetime as dt
            naive_end = dt.combine(event_date, end_time_only)
            cleaned['end_time'] = make_aware(naive_end)
        else:
            cleaned['end_time'] = None

        start_time = cleaned.get('start_time')
        end_time = cleaned.get('end_time')

        # At least one asset must be selected
        if 'assets' in cleaned and not assets:
            self.add_error('assets', 'At least one asset (track, vehicle, or operator) must be selected.')

        # Single track group rule
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

        # Conflict check — warn only, don't block saves.
        if assets and start_time and end_time:
            from cal.utils import get_asset_conflicts
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            for asset in assets:
                all_conflicts = get_asset_conflicts(
                    asset, start_time, end_time,
                    exclude_event_id=exclude_id,
                    approved_only=False,
                )
                if all_conflicts.exists():
                    conflict = all_conflicts.first()
                    self._conflict_warnings = getattr(self, '_conflict_warnings', [])
                    self._conflict_warnings.append(
                        f'Warning: "{conflict.title}" is already booked in this time slot. '
                        f'This event will be created as pending and require admin approval.'
                    )
                    break

        return cleaned

    def save(self, commit=True):
        """Write the combined start_time/end_time to the model before saving."""
        instance = super().save(commit=False)
        instance.start_time = self.cleaned_data.get('start_time')
        instance.end_time = self.cleaned_data.get('end_time')
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class FeedbackForm(ModelForm):
    class Meta:
        model = Feedback
        fields = ['category', 'subject', 'message', 'page_url']
        widgets = {
            'page_url': forms.HiddenInput(),
            'message': forms.Textarea(attrs={'rows': 4}),
        }
