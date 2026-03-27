"""
Django admin configuration for the ``cal`` application.

Registers Asset and Event models with customised list displays, filters,
search, and a bulk "approve" action for events.
"""

from django.contrib import admin
from cal.forms import EventForm
from cal.models import Asset, Event, Feedback


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    """Admin list view for assets — filterable by type."""

    list_display  = ('name', 'asset_type')
    list_filter   = ('asset_type',)
    search_fields = ('name',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    Admin list view for events.

    Includes a computed ``asset_names`` column, filters for approval status
    and asset type, a horizontal M2M widget for assets, and a bulk action
    to approve selected events in one click.
    """

    form          = EventForm
    list_display  = ('title', 'asset_names', 'start_time', 'end_time', 'created_by', 'is_approved')
    list_filter   = ('is_approved', 'assets__asset_type')
    search_fields = ('title',)
    actions       = ['approve_events']

    def asset_names(self, obj):
        """Return a comma-separated list of asset names for the list display."""
        return ', '.join(a.name for a in obj.assets.all()) or '—'
    asset_names.short_description = 'Assets'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('assets')

    def approve_events(self, request, queryset):
        """Bulk action — mark all selected events as approved."""
        queryset.update(is_approved=True)
    approve_events.short_description = 'Approve selected events'


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('subject', 'category', 'user', 'created_at', 'is_resolved')
    list_filter = ('category', 'is_resolved')
    search_fields = ('subject', 'message')
    readonly_fields = ('user', 'page_url', 'created_at')
