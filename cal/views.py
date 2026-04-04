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
from django.shortcuts import render, get_object_or_404
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
from .decorators import staff_required, staff_required_api
from .helpers import parse_api_datetime, validate_radio_channel, serialize_segments, stamp_response


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


@staff_required
@require_POST
def event_delete(request, event_id):
    """Admin only — delete an event.  Requires POST to prevent accidental deletion."""
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.delete()
    default = reverse('cal:calendar')
    return HttpResponseRedirect(_safe_next_url(request, default))


@staff_required
@require_POST
def event_approve(request, event_id):
    """Admin only — mark a pending event as approved.  Redirects to the pending list."""
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


@staff_required
@require_POST
def event_unapprove(request, event_id):
    """Admin only — revoke approval, returning an event to pending status."""
    event_obj = get_object_or_404(Event, pk=event_id)
    event_obj.is_approved = False
    event_obj.save(update_fields=['is_approved'])
    default = reverse('cal:event_edit', args=[event_id])
    return HttpResponseRedirect(_safe_next_url(request, default))


@staff_required
def pending_events(request):
    """Admin only — list all events awaiting approval, with conflict status."""
    events = Event.objects.filter(is_approved=False).order_by('start_time').prefetch_related('assets')

    for ev in events:
        conflict_events = []
        seen_pks = set()
        if ev.start_time and ev.end_time:
            for asset in ev.assets.all():
                for c in get_asset_conflicts(
                    asset, ev.start_time, ev.end_time,
                    exclude_event_id=ev.pk, approved_only=True,
                ):
                    if c.pk not in seen_pks:
                        seen_pks.add(c.pk)
                        conflict_events.append(c)
        ev.has_conflict = len(conflict_events) > 0
        ev.conflict_events = conflict_events

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


@staff_required
def asset_create(request):
    """Admin only — show a form to create a new asset."""
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


@staff_required
def asset_edit(request, asset_id):
    """Admin only — edit an existing asset's details."""
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


@staff_required
@require_POST
def asset_delete(request, asset_id):
    """Admin only — delete an asset.  Requires POST for safety."""
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

@staff_required
def dashboard(request):
    """
    Control Center Dashboard — admin only.

    Renders ``cal/dashboard.html`` with all track-type assets passed in context.
    """
    tracks = Asset.objects.filter(asset_type=Asset.AssetType.TRACK)
    return render(request, 'cal/dashboard.html', {'tracks': tracks})


@staff_required_api
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
        Q(start_time__date=target_date) |
        Q(start_time__isnull=True, segments__start__date=target_date)
    ).prefetch_related('segments').distinct().order_by('start_time')

    all_tracks = Asset.objects.filter(
        asset_type=Asset.AssetType.TRACK
    ).prefetch_related(
        Prefetch('events', queryset=track_events_qs, to_attr='day_events'),
        'subtracks',
    ).order_by('name')

    def _serialize_event(ev):
        return {
            'id': ev.pk,
            'title': ev.title,
            'description': ev.description,
            'start_time': localtime(ev.start_time).isoformat() if ev.start_time else None,
            'end_time': localtime(ev.end_time).isoformat() if ev.end_time else None,
            'is_approved': ev.is_approved,
            'is_impromptu': ev.is_impromptu,
            'actual_start': localtime(ev.actual_start).isoformat() if ev.actual_start else None,
            'actual_end': localtime(ev.actual_end).isoformat() if ev.actual_end else None,
            'radio_channel': ev.radio_channel,
            'effective_radio_channel': ev.effective_radio_channel,
            'is_stopped': ev.is_stopped,
            'is_currently_active': ev.is_currently_active,
            'total_actual_seconds': ev.total_actual_seconds,
            'segments': serialize_segments(ev),
        }

    def _serialize_events(track):
        return [_serialize_event(ev) for ev in track.day_events]

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
            # Events booked on ≥2 subtracks → promote to parent level
            sub_event_counts = {}  # event pk → count of subtracks
            for sub in subs:
                for ev in sub.day_events:
                    sub_event_counts[ev.pk] = sub_event_counts.get(ev.pk, 0) + 1
            multi_sub_pks = {pk for pk, cnt in sub_event_counts.items() if cnt >= 2}

            # Add promoted events to parent's events list (avoid duplicates)
            existing_pks = {ev['id'] for ev in track_data['events']}
            for sub in subs:
                for ev in sub.day_events:
                    if ev.pk in multi_sub_pks and ev.pk not in existing_pks:
                        track_data['events'].append(_serialize_event(ev))
                        existing_pks.add(ev.pk)
            track_data['events'].sort(key=lambda e: e['start_time'])

            track_data['subtracks'] = {
                sub.name: {
                    'id': sub.pk,
                    'radio_channel': sub.radio_channel,
                    'is_active': sub.is_active,
                    'events': [e for e in _serialize_events(sub) if e['id'] not in multi_sub_pks],
                }
                for sub in sorted(subs, key=lambda s: s.name)
            }
        data[track.name] = track_data

    return JsonResponse({'date': target_date.isoformat(), 'tracks': data})


