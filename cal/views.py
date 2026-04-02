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

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import ExtractHour, TruncDate
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import localtime
from django.utils.safestring import mark_safe
from django.views import generic
from django.views.decorators.http import require_POST

from .models import ActualTimeSegment, Asset, Event, Feedback
from .utils import Calendar, get_asset_conflicts
from .forms import EventForm, AssetForm, FeedbackForm, get_asset_tree


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
        view     = self.request.GET.get('view', 'day')
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
            context['has_pending'] = getattr(cal, 'gantt_has_pending', False)
            context['has_active'] = getattr(cal, 'gantt_has_active', False)
            context['has_completed'] = getattr(cal, 'gantt_has_completed', False)
            context['has_noshow'] = getattr(cal, 'gantt_has_noshow', False)
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

        # Day-view legend needs parent tracks with their colors
        if view == 'day':
            context['day_tracks'] = Asset.objects.filter(
                asset_type=Asset.AssetType.TRACK,
                parent__isnull=True,
            ).order_by('name')
            context['is_today'] = (d == localtime(timezone.now()).date())

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
    return localtime(timezone.now()).date()


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

def _safe_next_url(request, default_url):
    """
    Return the ``next`` URL from POST or GET params if it passes
    open-redirect validation, otherwise return *default_url*.
    """
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(url=next_url, allowed_hosts=set()):
        return next_url
    return default_url


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
        can_edit = request.user.is_staff or instance.created_by == request.user
    else:
        instance = Event()
        can_edit = True

    form = EventForm(request.POST or None, instance=instance)
    # Hide radio_channel from non-admin users
    if not request.user.is_staff:
        del form.fields['radio_channel']
    if request.POST:
        if not can_edit:
            return HttpResponseRedirect(reverse('cal:calendar'))
        if form.is_valid():
            ev = form.save(commit=False)
            if not event_id:
                ev.created_by = request.user
                # All events default to unapproved — must go through approval workflow
            ev.save()
            form.save_m2m()   # persist ManyToMany (assets) after the instance is saved
            default = reverse('cal:calendar')
            return HttpResponseRedirect(_safe_next_url(request, default))

    # Carry ?next= through to the template so the hidden field can persist it
    next_url = request.GET.get('next', '')
    segments = list(instance.segments.all()) if event_id else []
    return render(request, 'cal/event.html', {
        'form':            form,
        'event':           instance if event_id else None,
        'is_admin':        request.user.is_staff,
        'can_edit':        can_edit,
        'asset_data_json': get_asset_tree(),
        'next_url':        next_url,
        'segments':        segments,
    })


@login_required
@require_POST
def event_delete(request, event_id):
    """Admin only — delete an event.  Requires POST to prevent accidental deletion."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.delete()
    default = reverse('cal:calendar')
    return HttpResponseRedirect(_safe_next_url(request, default))


@login_required
@require_POST
def event_approve(request, event_id):
    """Admin only — mark a pending event as approved.  Redirects to the pending list."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    event_obj = get_object_or_404(Event, pk=event_id)

    # Check for conflicts with other approved events before approving
    for asset in event_obj.assets.all():
        conflicts = get_asset_conflicts(
            asset,
            event_obj.start_time,
            event_obj.end_time,
            exclude_event_id=event_obj.pk,
            approved_only=True,
        )
        if conflicts.exists():
            conflict = conflicts.first()
            messages.error(
                request,
                f'Cannot approve: conflicts with approved event "{conflict.title}".',
            )
            # Redirect back to the event edit page so user sees the error
            next_url = request.POST.get('next') or ''
            event_url = reverse('cal:event_edit', args=[event_id])
            if next_url:
                event_url += f'?next={next_url}'
            return HttpResponseRedirect(event_url)

    event_obj.is_approved = True
    event_obj.save(update_fields=['is_approved'])
    default = reverse('cal:pending_events')
    return HttpResponseRedirect(_safe_next_url(request, default))


