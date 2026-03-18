"""
Views for the ASI Track Manager calendar application.

Handles calendar rendering (month/week/day), event CRUD with approval
workflow, and asset management (list, create, edit, delete, detail/schedule).
Authentication is handled by Django's built-in auth framework via
@login_required and request.user.is_staff.
"""

from datetime import datetime, timedelta, date
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.views import generic
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.safestring import mark_safe
import calendar
import json

from .models import Asset, Event
from .utils import Calendar
from .forms import EventForm, AssetForm


# ── Index ─────────────────────────────────────────────────────────────────────

@login_required
def index(request):
    """Root URL — redirect to the calendar."""
    return HttpResponseRedirect(reverse('cal:calendar'))


# ── Calendar ──────────────────────────────────────────────────────────────────

class CalendarView(LoginRequiredMixin, generic.ListView):
    """
    Main calendar page supporting month, week, and day views.

    Query parameters:
        view  — 'month' (default), 'week', or 'day'.
        month — 'YYYY-M' for month view navigation.
        date  — 'YYYY-M-D' for week/day view navigation.
        asset — optional asset ID to filter displayed events.

    Context provided to the template:
        calendar       — pre-rendered HTML for the selected view.
        prev / next    — query strings for the previous/next navigation links.
        view           — current view mode string.
        assets         — active Asset queryset for the filter dropdown.
        selected_asset — currently selected asset ID (or None).
        pending_count  — number of unapproved events (admins only).
    """

    model = Event
    template_name = 'cal/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        view     = self.request.GET.get('view', 'month')
        asset_id = self.request.GET.get('asset', None)

        # Month view uses ?month=YYYY-M; week/day views use ?date=YYYY-M-D
        if view == 'month':
            param = self.request.GET.get('month', None)
        else:
            param = self.request.GET.get('date', None)

        d   = get_date(param, view)
        cal = Calendar(d.year, d.month, asset_id=asset_id)

        # Render the appropriate calendar HTML
        if view == 'week':
            html_cal = cal.formatweekview(d)
        elif view == 'day':
            html_cal = cal.formatdayview(d)
        else:
            html_cal = cal.formatmonth(withyear=True)

        context['calendar'] = mark_safe(html_cal)

        # Build the query string that represents the current position
        if view == 'month':
            current_q = f"month={d.year}-{d.month}"
        else:
            current_q = f"date={d.year}-{d.month}-{d.day}"

        if asset_id:
            current_q += f"&asset={asset_id}"

        context['current_q']      = current_q
        context['prev']           = prev_for(d, view) + (f'&asset={asset_id}' if asset_id else '')
        context['next']           = next_for(d, view) + (f'&asset={asset_id}' if asset_id else '')
        context['view']           = view
        context['assets']         = Asset.objects.all()
        context['selected_asset'] = asset_id
        return context


def get_date(req_str, view='month'):
    """
    Parse a date string from a query parameter into a ``date`` object.

    For month view, expects 'YYYY-M' and returns the first of that month.
    For week/day views, expects 'YYYY-M-D'.  Falls back to today on any
    parse error or missing value.
    """
    if req_str:
        try:
            parts = [int(x) for x in req_str.split('-')]
            if view == 'month':
                year, month = parts[0], parts[1]
                return date(year, month, day=1)
            else:
                year, month, day = parts[0], parts[1], parts[2]
                return date(year, month, day)
        except Exception:
            pass
    return datetime.today().date()


def prev_for(d, view):
    """Return a query string pointing to the previous month, week, or day."""
    if view == 'month':
        first = d.replace(day=1)
        prev_month = first - timedelta(days=1)
        return f"view=month&month={prev_month.year}-{prev_month.month}"
    elif view == 'week':
        prev_date = d - timedelta(days=7)
        return f"view={view}&date={prev_date.year}-{prev_date.month}-{prev_date.day}"
    else:
        prev_date = d - timedelta(days=1)
        return f"view=day&date={prev_date.year}-{prev_date.month}-{prev_date.day}"


def next_for(d, view):
    """Return a query string pointing to the next month, week, or day."""
    if view == 'month':
        days_in_month = calendar.monthrange(d.year, d.month)[1]
        last = d.replace(day=days_in_month)
        next_month = last + timedelta(days=1)
        return f"view=month&month={next_month.year}-{next_month.month}"
    elif view == 'week':
        next_date = d + timedelta(days=7)
        return f"view={view}&date={next_date.year}-{next_date.month}-{next_date.day}"
    else:
        next_date = d + timedelta(days=1)
        return f"view=day&date={next_date.year}-{next_date.month}-{next_date.day}"


# ── Events ────────────────────────────────────────────────────────────────────

