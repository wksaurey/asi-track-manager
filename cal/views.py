"""
Views for the ASI Track Manager calendar application.

Handles calendar rendering (month/week/day), event CRUD with approval
workflow, and asset management (list, create, edit, delete, detail/schedule).
Authentication is handled by Django's built-in auth framework via
@login_required and request.user.is_staff.
"""

import calendar
import json
from collections import defaultdict
from datetime import datetime, timedelta, date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import ExtractHour, TruncDate
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views import generic
from django.views.decorators.http import require_POST

from .models import Asset, Event
from .utils import Calendar
from .forms import EventForm, AssetForm, get_asset_tree


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
    return timezone.now().date()


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

    return render(request, 'cal/event.html', {
        'form':            form,
        'event':           instance if event_id else None,
        'is_admin':        request.user.is_staff,
        'asset_data_json': get_asset_tree(),
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
    next_url = request.POST.get('next', '')
    if next_url and url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
        return HttpResponseRedirect(next_url)
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
    assets = Asset.objects.prefetch_related('subtracks').all()
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
        saved = form.save()
        if saved.parent_id:
            return HttpResponseRedirect(reverse('cal:asset_edit', args=[saved.parent_id]))
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
    today   = timezone.now().date()
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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    """
    Control Center Dashboard — admin only.

    Renders ``cal/dashboard.html`` with all track-type assets passed in context.
    """
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    tracks = Asset.objects.filter(asset_type=Asset.AssetType.TRACK)
    return render(request, 'cal/dashboard.html', {'tracks': tracks})


@login_required
def dashboard_events_api(request):
    """
    JSON API — admin only.

    Returns approved events for a specific day grouped by track asset name.
    Accepts an optional ``?date=YYYY-MM-DD`` query parameter; defaults to today.

    Response shape::

        {
            "date": "YYYY-MM-DD",
            "tracks": {
                "<track name>": {
                    "id": <asset pk>,
                    "events": [
                        {
                            "id": <event pk>,
                            "title": "...",
                            "description": "...",
                            "start_time": "<ISO 8601>",
                            "end_time": "<ISO 8601>",
                            "is_approved": true
                        },
                        ...
                    ]
                },
                ...
            }
        }
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    today = timezone.now().date()
    date_param = request.GET.get('date')
    if date_param:
        try:
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            target_date = today
    else:
        target_date = today

    track_events_qs = Event.objects.filter(
        is_approved=True, start_time__date=target_date
    ).order_by('start_time')

    tracks = Asset.objects.filter(
        asset_type=Asset.AssetType.TRACK
    ).prefetch_related(
        Prefetch('events', queryset=track_events_qs, to_attr='day_events')
    )

    data = {}
    for track in tracks:
        data[track.display_name] = {
            'id': track.pk,
            'color': track.color,
            'events': [
                {
                    'id':           ev.pk,
                    'title':        ev.title,
                    'description':  ev.description,
                    'start_time':   ev.start_time.isoformat(),
                    'end_time':     ev.end_time.isoformat(),
                    'is_approved':  ev.is_approved,
                    'actual_start': ev.actual_start.isoformat() if ev.actual_start else None,
                    'actual_end':   ev.actual_end.isoformat() if ev.actual_end else None,
                }
                for ev in track.day_events
            ],
        }

    return JsonResponse({'date': target_date.isoformat(), 'tracks': data})


# ── Analytics ─────────────────────────────────────────────────────────────────

@login_required
def analytics(request):
    if not request.user.is_staff:
        return redirect('cal:calendar')
    return render(request, 'cal/analytics.html')


@login_required
def analytics_api(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    today = timezone.now().date()
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else today - timedelta(days=today.weekday())
    except ValueError:
        start_date = today - timedelta(days=today.weekday())
    try:
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else start_date + timedelta(days=6)
    except ValueError:
        end_date = start_date + timedelta(days=6)

    # Base queryset — all events in range
    events = Event.objects.filter(
        start_time__date__gte=start_date,
        start_time__date__lte=end_date,
        is_approved=True,
    )

    # Prefetch all events once to avoid N+1 queries per asset.
    # SQLite lacks duration math, so we compute in Python from a single queryset.
    all_events = list(events.prefetch_related('assets'))

    # Build asset_id → [event, ...] mapping for O(1) lookups
    events_by_asset = defaultdict(list)
    for ev in all_events:
        for asset in ev.assets.all():
            events_by_asset[asset.pk].append(ev)

    # 1. Track utilization
    track_assets = Asset.objects.filter(asset_type=Asset.AssetType.TRACK)
    track_utilization = []
    for track in track_assets:
        track_events = events_by_asset.get(track.pk, [])
        scheduled_secs = sum(
            (e.end_time - e.start_time).total_seconds()
            for e in track_events
        )
        actual_secs = sum(
            (e.actual_end - e.actual_start).total_seconds()
            for e in track_events
            if e.actual_start and e.actual_end
        )
        track_utilization.append({
            'name': track.display_name,
            'color': track.color or '#10b981',
            'scheduled_hours': round(scheduled_secs / 3600, 1),
            'actual_hours': round(actual_secs / 3600, 1),
            'event_count': len(track_events),
        })

    # 2. Schedule accuracy — for events with actual times
    start_deltas = []
    end_deltas = []
    for e in all_events:
        if e.actual_start and e.actual_end:
            start_deltas.append((e.actual_start - e.start_time).total_seconds() / 60)
            end_deltas.append((e.actual_end - e.end_time).total_seconds() / 60)

    schedule_accuracy = {
        'avg_start_delta_minutes': round(sum(start_deltas) / len(start_deltas), 1) if start_deltas else 0,
        'avg_end_delta_minutes': round(sum(end_deltas) / len(end_deltas), 1) if end_deltas else 0,
        'events_with_actuals': len(start_deltas),
        'total_events': len(all_events),
    }

    # 3. Usage trends — events per day
    daily = (
        events
        .annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    # Fill in missing days with 0
    day_counts = {str(row['day']): row['count'] for row in daily}
    labels = []
    counts = []
    d = start_date
    while d <= end_date:
        labels.append(str(d))
        counts.append(day_counts.get(str(d), 0))
        d += timedelta(days=1)

    usage_trends = {'labels': labels, 'counts': counts}

    # 4. Peak hours
    peak = (
        events
        .annotate(hour=ExtractHour('start_time'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )
    peak_hours = [{'hour': r['hour'], 'count': r['count']} for r in peak]

    # 5. User activity
    all_events_in_range = Event.objects.filter(
        start_time__date__gte=start_date,
        start_time__date__lte=end_date,
    )
    user_data = (
        all_events_in_range
        .filter(created_by__isnull=False)
        .values('created_by__username')
        .annotate(
            total=Count('id'),
            approved=Count('id', filter=Q(is_approved=True)),
        )
        .order_by('-total')
    )
    user_activity = [
        {
            'username': r['created_by__username'],
            'total': r['total'],
            'approved': r['approved'],
            'pending': r['total'] - r['approved'],
        }
        for r in user_data
    ]

    # 6. Asset usage (vehicles and operators)
    non_track_assets = Asset.objects.exclude(asset_type=Asset.AssetType.TRACK)
    asset_usage = []
    for asset in non_track_assets:
        asset_events = events_by_asset.get(asset.pk, [])
        sched_secs = sum(
            (e.end_time - e.start_time).total_seconds()
            for e in asset_events
        )
        asset_usage.append({
            'name': asset.name,
            'type': asset.asset_type,
            'event_count': len(asset_events),
            'total_hours': round(sched_secs / 3600, 1),
        })

    return JsonResponse({
        'range': {'start': str(start_date), 'end': str(end_date)},
        'track_utilization': track_utilization,
        'schedule_accuracy': schedule_accuracy,
        'usage_trends': usage_trends,
        'peak_hours': peak_hours,
        'user_activity': user_activity,
        'asset_usage': asset_usage,
    })


@login_required
@require_POST
def dashboard_stamp_actual(request, event_id):
    """
    JSON API — admin only.

    Stamps actual start or end times on an event.
    Accepts POST with a JSON body containing an ``action`` field:

    - ``"start"``       — sets ``actual_start`` to now (or ``time`` if provided).
    - ``"end"``         — sets ``actual_end`` to now (or ``time`` if provided).
    - ``"clear_start"`` — clears ``actual_start``.
    - ``"clear_end"``   — clears ``actual_end``.

    Optional ``time`` field: an ISO 8601 string or ``"HH:MM"`` (combined with
    the event's date).  When omitted, the current time is used.

    URL: /cal/api/event/<event_id>/stamp/
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        event = Event.objects.get(pk=event_id)
    except Event.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    action = body.get('action')
    time_str = body.get('time')  # Optional: ISO 8601 string or "HH:MM"

    # Parse the custom time if provided
    custom_time = None
    if time_str:
        try:
            # Try full ISO format first
            custom_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            if timezone.is_naive(custom_time):
                custom_time = timezone.make_aware(custom_time)
        except (ValueError, TypeError):
            try:
                # Try HH:MM format — combine with event's date
                parts = time_str.strip().split(':')
                if len(parts) == 2:
                    h, m = int(parts[0]), int(parts[1])
                    event_date = event.start_time.date()
                    naive = datetime.combine(event_date, datetime.min.time().replace(hour=h, minute=m))
                    custom_time = timezone.make_aware(naive)
            except (ValueError, TypeError):
                pass

    # ── Validation ──────────────────────────────────────────────
    if action == 'end':
        if not event.actual_start:
            return JsonResponse(
                {'error': 'Cannot stamp end time before start time is recorded.'},
                status=400,
            )
        if custom_time and custom_time < event.actual_start:
            return JsonResponse(
                {'error': 'End time cannot be before start time.'},
                status=400,
            )
    if action == 'start' and custom_time:
        event_date = event.start_time.date()
        event_midnight = timezone.make_aware(datetime.combine(event_date, datetime.min.time()))
        if custom_time < event_midnight - timedelta(hours=24) or custom_time > event_midnight + timedelta(hours=48):
            return JsonResponse(
                {'error': 'Custom time must be within 24 hours of the event date.'},
                status=400,
            )

    if action == 'start':
        event.actual_start = custom_time or timezone.now()
        event.save(update_fields=['actual_start'])
    elif action == 'end':
        event.actual_end = custom_time or timezone.now()
        event.save(update_fields=['actual_end'])
    elif action == 'clear_start':
        event.actual_start = None
        event.save(update_fields=['actual_start'])
    elif action == 'clear_end':
        event.actual_end = None
        event.save(update_fields=['actual_end'])
    else:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    return JsonResponse({
        'id': event.pk,
        'actual_start': event.actual_start.isoformat() if event.actual_start else None,
        'actual_end':   event.actual_end.isoformat() if event.actual_end else None,
    })