@login_required
@require_POST
def event_unapprove(request, event_id):
    """Admin only — revoke approval, returning an event to pending status."""
    if not request.user.is_staff:
        return HttpResponseRedirect(reverse('cal:calendar'))
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.is_approved = False
    event_obj.save(update_fields=['is_approved'])
    default = reverse('cal:event_edit', args=[event_id])
    return HttpResponseRedirect(_safe_next_url(request, default))


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
    today   = localtime(timezone.now()).date()
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

    today = localtime(timezone.now()).date()
    date_param = request.GET.get('date')
    if date_param:
        try:
            target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            target_date = today
    else:
        target_date = today

    track_events_qs = Event.objects.filter(
        start_time__date=target_date
    ).prefetch_related('segments').order_by('start_time')

    all_tracks = Asset.objects.filter(
        asset_type=Asset.AssetType.TRACK
    ).prefetch_related(
        Prefetch('events', queryset=track_events_qs, to_attr='day_events'),
        'subtracks',
    ).order_by('name')

    def _serialize_events(track):
        return [
            {
                'id': ev.pk,
                'title': ev.title,
                'description': ev.description,
                'start_time': localtime(ev.start_time).isoformat(),
                'end_time': localtime(ev.end_time).isoformat(),
                'is_approved': ev.is_approved,
                'is_impromptu': ev.is_impromptu,
                'actual_start': localtime(ev.actual_start).isoformat() if ev.actual_start else None,
                'actual_end': localtime(ev.actual_end).isoformat() if ev.actual_end else None,
                'radio_channel': ev.radio_channel,
                'effective_radio_channel': ev.effective_radio_channel,
                'is_stopped': ev.is_stopped,
                'is_currently_active': ev.is_currently_active,
                'total_actual_seconds': ev.total_actual_seconds,
                'segments': [
                    {
                        'id': s.pk,
                        'start': localtime(s.start).isoformat(),
                        'end': localtime(s.end).isoformat() if s.end else None,
                    }
                    for s in ev.segments.all()
                ],
            }
            for ev in track.day_events
        ]

    # Group: parent tracks with subtracks nested; standalone tracks at top level
    data = {}
    parent_tracks = [t for t in all_tracks if t.parent_id is None]
    sub_by_parent = {}
    for t in all_tracks:
        if t.parent_id is not None:
            sub_by_parent.setdefault(t.parent_id, []).append(t)

    for track in parent_tracks:
        subs = sub_by_parent.get(track.pk, [])
        track_data = {
            'id': track.pk,
            'color': track.color,
            'radio_channel': track.radio_channel,
            'is_active': track.is_active,
            'events': _serialize_events(track),
        }
        if subs:
            track_data['subtracks'] = {
                sub.name: {
                    'id': sub.pk,
                    'radio_channel': sub.radio_channel,
                    'is_active': sub.is_active,
                    'events': _serialize_events(sub),
                }
                for sub in sorted(subs, key=lambda s: s.name)
            }
        data[track.name] = track_data

    return JsonResponse({'date': target_date.isoformat(), 'tracks': data})


# ── Analytics ─────────────────────────────────────────────────────────────────

@login_required
@require_POST
def track_active_toggle(request, asset_id):
    """Admin only — toggle a track's active/unsafe state."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    track = get_object_or_404(Asset, pk=asset_id, asset_type=Asset.AssetType.TRACK)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    is_active = body.get('is_active')
    if isinstance(is_active, bool):
        track.is_active = is_active
    else:
        # No explicit value — toggle
        track.is_active = not track.is_active
    track.save(update_fields=['is_active'])
    return JsonResponse({'id': track.pk, 'is_active': track.is_active})


@login_required
@require_POST
def set_radio_channel(request, asset_id):
    """Admin only — set or clear a track's radio channel (11–16)."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    track = get_object_or_404(Asset, pk=asset_id, asset_type=Asset.AssetType.TRACK)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    channel = body.get('channel')
    if channel is not None:
        try:
            channel = int(channel)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Channel must be an integer (11–16) or null.'}, status=400)
        if channel < 11 or channel > 16:
            return JsonResponse({'error': 'Channel must be between 11 and 16.'}, status=400)
    track.radio_channel = channel
    track.save(update_fields=['radio_channel'])
    return JsonResponse({'id': track.pk, 'radio_channel': track.radio_channel})