@login_required
def event(request, event_id=None):
    """
    Create or edit an event.

    - If ``event_id`` is provided, loads an existing event for editing.
      Regular users may only edit events they created; admins can edit any.
    - On POST with valid data, saves the event.  New events record the
      creator (request.user) and are auto-approved only when the creator
      is staff.
    - ``form.save_m2m()`` is called separately because we use
      ``commit=False`` to set fields before the initial save.
    """
    if event_id:
        instance = get_object_or_404(Event, pk=event_id)
        # Regular users can only edit their own events
        if not request.user.is_staff and instance.created_by != request.user:
            return HttpResponseRedirect(reverse('cal:calendar'))
    else:
        instance = Event()

    form = EventForm(request.POST or None, instance=instance)
    if request.POST and form.is_valid():
        ev = form.save(commit=False)
        if not event_id:
            ev.created_by  = request.user
            ev.is_approved = request.user.is_staff  # admin = auto-approve; user = pending
        ev.save()
        form.save_m2m()   # persist ManyToMany (assets) after the instance is saved
        return HttpResponseRedirect(reverse('cal:calendar'))

    tracks = (
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK, parent__isnull=True)
        .prefetch_related('subtracks')
        .order_by('name')
    )
    asset_data = {
        'tracks': [
            {
                'id': t.pk,
                'name': t.name,
                'subtracks': [{'id': s.pk, 'name': s.name} for s in t.subtracks.order_by('name')],
            }
            for t in tracks
        ],
        'vehicles':  [{'id': a.pk, 'name': a.name} for a in Asset.objects.filter(asset_type=Asset.AssetType.VEHICLE).order_by('name')],
        'operators': [{'id': a.pk, 'name': a.name} for a in Asset.objects.filter(asset_type=Asset.AssetType.OPERATOR).order_by('name')],
    }
    return render(request, 'cal/event.html', {
        'form':           form,
        'event':          instance if event_id else None,
        'is_admin':       request.user.is_staff,
        'asset_data_json': mark_safe(json.dumps(asset_data)),
    })


@login_required
@require_POST
def event_delete(request, event_id):
    """Admin only — delete an event.  Requires POST to prevent accidental deletion."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.delete()
    return HttpResponseRedirect(reverse('cal:calendar'))


@login_required
@require_POST
def event_approve(request, event_id):
    """Admin only — mark a pending event as approved.  Redirects to the pending list."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.is_approved = True
    event_obj.save(update_fields=['is_approved'])
    return HttpResponseRedirect(reverse('cal:pending_events'))


@login_required
def pending_events(request):
    """Admin only — list all events awaiting approval."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    events = Event.objects.filter(is_approved=False).order_by('start_time').prefetch_related('assets')
    return render(request, 'cal/pending_events.html', {'events': events})


# ── Asset management ──────────────────────────────────────────────────────────

@login_required
def asset_list(request):
    """Display all assets grouped by type. Requires login."""
    assets = Asset.objects.all()
    grouped_assets = []
    for type_value, type_label in Asset.AssetType.choices:
        group = [a for a in assets if a.asset_type == type_value]
        if group:
            grouped_assets.append((type_label, type_value, group))
    return render(request, 'cal/asset_list.html', {
        'assets': assets,
        'grouped_assets': grouped_assets,
    })


@login_required
def asset_create(request):
    """Admin only — show a form to create a new asset."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    initial = {}
    parent_id = request.GET.get('parent')
    if parent_id:
        initial = {'asset_type': 'track', 'parent': parent_id}
    form = AssetForm(request.POST or None, initial=initial)
    if request.POST and form.is_valid():
        saved = form.save()
        if saved.parent_id:
            return HttpResponseRedirect(reverse('cal:asset_edit', args=[saved.parent_id]))
        return HttpResponseRedirect(reverse('cal:asset_list'))
    return render(request, 'cal/asset_form.html', {'form': form, 'page_title': 'New Asset'})


@login_required
def asset_edit(request, asset_id):
    """Admin only — edit an existing asset's details."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    instance = get_object_or_404(Asset, pk=asset_id)
    form = AssetForm(request.POST or None, instance=instance)
    if request.POST and form.is_valid():
        form.save()
        return HttpResponseRedirect(reverse('cal:asset_list'))
    subtracks = instance.subtracks.order_by('name') if instance.asset_type == Asset.AssetType.TRACK and not instance.parent_id else None
    return render(request, 'cal/asset_form.html', {
        'form':       form,
        'page_title': f'Edit — {instance.name}',
        'asset':      instance,
        'subtracks':  subtracks,
    })


@login_required
@require_POST
def asset_delete(request, asset_id):
    """Admin only — delete an asset.  Requires POST for safety."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:asset_list'))
    asset = get_object_or_404(Asset, pk=asset_id)
    parent_id = asset.parent_id
    asset.delete()
    if parent_id:
        return HttpResponseRedirect(reverse('cal:asset_edit', args=[parent_id]))
    return HttpResponseRedirect(reverse('cal:asset_list'))


# ── Asset availability / schedule ─────────────────────────────────────────────

@login_required
def asset_detail(request, asset_id):
    """
    Show an asset's schedule page.

    Displays two sections:
    - Upcoming events within the next 30 days.
    - The 10 most recent past events for historical reference.
    """
    asset   = get_object_or_404(Asset, pk=asset_id)
    today   = datetime.today().date()
    horizon = today + timedelta(days=30)

    upcoming = asset.events.prefetch_related('assets').filter(
        start_time__date__gte=today,
        start_time__date__lte=horizon,
    ).order_by('start_time')

    past = asset.events.prefetch_related('assets').filter(
        start_time__date__lt=today,
    ).order_by('-start_time')[:10]

    return render(request, 'cal/asset_detail.html', {
        'asset':    asset,
        'upcoming': upcoming,
        'past':     past,
        'today':    today,
        'horizon':  horizon,
    })
