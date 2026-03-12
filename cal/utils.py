"""
Calendar HTML rendering utilities.

Extends Python's ``calendar.HTMLCalendar`` to produce month, week, and day
views populated with Event data.  Each view supports optional asset filtering
and highlights today's date and weekends with CSS classes.
"""

from datetime import datetime, timedelta, date as date_type
from calendar import HTMLCalendar

from django.urls import reverse

from cal.models import Event


class Calendar(HTMLCalendar):
    """
    Custom HTML calendar that renders Event objects into month, week, or day views.

    Args:
        year:     The calendar year to display.
        month:    The calendar month to display.
        asset_id: Optional asset PK — when set, only events linked to this
                  asset are shown.
    """

    def __init__(self, year=None, month=None, asset_id=None):
        self.year     = year
        self.month    = month
        self.asset_id = asset_id
        self.today    = date_type.today()
        super(Calendar, self).__init__()

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _base_queryset(self):
        """Return the Event queryset, optionally filtered by asset_id."""
        qs = Event.objects.prefetch_related('assets')
        if self.asset_id:
            qs = qs.filter(assets__id=self.asset_id)
        return qs

    def _event_classes(self, event):
        """Build a CSS class string for an event (type colour + pending state)."""
        classes = f'event {event.asset_css_class}'
        if not event.is_approved:
            classes += ' event-pending'
        return classes

    @staticmethod
    def _fmt_time(dt):
        """Format a datetime as '8:30 AM' (no leading zero on the hour)."""
        return dt.strftime('%I:%M %p').lstrip('0') or '12:00 AM'

    # ── Month view ─────────────────────────────────────────────────────────

    def formatday(self, day, events):
        """
        Render a single day cell for the month table.

        ``day=0`` represents a filler cell outside the current month.
        Real days receive 'today' and/or 'weekend' CSS classes as needed.
        """
        events_per_day = events.filter(start_time__day=day).order_by('start_time')
        d = ''
        for event in events_per_day:
            d += f'<li class="{self._event_classes(event)}">{event.get_html_url}</li>'

        if day != 0:
            is_today = (
                day == self.today.day
                and self.month == self.today.month
                and self.year  == self.today.year
            )
            is_weekend = date_type(self.year, self.month, day).weekday() >= 5

            td_classes = []
            if is_today:   td_classes.append('today')
            if is_weekend: td_classes.append('weekend')
            td_cls    = (' class="' + ' '.join(td_classes) + '"') if td_classes else ''
            date_span = (
                f'<span class="date today-circle">{day}</span>'
                if is_today else
                f'<span class="date">{day}</span>'
            )
            return f'<td{td_cls}>{date_span}<ul>{d}</ul></td>'
        return '<td class="noday"></td>'

    def formatweek(self, theweek, events):
        """Render one week row (7 day cells) for the month table."""
        week = ''
        for d, _ in theweek:
            week += self.formatday(d, events)
        return f'<tr>{week}</tr>'

    def formatmonth(self, withyear=True):
        """
        Render the full month view as an HTML table.

        Queries events once for the entire month, then passes the queryset
        into each day cell to avoid N+1 queries.
        """
        events = self._base_queryset().filter(
            start_time__year=self.year,
            start_time__month=self.month,
        )
        cal  = '<table class="calendar month-table">\n'
        cal += f'{self.formatmonthname(self.year, self.month, withyear=withyear)}\n'
        cal += f'{self.formatweekheader()}\n'
        for week in self.monthdays2calendar(self.year, self.month):
            cal += f'{self.formatweek(week, events)}\n'
        cal += '</table>'
        return cal

    # ── Week view ──────────────────────────────────────────────────────────

    def formatweekview(self, start_date):
        """
        Render a 7-day week view as an HTML table.

        The week always starts on Monday.  Generates a header row with day
        abbreviations/dates and a body row with event lists per day.
        Produces a label like "March 9 - 15, 2026" (or cross-month variant).
        """
        # Snap to Monday of the week containing start_date
        start  = start_date - timedelta(days=start_date.weekday())
        end    = start + timedelta(days=6)
        events = self._base_queryset().filter(
            start_time__date__gte=start,
            start_time__date__lte=end,
        )

        # Week range label — single-month vs. cross-month format
        if start.month == end.month:
            label = f'{start.strftime("%B %d")} &ndash; {end.strftime("%d, %Y")}'
        else:
            label = f'{start.strftime("%b %d")} &ndash; {end.strftime("%b %d, %Y")}'

        day_abbr = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        # Header row: day abbreviation + date number
        header = ''
        for i in range(7):
            day      = start + timedelta(days=i)
            is_today = (day == self.today)
            th_class = 'wk-th'
            if is_today: th_class += ' wk-today-head'
            elif i >= 5: th_class += ' wk-weekend-head'
            num_class = 'wk-daynum wk-today-num' if is_today else 'wk-daynum'
            header += (
                f'<th class="{th_class}">'
                f'<div class="wk-dayname">{day_abbr[i]}</div>'
                f'<div class="{num_class}">{day.day}</div>'
                f'</th>'
            )

        # Body row: one cell per day containing that day's event list
        body = ''
        for i in range(7):
            day        = start + timedelta(days=i)
            td_classes = []
            if day == self.today: td_classes.append('today')
            if i >= 5:            td_classes.append('weekend')
            td_cls = ' '.join(td_classes)

            d_events = events.filter(
                start_time__day=day.day,
                start_time__month=day.month,
                start_time__year=day.year,
            ).order_by('start_time')

            items = ''
            for ev in d_events:
                items += (
                    f'<li class="{self._event_classes(ev)}">'
                    f'{ev.get_html_url}'
                    f'</li>'
                )

            body += f'<td class="{td_cls}"><ul class="wk-events">{items}</ul></td>'

        return (
            f'<div class="calendar week-view">'
            f'<div class="week-label">{label}</div>'
            f'<table class="week-table">'
            f'<thead><tr>{header}</tr></thead>'
            f'<tbody><tr>{body}</tr></tbody>'
            f'</table>'
            f'</div>'
        )

    # ── Day view ───────────────────────────────────────────────────────────

    def formatdayview(self, day_date):
        """
        Render a single-day detail view.

        Shows each event with its start/end times, computed duration (e.g.
        '2h 30m'), and the standard event link HTML.  Displays a friendly
        "No events" message when the day is empty.
        """
        events = self._base_queryset().filter(
            start_time__year=day_date.year,
            start_time__month=day_date.month,
            start_time__day=day_date.day,
        ).order_by('start_time')

        is_today  = (day_date == self.today)
        today_pfx = 'Today &mdash; ' if is_today else ''
        title     = f'{today_pfx}{day_date.strftime("%A, %B %d, %Y")}'

        if not events.exists():
            body = (
                '<div class="day-no-events">'
                '<i class="fas fa-calendar-times"></i> No events scheduled for this day.'
                '</div>'
            )
        else:
            rows = ''
            for ev in events:
                # Compute human-readable duration from the time delta
                total_m = int((ev.end_time - ev.start_time).total_seconds()) // 60
                hrs, mn = divmod(total_m, 60)
                dur_str = (f'{hrs}h {mn}m' if mn else f'{hrs}h') if hrs else f'{mn}m'
                rows += (
                    f'<div class="day-ev-row {self._event_classes(ev)}">'
                    f'<div class="day-ev-time">'
                    f'<span class="dev-start">{self._fmt_time(ev.start_time)}</span>'
                    f'<span class="dev-sep">&rarr;</span>'
                    f'<span class="dev-end">{self._fmt_time(ev.end_time)}</span>'
                    f'<span class="dev-dur">{dur_str}</span>'
                    f'</div>'
                    f'<div class="day-ev-content">{ev.get_html_url}</div>'
                    f'</div>'
                )
            body = f'<div class="day-event-list">{rows}</div>'

        return (
            f'<div class="calendar day-view">'
            f'<div class="day-view-title">{title}</div>'
            f'{body}'
            f'</div>'
        )