@login_required
@require_POST
def set_event_radio_channel(request, event_id):
    """Admin only — set or clear a per-event radio channel override (11–16)."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    event_obj = get_object_or_404(Event, pk=event_id)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    channel = body.get('channel')
    if channel is not None:
        try:
            channel = int(channel)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Channel must be an integer (11–16) or null.'}, status=400)
        if channel < 11 or channel > 16:
            return JsonResponse({'error': 'Channel must be between 11 and 16.'}, status=400)
    event_obj.radio_channel = channel
    event_obj.save(update_fields=['radio_channel'])
    return JsonResponse({
        'id': event_obj.pk,
        'radio_channel': event_obj.radio_channel,
        'effective_radio_channel': event_obj.effective_radio_channel,
    })


@login_required
def analytics(request):
    if not request.user.is_staff:
        return redirect('cal:calendar')
    return render(request, 'cal/analytics.html')


@login_required
def analytics_api(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    today = localtime(timezone.now()).date()
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
    all_events = list(events.prefetch_related('assets', 'segments'))

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

    # 7. Wasted time by unapproved events (use all_events_in_range, already queried)
    unapproved_secs = sum(
        (e.end_time - e.start_time).total_seconds()
        for e in all_events_in_range.filter(is_approved=False).only('start_time', 'end_time')
    )

    # 8. Impromptu event count (use all_events_in_range, already queried)
    impromptu_count = all_events_in_range.filter(is_impromptu=True).count()

    return JsonResponse({
        'range': {'start': str(start_date), 'end': str(end_date)},
        'track_utilization': track_utilization,
        'schedule_accuracy': schedule_accuracy,
        'usage_trends': usage_trends,
        'peak_hours': peak_hours,
        'user_activity': user_activity,
        'asset_usage': asset_usage,
        'unapproved_waste_hours': round(unapproved_secs / 3600, 1),
        'impromptu_count': impromptu_count,
    })


@login_required
@require_POST
def event_impromptu(request):
    """Admin only — create an impromptu event from the dashboard."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    track_id = body.get('track_id')
    title = body.get('title', '').strip()
    start_time = body.get('start_time')
    end_time = body.get('end_time')
    confirmed = body.get('confirmed', False)

    if not all([track_id, title, start_time, end_time]):
        return JsonResponse({'error': 'Missing required fields: track_id, title, start_time, end_time'}, status=400)

    track = get_object_or_404(Asset, pk=track_id, asset_type=Asset.AssetType.TRACK)

    try:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Invalid datetime format.'}, status=400)

    if start_dt >= end_dt:
        return JsonResponse({'error': 'End time must be after start time.'}, status=400)

    conflicts = get_asset_conflicts(track, start_dt, end_dt, approved_only=True)
    if conflicts.exists() and not confirmed:
        return JsonResponse({
            'requires_confirmation': True,
            'conflicts': [
                {
                    'id': c.pk,
                    'title': c.title,
                    'start_time': localtime(c.start_time).isoformat(),
                    'end_time': localtime(c.end_time).isoformat(),
                }
                for c in conflicts[:5]
            ]
        })

    ev = Event.objects.create(
        title=title,
        start_time=start_dt,
        end_time=end_dt,
        is_impromptu=True,
        is_approved=True,
        created_by=request.user,
    )
    ev.assets.add(track)

    return JsonResponse({
        'id': ev.pk,
        'is_impromptu': True,
        'is_approved': True,
    }, status=201)