@staff_required_api
@require_POST
def api_event_approve(request, event_id):
    """
    JSON API — admin only.

    Approve a pending event after checking for scheduling conflicts with
    other approved events.  Returns 409 with conflict details if any
    overlapping approved events share conflicting assets.

    URL: /cal/api/event/<event_id>/approve/
    """
    event_obj = get_object_or_404(Event, pk=event_id)

    # Check for conflicts with existing approved events
    conflicts = []
    seen_pks = set()
    for asset in event_obj.assets.all():
        overlapping = get_asset_conflicts(
            asset, event_obj.start_time, event_obj.end_time,
            exclude_event_id=event_obj.pk, approved_only=True,
        )
        for c in overlapping:
            if c.pk not in seen_pks:
                seen_pks.add(c.pk)
                conflict_ids = asset.conflicting_asset_ids()
                conflict_asset = c.assets.filter(pk__in=conflict_ids).first()
                conflicts.append({
                    'id': c.pk,
                    'title': c.title,
                    'asset': str(conflict_asset or asset),
                    'start_time': c.start_time.isoformat(),
                    'end_time': c.end_time.isoformat(),
                })

    if conflicts:
        labels = [
            f'"{c["title"]}" ({c["asset"]})'
            for c in conflicts
        ]
        return JsonResponse({
            'error': f'Conflicts with: {", ".join(labels)}',
            'conflicts': conflicts,
        }, status=409)

    event_obj.is_approved = True
    event_obj.save(update_fields=['is_approved'])
    return JsonResponse({'approved': True, 'id': event_obj.pk})


