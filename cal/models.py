"""
Models for the ASI Track Manager calendar application.

Defines two core models:
- Asset: a reservable resource (vehicle, track, or operator).
- Event: a scheduled reservation that can reference one or more assets.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.html import escape
from django.utils.timezone import localtime

# Predefined palette for track colors.  New tracks auto-pick the first unused
# color; all 16 are available for manual override via the asset edit form.
TRACK_COLOR_PALETTE = [
    # Reds / oranges / yellows  (~0° → 60° hue)
    '#dc2626',  # red-600      — 4.69:1
    '#c2410c',  # orange-700   — 5.17:1
    '#b45309',  # amber-700    — 5.05:1
    '#a16207',  # yellow-700   — 4.93:1
    # Greens  (~80° → 175° hue)
    '#4d7c0f',  # lime-700     — 5.00:1
    '#15803d',  # green-700    — 5.07:1
    '#047857',  # emerald-700  — 5.53:1
    '#0f766e',  # teal-700     — 5.50:1
    # Blues  (~185° → 240° hue)
    '#0e7490',  # cyan-700     — 5.38:1
    '#0369a1',  # sky-700      — 5.97:1
    '#2563eb',  # blue-600     — 5.20:1
    '#4f46e5',  # indigo-600   — 6.29:1
    # Purples / pinks  (~260° → 340° hue)
    '#7c3aed',  # violet-600   — 5.71:1
    '#9333ea',  # purple-600   — 5.38:1
    '#c026d3',  # fuchsia-600  — 4.71:1
    '#db2777',  # pink-600     — 4.61:1
]

# Radio channel choices shared by Asset and Event models.
RADIO_CHANNEL_CHOICES = [(ch, f'Ch {ch}') for ch in range(1, 17)]


class Asset(models.Model):
    """
    A reservable resource on the ASI Mendon Campus.

    Each asset belongs to one of three types (vehicle, track, operator) and
    can be linked to many events via a ManyToMany relationship.

    Tracks may optionally have a parent track (subtrack support).  A track
    with parent=None is a top-level track; a track with parent set is a
    subtrack of that parent.  Only asset_type='track' assets should use
    this field.
    """

    class AssetType(models.TextChoices):
        VEHICLE  = 'vehicle',  'Vehicle'
        TRACK    = 'track',    'Track'
        OPERATOR = 'operator', 'Operator'

    name        = models.CharField(max_length=200)
    asset_type  = models.CharField(max_length=20, choices=AssetType.choices)
    description = models.TextField(blank=True)
    color       = models.CharField(
        max_length=7,
        blank=True,
        default='',
        help_text='Hex color for this track (e.g. #3b82f6). Auto-assigned if left blank.',
    )
    parent      = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='subtracks',
        help_text='Parent track (only for subtracks)',
    )
    radio_channel = models.IntegerField(
        null=True,
        blank=True,
        choices=RADIO_CHANNEL_CHOICES,
        help_text='Radio channel assigned to this track (11–16).',
    )
    is_active = models.BooleanField(
        default=False,
        help_text='Whether this track is currently active/unsafe to approach.',
    )

    class Meta:
        ordering = ['asset_type', 'name']
        # Top-level assets (parent=None) must be unique by name.
        # Subtracks are unique within their parent (handled in clean()).
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(parent__isnull=True),
                name='unique_top_level_asset_name',
            )
        ]

    @classmethod
    def next_available_color(cls):
        """Return the first palette color not yet used by any track, cycling if needed."""
        used = set(
            cls.objects.filter(asset_type=cls.AssetType.TRACK)
            .exclude(color='')
            .values_list('color', flat=True)
        )
        for c in TRACK_COLOR_PALETTE:
            if c not in used:
                return c
        # All colors taken — cycle by count
        count = cls.objects.filter(asset_type=cls.AssetType.TRACK).exclude(color='').count()
        return TRACK_COLOR_PALETTE[count % len(TRACK_COLOR_PALETTE)]

    def save(self, *args, **kwargs):
        if self.asset_type == self.AssetType.TRACK and not self.color:
            self.color = self.next_available_color()
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.parent_id is not None:
            siblings = Asset.objects.filter(parent_id=self.parent_id, name=self.name)
            if self.pk:
                siblings = siblings.exclude(pk=self.pk)
            if siblings.exists():
                raise ValidationError({'name': 'A subtrack with this name already exists under this parent track.'})

    def __str__(self):
        return f'{self.get_asset_type_display()} — {self.name}'

    def conflicting_asset_ids(self):
        """
        Return the set of asset IDs that conflict with booking this asset.

        - Booking a parent track conflicts with itself AND all its subtracks.
        - Booking a subtrack conflicts with itself AND its parent track.
        - Sibling subtracks do NOT conflict with each other.
        """
        ids = {self.pk}
        if self.asset_type == Asset.AssetType.TRACK:
            if self.parent_id is None:
                ids.update(self.subtracks.values_list('pk', flat=True))
            else:
                ids.add(self.parent_id)
        return ids

    @property
    def display_name(self):
        """
        Return a user-facing label for this asset.

        - Subtrack: 'Parent Name – Subtrack Name'
        - Parent track (has subtracks): 'Name (whole)'
        - Everything else: just 'Name'
        """
        if self.parent_id:
            return f'{self.parent.name} \u2013 {self.name}'
        return self.name


class Event(models.Model):
    """
    A scheduled reservation on the calendar.

    Events are created by both regular users and admins.  Admin-created
    events are auto-approved, while user-created events default to pending
    (is_approved=False) until an admin approves them.

    The ``assets`` ManyToMany field links an event to the resources it
    reserves, enabling conflict detection in the booking form.
    """

    title       = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time   = models.DateTimeField(null=True, blank=True)
    end_time     = models.DateTimeField(null=True, blank=True)
    is_stopped  = models.BooleanField(default=False)
    assets      = models.ManyToManyField(
        Asset,
        blank=True,
        related_name='events',
    )
    # Per-event radio channel override (None = inherit from track)
    radio_channel = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        choices=RADIO_CHANNEL_CHOICES,
        help_text='Override radio channel for this event (11–16). Leave blank to use the track default.',
    )
    # Auth / approval fields
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events',
    )
    is_approved = models.BooleanField(default=False)
    is_impromptu = models.BooleanField(
        default=False,
        help_text='Set automatically for unplanned events created from the dashboard.',
    )
    created_at  = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.title

    # ── Segment-based computed properties ─────────────────────────────────

    @property
    def current_segment(self):
        """Return the open (end=None) segment, or None."""
        return self.segments.filter(end__isnull=True).first()

    @property
    def is_currently_active(self):
        return self.current_segment is not None

    @property
    def total_actual_seconds(self):
        total = 0
        for seg in self.segments.all():
            if seg.end:
                total += (seg.end - seg.start).total_seconds()
        return total

    @property
    def total_actual_display(self):
        """Human-readable total actual time (e.g. '1h 30m')."""
        secs = self.total_actual_seconds
        if secs < 60:
            return '<1m'
        m = int(secs) // 60
        h, m = divmod(m, 60)
        if h and m:
            return f'{h}h {m}m'
        return f'{h}h' if h else f'{m}m'

    @property
    def actual_start(self):
        """First segment start (backward compat)."""
        first = self.segments.order_by('start').first()
        return first.start if first else None

    @property
    def actual_end(self):
        """Last closed segment end, or None."""
        last = self.segments.filter(end__isnull=False).order_by('-end').first()
        return last.end if last else None

    @property
    def effective_radio_channel(self):
        """
        Return the radio channel in effect for this event.

        - The event's own ``radio_channel`` if explicitly set.
        - Otherwise, the ``radio_channel`` of the first track-type asset.
        - Otherwise, ``None``.
        """
        if self.radio_channel is not None:
            return self.radio_channel
        for asset in self.assets.all():
            if asset.asset_type == Asset.AssetType.TRACK and asset.radio_channel is not None:
                return asset.radio_channel
        return None

    # ── Display helpers used by calendar templates ─────────────────────────

    @property
    def asset_css_class(self):
        """
        Return a CSS class based on the event's asset types.

        - 'event-vehicle', 'event-track', or 'event-operator' when all
          attached assets share the same type.
        - 'event-multi' when multiple asset types are mixed.
        - 'event-none' when no assets are attached.
        """
        asset_list = list(self.assets.all())
        if not asset_list:
            return 'event-none'
        types = {a.asset_type for a in asset_list}
        if len(types) == 1:
            return f'event-{asset_list[0].asset_type}'
        return 'event-multi'

    @property
    def asset_badge_html(self):
        """Return inline HTML badge spans for each attached asset, colour-coded by type."""
        return ''.join(
            f'<span class="asset-badge badge-{a.asset_type}">{escape(a.display_name)}</span>'
            for a in self.assets.all()
        )

    @property
    def _time_range(self):
        """
        Return a compact time range string for the event.

        Omits the AM/PM suffix on the start time when both times share the
        same period, e.g. '8:30-10:00 AM' instead of '8:30 AM-10:00 AM'.
        Uses an en-dash and non-breaking spaces for clean rendering.
        """
        if not self.start_time or not self.end_time:
            return 'Impromptu'
        local_s = localtime(self.start_time)
        local_e = localtime(self.end_time)
        t_s = local_s.strftime('%I:%M').lstrip('0') or '12:00'
        t_e = local_e.strftime('%I:%M').lstrip('0') or '12:00'
        if local_s.strftime('%p') == local_e.strftime('%p'):
            return f'{t_s}\u2013{t_e}\u00a0{local_e.strftime("%p")}'
        return (
            f'{t_s}\u00a0{local_s.strftime("%p")}'
            f'\u2013{t_e}\u00a0{local_e.strftime("%p")}'
        )

    @property
    def get_html_url(self):
        """
        Return an HTML anchor tag for rendering this event in the calendar.

        Includes the event title, formatted time range, a PENDING badge
        (if not yet approved), and colour-coded asset badges.
        """
        url     = reverse('cal:event_edit', args=(self.id,))
        pending = (
            '<span class="pending-badge">PENDING</span>'
            if not self.is_approved else ''
        )
        creator = (
            f'<span class="event-creator">{escape(self.created_by.username)}</span>'
            if self.created_by else ''
        )
        return (
            f'<a class="event-link" href="{url}">'
            f'<span class="event-title">{escape(self.title)}</span>'
            f'<span class="event-time">{self._time_range}</span>'
            f'{pending}'
            f'{creator}'
            f'{self.asset_badge_html}'
            f'</a>'
        )


class ActualTimeSegment(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='segments')
    start = models.DateTimeField()
    end = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start']

    def __str__(self):
        end_str = localtime(self.end).isoformat() if self.end else 'open'
        return f'Segment {self.pk}: {localtime(self.start).isoformat()} — {end_str}'

    @property
    def duration_display(self):
        """Human-readable segment duration (e.g. '45m')."""
        if not self.end:
            return None
        secs = (self.end - self.start).total_seconds()
        if secs < 60:
            return '<1m'
        m = int(secs) // 60
        h, m = divmod(m, 60)
        if h and m:
            return f'{h}h {m}m'
        return f'{h}h' if h else f'{m}m'


class Feedback(models.Model):
    class Category(models.TextChoices):
        BUG = 'bug', 'Bug Report'
        FEATURE = 'feature', 'Feature Request'
        OTHER = 'other', 'Other'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='feedback',
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.BUG)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    page_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.get_category_display()}] {self.subject}'