@login_required
@require_POST
def dashboard_stamp_actual(request, event_id):
    """
    JSON API — admin only.

    Stamps actual start/end times via segments.  Supports both legacy
    actions (start/end/clear_start/clear_end) and new play/pause/stop/clear.

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
    time_str = body.get('time')

    # Parse the custom time if provided
    custom_time = None
    if time_str:
        try:
            custom_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            if timezone.is_naive(custom_time):
                custom_time = timezone.make_aware(custom_time)
        except (ValueError, TypeError):
            try:
                parts = time_str.strip().split(':')
                if len(parts) == 2:
                    h, m = int(parts[0]), int(parts[1])
                    event_date = event.start_time.date()
                    naive = datetime.combine(event_date, datetime.min.time().replace(hour=h, minute=m))
                    custom_time = timezone.make_aware(naive)
            except (ValueError, TypeError):
                pass

    # ── Legacy actions (backward compat) ────────────────────────
    if action == 'start':
        # Validation
        if custom_time:
            event_date = event.start_time.date()
            event_midnight = timezone.make_aware(datetime.combine(event_date, datetime.min.time()))
            if custom_time < event_midnight - timedelta(hours=24) or custom_time > event_midnight + timedelta(hours=48):
                return JsonResponse(
                    {'error': 'Custom time must be within 24 hours of the event date.'},
                    status=400,
                )
        # Clear existing segments and create a new open one
        event.segments.all().delete()
        ActualTimeSegment.objects.create(event=event, start=custom_time or timezone.now())
    elif action == 'end':
        if not event.actual_start:
            return JsonResponse(
                {'error': 'Cannot stamp end time before start time is recorded.'},
                status=400,
            )
        stamp_time = custom_time or timezone.now()
        if custom_time and custom_time < event.actual_start:
            return JsonResponse(
                {'error': 'End time cannot be before start time.'},
                status=400,
            )
        # Close the open segment
        seg = event.current_segment
        if seg:
            seg.end = stamp_time
            seg.save()
        else:
            # No open segment — create a closed one from actual_start to now
            ActualTimeSegment.objects.create(
                event=event, start=event.actual_start, end=stamp_time,
            )
    elif action == 'clear_start':
        event.segments.all().delete()
    elif action == 'clear_end':
        seg = event.segments.filter(end__isnull=False).order_by('-end').first()
        if seg:
            seg.end = None
            seg.save()

    # ── New play/pause/stop/clear actions ───────────────────────
    elif action == 'play':
        if event.is_stopped:
            return JsonResponse({'error': 'Event is stopped.'}, status=400)
        if event.current_segment is not None:
            return JsonResponse({'error': 'Already playing.'}, status=400)
        ActualTimeSegment.objects.create(event=event, start=custom_time or timezone.now())
    elif action == 'pause':
        seg = event.current_segment
        if seg is None:
            return JsonResponse({'error': 'Not playing.'}, status=400)
        seg.end = custom_time or timezone.now()
        seg.save()
    elif action == 'stop':
        seg = event.current_segment
        if seg is None:
            return JsonResponse({'error': 'Not playing.'}, status=400)
        seg.end = custom_time or timezone.now()
        seg.save()
        event.is_stopped = True
        event.save(update_fields=['is_stopped'])
    elif action == 'undo':
        # Undo the most recent stamp action:
        #   stopped  → un-stop + reopen last segment (undo "stop")
        #   paused   → delete last closed segment (undo "pause")
        #   active   → delete the open segment (undo "play")
        if event.is_stopped:
            event.is_stopped = False
            event.save(update_fields=['is_stopped'])
            last_seg = event.segments.order_by('-start').first()
            if last_seg and last_seg.end:
                last_seg.end = None
                last_seg.save()
        elif event.current_segment is not None:
            # Active — delete the open segment
            event.current_segment.delete()
        else:
            # Paused — delete the most recent closed segment
            last_seg = event.segments.order_by('-start').first()
            if last_seg:
                last_seg.delete()
    elif action == 'clear':
        event.segments.all().delete()
        event.is_stopped = False
        event.save(update_fields=['is_stopped'])
    else:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    # Refresh to get up-to-date segment data
    event.refresh_from_db()
    return JsonResponse({
        'id': event.pk,
        'actual_start': localtime(event.actual_start).isoformat() if event.actual_start else None,
        'actual_end': localtime(event.actual_end).isoformat() if event.actual_end else None,
        'is_stopped': event.is_stopped,
        'segments': [
            {
                'id': s.pk,
                'start': localtime(s.start).isoformat(),
                'end': localtime(s.end).isoformat() if s.end else None,
            }
            for s in event.segments.all()
        ],
    })


@login_required
@require_POST
def segment_edit(request, segment_id):
    """
    JSON API — admin only.
    Edit an individual ActualTimeSegment's start and/or end times.
    URL: /cal/api/segment/<segment_id>/edit/
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        seg = ActualTimeSegment.objects.select_related('event').get(pk=segment_id)
    except ActualTimeSegment.DoesNotExist:
        return JsonResponse({'error': 'Segment not found'}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    def parse_time(val, event):
        if not val:
            return None
        try:
            dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except (ValueError, TypeError):
            pass
        try:
            parts = val.strip().split(':')
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1])
                event_date = event.start_time.date()
                naive = datetime.combine(event_date, datetime.min.time().replace(hour=h, minute=m))
                return timezone.make_aware(naive)
        except (ValueError, TypeError):
            pass
        return None

    event = seg.event
    new_start = parse_time(body.get('start'), event)
    new_end = parse_time(body.get('end'), event)

    if new_start:
        seg.start = new_start
    if new_end:
        seg.end = new_end
    if body.get('end') is None and 'end' in body:
        seg.end = None

    if seg.end and seg.start and seg.end < seg.start:
        return JsonResponse({'error': 'End time cannot be before start time.'}, status=400)

    seg.save()

    event.refresh_from_db()
    return JsonResponse({
        'id': event.pk,
        'actual_start': localtime(event.actual_start).isoformat() if event.actual_start else None,
        'actual_end': localtime(event.actual_end).isoformat() if event.actual_end else None,
        'is_stopped': event.is_stopped,
        'segments': [
            {
                'id': s.pk,
                'start': localtime(s.start).isoformat(),
                'end': localtime(s.end).isoformat() if s.end else None,
            }
            for s in event.segments.all()
        ],
    })


# ── Feedback ─────────────────────────────────────────────────────────────────

@login_required
@require_POST
def submit_feedback(request):
    form = FeedbackForm(request.POST)
    if form.is_valid():
        fb = form.save(commit=False)
        fb.user = request.user
        fb.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'errors': form.errors}, status=400)


@login_required
def feedback_list(request):
    if not request.user.is_developer:
        return HttpResponseRedirect(reverse('cal:calendar'))
    items = Feedback.objects.select_related('user').all()
    return render(request, 'cal/feedback_list.html', {'items': items})


@login_required
@require_POST
def feedback_resolve(request, feedback_id):
    if not request.user.is_developer:
        return HttpResponseRedirect(reverse('cal:calendar'))
    fb = get_object_or_404(Feedback, pk=feedback_id)
    fb.is_resolved = not fb.is_resolved
    fb.save(update_fields=['is_resolved'])
    return HttpResponseRedirect(reverse('cal:feedback_list'))