@staff_required_api
@require_POST
def mass_approve_events(request):
    """Admin only — approve multiple pending events that have no conflicts."""
    try:
        data = json.loads(request.body)
        event_ids = data.get('event_ids', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body'}, status=400)

    if not event_ids:
        return JsonResponse({'error': 'No events specified'}, status=400)

    pending = list(Event.objects.filter(
        pk__in=event_ids, is_approved=False,
    ).prefetch_related('assets'))

    # First pass: identify ALL events with conflicts (approved or within batch)
    conflict_pks = set()
    for ev in pending:
        if not ev.start_time or not ev.end_time:
            continue
        for asset in ev.assets.all():
            # Check against already-approved events
            approved_conflicts = get_asset_conflicts(
                asset, ev.start_time, ev.end_time,
                exclude_event_id=ev.pk, approved_only=True,
            )
            if approved_conflicts.exists():
                conflict_pks.add(ev.pk)
                break
            # Check against other pending events in this batch
            for other in pending:
                if other.pk == ev.pk or not other.start_time or not other.end_time:
                    continue
                other_asset_ids = {a.pk for a in other.assets.all()}
                conflict_ids = asset.conflicting_asset_ids()
                if (conflict_ids & other_asset_ids and
                        ev.start_time < other.end_time and ev.end_time > other.start_time):
                    conflict_pks.add(ev.pk)
                    conflict_pks.add(other.pk)
                    break
            if ev.pk in conflict_pks:
                break

    # Second pass: approve clean events, skip conflicting ones
    approved_count = 0
    skipped = []
    for ev in pending:
        if ev.pk in conflict_pks:
            skipped.append({
                'id': ev.pk, 'title': ev.title, 'reason': 'Booking conflict',
            })
        else:
            ev.is_approved = True
            ev.save(update_fields=['is_approved'])
            approved_count += 1

    return JsonResponse({
        'approved': approved_count,
        'skipped': len(skipped),
        'skipped_details': skipped,
    })


# ── Analytics ─────────────────────────────────────────────────────────────────

@staff_required_api
@require_POST
def track_active_toggle(request, asset_id):
    """Admin only — toggle a track's active/unsafe state."""
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


@staff_required_api
@require_POST
def set_radio_channel(request, asset_id):
    """Admin only — set or clear a track's radio channel (11–16)."""
    track = get_object_or_404(Asset, pk=asset_id, asset_type=Asset.AssetType.TRACK)
    channel, err = validate_radio_channel(request.body)
    if err:
        return err
    track.radio_channel = channel
    track.save(update_fields=['radio_channel'])
    return JsonResponse({'id': track.pk, 'radio_channel': track.radio_channel})


@staff_required_api
@require_POST
def set_event_radio_channel(request, event_id):
    """Admin only — set or clear a per-event radio channel override (11–16)."""
    event_obj = get_object_or_404(Event, pk=event_id)
    channel, err = validate_radio_channel(request.body)
    if err:
        return err
    event_obj.radio_channel = channel
    event_obj.save(update_fields=['radio_channel'])
    return JsonResponse({
        'id': event_obj.pk,
        'radio_channel': event_obj.radio_channel,
        'effective_radio_channel': event_obj.effective_radio_channel,
    })


@staff_required
def analytics(request):
    return render(request, 'cal/analytics.html')


@staff_required_api
def analytics_api(request):
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


@staff_required_api
@require_POST
def api_create_event(request):
    """
    JSON API — staff only.
    Create a new event. Two modes:
    - Scheduled: requires start_time, end_time. Runs conflict detection.
    - Impromptu: is_impromptu=true. No times required, auto-approved, opens a segment immediately.
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    title = (body.get('title') or '').strip()
    if not title:
        return JsonResponse({'error': 'Title is required.'}, status=400)

    description = (body.get('description') or '').strip()
    asset_ids = body.get('asset_ids', [])
    is_impromptu = bool(body.get('is_impromptu', False))

    # Validate assets
    if not asset_ids:
        return JsonResponse({'error': 'At least one asset is required.'}, status=400)
    assets = list(Asset.objects.filter(pk__in=asset_ids))
    if len(assets) != len(asset_ids):
        return JsonResponse({'error': 'One or more asset IDs are invalid.'}, status=400)

    # Single track group rule
    track_assets = [a for a in assets if a.asset_type == Asset.AssetType.TRACK]
    if len(track_assets) > 1:
        parents = set()
        for t in track_assets:
            parents.add(t.parent_id if t.parent_id else t.pk)
        if len(parents) > 1:
            return JsonResponse({'error': 'Only one track group per reservation.'}, status=400)

    # Parse times for scheduled events
    start_time = None
    end_time = None
    if not is_impromptu:
        start_time = parse_api_datetime(body.get('start_time'))
        end_time = parse_api_datetime(body.get('end_time'))
        if not start_time or not end_time:
            return JsonResponse({'error': 'start_time and end_time are required for scheduled events.'}, status=400)
        if start_time >= end_time:
            return JsonResponse({'error': 'End time must be after start time.'}, status=400)

        # Conflict detection using shared helper
        for asset in assets:
            conflicts = get_asset_conflicts(asset, start_time, end_time, approved_only=True)
            if conflicts.exists():
                conflict = conflicts.first()
                return JsonResponse({
                    'error': f'Scheduling conflict: "{conflict.title}" already has a conflicting booking.'
                }, status=400)

    # For impromptu events, check for active events on the same track(s).
    # First, auto-close any stale open segments from previous days.
    now = timezone.now()
    today = localtime(now).date()
    confirmed = bool(body.get('confirmed', False))

    if is_impromptu:
        conflict_ids = set()
        for asset in assets:
            conflict_ids.update(asset.conflicting_asset_ids())

        # Auto-stop stale segments from previous days
        stale_segments = ActualTimeSegment.objects.filter(
            event__assets__in=conflict_ids,
            end__isnull=True,
        ).exclude(start__date=today)
        for seg in stale_segments:
            # Close at end of the day the segment started
            seg.end = seg.start.replace(hour=23, minute=59, second=59)
            seg.save(update_fields=['end'])

        # Now check for today's active events only
        if not confirmed:
            active_events = list(
                Event.objects.filter(
                    assets__in=conflict_ids,
                    is_approved=True,
                    segments__end__isnull=True,
                    segments__start__date=today,
                ).distinct()[:5]
            )
            if active_events:
                return JsonResponse({
                    'requires_confirmation': True,
                    'active_events': [
                        {'id': ae.pk, 'title': ae.title}
                        for ae in active_events
                    ],
                    'message': (
                        f'"{active_events[0].title}" is currently active on this track '
                        f'and will be paused if you continue.'
                        if len(active_events) == 1 else
                        f'{len(active_events)} events are currently active on this track '
                        f'and will be paused if you continue.'
                    ),
                }, status=409)

        # If confirmed, pause today's active events first
        if confirmed:
            active_events = Event.objects.filter(
                assets__in=conflict_ids,
                is_approved=True,
                segments__end__isnull=True,
                segments__start__date=today,
            ).distinct()
            for ae in active_events:
                open_seg = ae.segments.filter(end__isnull=True).first()
                if open_seg:
                    open_seg.end = now
                    open_seg.save(update_fields=['end'])

    ev = Event(
        title=title,
        description=description,
        is_impromptu=is_impromptu,
        start_time=start_time,      # None for impromptu
        end_time=end_time,          # None for impromptu
        created_by=request.user,
        is_approved=True,
    )
    ev.save()
    ev.assets.set(assets)

    # For impromptu events, open a segment immediately (v1.1 segment model)
    if is_impromptu:
        ActualTimeSegment.objects.create(event=ev, start=now)

    # Inherit radio channel from track
    if ev.radio_channel is None and track_assets:
        track = track_assets[0]
        channel = track.radio_channel
        if channel is None and track.parent_id:
            channel = track.parent.radio_channel
        if channel is not None:
            ev.radio_channel = channel
            ev.save(update_fields=['radio_channel'])

    return JsonResponse({
        'id': ev.pk,
        'title': ev.title,
        'is_impromptu': ev.is_impromptu,
        'is_approved': ev.is_approved,
    }, status=201)


@staff_required_api
@require_POST
def dashboard_stamp_actual(request, event_id):
    """
    JSON API — admin only.

    Stamps actual start/end times via segments.  Supports both legacy
    actions (start/end/clear_start/clear_end) and new play/pause/stop/clear.

    URL: /cal/api/event/<event_id>/stamp/
    """

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
    custom_time = parse_api_datetime(time_str, reference_event=event) if time_str else None

    # Reject future times
    if custom_time and custom_time > timezone.now():
        return JsonResponse({'error': 'Time cannot be in the future.'}, status=400)

    # ── Legacy actions (backward compat) ────────────────────────
    if action == 'start':
        # Validation
        if custom_time:
            event_date = event.start_time.date() if event.start_time else localtime(timezone.now()).date()
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
    return stamp_response(event)


@staff_required_api
@require_POST
def segment_edit(request, segment_id):
    """
    JSON API — admin only.
    Edit an individual ActualTimeSegment's start and/or end times.
    URL: /cal/api/segment/<segment_id>/edit/
    """

    try:
        seg = ActualTimeSegment.objects.select_related('event').get(pk=segment_id)
    except ActualTimeSegment.DoesNotExist:
        return JsonResponse({'error': 'Segment not found'}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    event = seg.event
    new_start = parse_api_datetime(body.get('start'), reference_event=event)
    new_end = parse_api_datetime(body.get('end'), reference_event=event)

    if new_start:
        seg.start = new_start
    if new_end:
        seg.end = new_end
    if body.get('end') is None and 'end' in body:
        seg.end = None

    now = timezone.now()
    if seg.start and seg.start > now:
        return JsonResponse({'error': 'Time cannot be in the future.'}, status=400)
    if seg.end and seg.end > now:
        return JsonResponse({'error': 'Time cannot be in the future.'}, status=400)

    if seg.end and seg.start and seg.end < seg.start:
        return JsonResponse({'error': 'End time cannot be before start time.'}, status=400)

    seg.save()

    event.refresh_from_db()
    return stamp_response(event)


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
