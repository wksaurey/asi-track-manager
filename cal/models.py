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
        VEHICLE  = 'vehicle',  'Heavy Equipment Vehicle'
        TRACK    = 'track',    'Track'
        OPERATOR = 'operator', 'Operator'

    name        = models.CharField(max_length=200)
    asset_type  = models.CharField(max_length=20, choices=AssetType.choices)
    description = models.TextField(blank=True)
    parent      = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='subtracks',
        help_text='Parent track (only for subtracks)',
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
    description = models.TextField()
    start_time   = models.DateTimeField()
    end_time     = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end   = models.DateTimeField(null=True, blank=True)
    assets      = models.ManyToManyField(
        Asset,
        blank=True,
        related_name='events',
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
    created_at  = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.title

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
        t_s = self.start_time.strftime('%I:%M').lstrip('0') or '12:00'
        t_e = self.end_time.strftime('%I:%M').lstrip('0') or '12:00'
        if self.start_time.strftime('%p') == self.end_time.strftime('%p'):
            return f'{t_s}\u2013{t_e}\u00a0{self.end_time.strftime("%p")}'
        return (
            f'{t_s}\u00a0{self.start_time.strftime("%p")}'
            f'\u2013{t_e}\u00a0{self.end_time.strftime("%p")}'
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
        return (
            f'<a class="event-link" href="{url}">'
            f'<span class="event-title">{escape(self.title)}</span>'
            f'<span class="event-time">{self._time_range}</span>'
            f'{pending}'
            f'{self.asset_badge_html}'
            f'</a>'
        )
