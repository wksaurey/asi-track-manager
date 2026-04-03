"""
Shared helper functions for the ASI Track Manager calendar application.

Extracted from views.py and utils.py to eliminate duplication.
"""

import json
from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.utils.timezone import localtime


def parse_api_datetime(val, reference_event=None):
    """Parse an ISO string or HH:MM into an aware datetime.

    Tries full ISO 8601 first (with 'Z' → '+00:00' normalization).
    Falls back to HH:MM format when a *reference_event* is provided,
    combining the time with the event's start date.

    Returns ``None`` on failure or when *val* is falsy.
    """
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except (ValueError, TypeError):
        pass
    if reference_event:
        try:
            parts = val.strip().split(':')
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1])
                if reference_event.start_time:
                    event_date = reference_event.start_time.date()
                else:
                    # Impromptu events: use first segment's date or today
                    first_seg = reference_event.segments.order_by('start').first()
                    event_date = first_seg.start.date() if first_seg else timezone.now().date()
                naive = datetime.combine(
                    event_date,
                    datetime.min.time().replace(hour=h, minute=m),
                )
                return timezone.make_aware(naive)
        except (ValueError, TypeError):
            pass
    return None


def validate_radio_channel(request_body):
    """Parse and validate a radio channel from a JSON request body.

    Returns ``(channel_int_or_None, error_response_or_None)``.
    On success the second element is ``None``; on failure the first
    element is ``None`` and the second is a ``JsonResponse`` ready
    to return to the client.
    """
    try:
        data = json.loads(request_body)
    except (json.JSONDecodeError, ValueError):
        return None, JsonResponse({'error': 'Invalid JSON'}, status=400)
    ch = data.get('channel')
    if ch is not None:
        try:
            ch = int(ch)
        except (ValueError, TypeError):
            return None, JsonResponse(
                {'error': 'Channel must be an integer (1\u201316) or null.'},
                status=400,
            )
        if ch < 1 or ch > 16:
            return None, JsonResponse(
                {'error': 'Channel must be between 11 and 16.'},
                status=400,
            )
    return ch, None


def serialize_segments(event):
    """Serialize an event's segments for JSON API responses."""
    return [
        {
            'id': s.pk,
            'start': localtime(s.start).isoformat(),
            'end': localtime(s.end).isoformat() if s.end else None,
        }
        for s in event.segments.all()
    ]


def stamp_response(event):
    """Standard JSON response for stamp/segment API operations."""
    return JsonResponse({
        'id': event.pk,
        'actual_start': localtime(event.actual_start).isoformat() if event.actual_start else None,
        'actual_end': localtime(event.actual_end).isoformat() if event.actual_end else None,
        'is_stopped': event.is_stopped,
        'segments': serialize_segments(event),
    })
