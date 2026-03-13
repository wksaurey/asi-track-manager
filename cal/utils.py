"""
Calendar HTML rendering utilities.

Extends Python's ``calendar.HTMLCalendar`` to produce month, week, and day
views populated with Event data.  Each view supports optional asset filtering
and highlights today's date and weekends with CSS classes.
"""

from datetime import datetime, timedelta, date as date_type
from calendar import HTMLCalendar

from django.urls import reverse
from django.utils.html import escape

from cal.models import Asset, Event


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

    @staticmethod
    def _assign_rows(events):
        """
        Assign each event to a sub-row index (0-based) such that no two events
        in the same sub-row overlap. O(N²), acceptable at this scale.
        Returns (assignments, n_rows) where assignments is a list of (event, row_idx).
        """
        assignments = []
        row_end_times = []
        for ev in sorted(events, key=lambda e: e.start_time):
            placed = False
            for i, row_end in enumerate(row_end_times):
                if ev.start_time >= row_end:
                    assignments.append((ev, i))
                    row_end_times[i] = ev.end_time
                    placed = True
                    break
            if not placed:
                assignments.append((ev, len(row_end_times)))
                row_end_times.append(ev.end_time)
        return assignments, len(row_end_times)

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
            day_date  = date_type(self.year, self.month, day)
            is_weekend = day_date.weekday() >= 5

            td_classes = []
            if is_today:   td_classes.append('today')
            if is_weekend: td_classes.append('weekend')
            td_cls    = (' class="' + ' '.join(td_classes) + '"') if td_classes else ''
            new_url  = reverse('cal:event_new') + f'?date={day_date.isoformat()}'
            date_num = (
                f'<span class="date today-circle">{day}</span>'
                if is_today else
                f'<span class="date">{day}</span>'
            )
            add_link = f'<a class="day-add-overlay" href="{new_url}" title="Add event">+</a>'
            return f'<td{td_cls}><div class="day-cell-header">{date_num}{add_link}</div><ul>{d}</ul></td>'
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

    # ── Day view ───────────────────────────────────────────────────────────

    def formatdayview(self, day_date):
        """
        Render the day view as a horizontal Gantt timeline.

        Rows    = all Track assets (asset_type='track'), ordered by name.
        Columns = fixed 6:00 AM to 8:00 PM time axis (840 minutes).
        Events are rendered as proportional blocks: left% = (start - 6am) / 840 * 100,
        width% = duration / 840 * 100. Events partially outside the range are clamped.
        Events entirely outside 6am-8pm are skipped (zero-width after clamping).
        Overlapping events on the same track are stacked in sub-rows.
        Only track-type assets are shown; vehicle/operator events are not shown.
        """
        GANTT_START = 6    # 6:00 AM
        GANTT_MINS  = 840  # 14 hours × 60

        is_today  = (day_date == self.today)
        today_pfx = 'Today &mdash; ' if is_today else ''
        title     = f'{today_pfx}{day_date.strftime("%A, %B %d, %Y")}'

        tracks = Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK
        ).order_by('name')

        if not tracks.exists():
            return (
                f'<div class="calendar day-view gantt-view">'
                f'<div class="day-view-title">{title}</div>'
                f'<div class="gantt-empty">No tracks configured.</div>'
                f'</div>'
            )

        # Single query for all track events on this day.
        all_events = list(
            Event.objects.filter(
                assets__asset_type=Asset.AssetType.TRACK,
                start_time__year=day_date.year,
                start_time__month=day_date.month,
                start_time__day=day_date.day,
            ).prefetch_related('assets').distinct()
        )

        # ── Time axis ────────────────────────────────────────────────
        axis_markers = ''
        for h in range(GANTT_START, GANTT_START + 15):  # 6am through 8pm inclusive
            pct   = round((h - GANTT_START) * 60 / GANTT_MINS * 100, 4)
            label = f'{h % 12 or 12}{"am" if h < 12 else "pm"}'
            axis_markers += (
                f'<div class="gantt-hour-marker" style="left:{pct}%">'
                f'<span class="gantt-hour-label">{label}</span>'
                f'</div>'
            )
        axis_row = (
            f'<div class="gantt-axis-row">'
            f'<div class="gantt-track-label-spacer"></div>'
            f'<div class="gantt-axis">{axis_markers}</div>'
            f'</div>'
        )

        # ── Track rows ───────────────────────────────────────────────
        rows_html = ''
        for track in tracks:
            track_events = sorted(
                [ev for ev in all_events
                 if any(a.id == track.id for a in ev.assets.all())],
                key=lambda ev: ev.start_time,
            )
            assigned, n_rows = self._assign_rows(track_events)

            sub_rows = [[] for _ in range(max(n_rows, 1))]
            for ev, row_idx in assigned:
                sub_rows[row_idx].append(ev)

            sub_rows_html = ''
            for sub_row_events in sub_rows:
                blocks = ''
                for ev in sub_row_events:
                    origin    = ev.start_time.replace(hour=GANTT_START, minute=0, second=0, microsecond=0)
                    start_off = max(0, int((ev.start_time - origin).total_seconds()) // 60)
                    end_off   = min(GANTT_MINS, int((ev.end_time - origin).total_seconds()) // 60)
                    width_m   = max(0, end_off - start_off)
                    if width_m == 0:
                        continue
                    left_pct  = round(start_off / GANTT_MINS * 100, 4)
                    width_pct = round(width_m   / GANTT_MINS * 100, 4)
                    edit_url  = reverse('cal:event_edit', args=(ev.id,))
                    css       = self._event_classes(ev)
                    t_start   = self._fmt_time(ev.start_time)
                    t_end     = self._fmt_time(ev.end_time)
                    blocks += (
                        f'<a class="gantt-block {css}" href="{edit_url}"'
                        f' style="left:{left_pct}%;width:{width_pct}%"'
                        f' title="{escape(ev.title)}">'
                        f'<span class="gantt-block-title">{escape(ev.title)}</span>'
                        f'<span class="gantt-block-time">{t_start}&ndash;{t_end}</span>'
                        f'</a>'
                    )
                sub_rows_html += f'<div class="gantt-sub-row">{blocks}</div>'

            rows_html += (
                f'<div class="gantt-row" style="--sub-rows:{max(n_rows,1)}">'
                f'<div class="gantt-track-label">{escape(track.name)}</div>'
                f'<div class="gantt-lane">{sub_rows_html}</div>'
                f'</div>'
            )

        return (
            f'<div class="calendar day-view gantt-view">'
            f'<div class="day-view-title">{title}</div>'
            f'{axis_row}'
            f'<div class="gantt-body">{rows_html}</div>'
            f'</div>'
        )

    # ── Week view ─────────────────────────────────────────────────────────

    def formatweekview(self, start_date):
        """
        Render a per-track timeline table for the week containing start_date.

        Rows    = all Track assets (asset_type='track'), ordered by name.
        Columns = Mon–Sun of the week.
        Each cell shows events booked for that track on that day, or a gap
        indicator ('—') if empty.

        NOTE: Intentionally ignores self.asset_id — the track view shows all
        tracks regardless of the asset filter. Documented here for future maintainers.
        """
        start = start_date - timedelta(days=start_date.weekday())  # snap to Monday
        end   = start + timedelta(days=6)

        tracks = Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK
        ).order_by('name')

        # Single query for all track-related events this week.
        # .distinct() prevents duplicates from the M2M join when an event
        # has multiple track assets.
        events = list(
            Event.objects.filter(
                assets__asset_type=Asset.AssetType.TRACK,
                start_time__date__gte=start,
                start_time__date__lte=end,
            ).prefetch_related('assets').distinct()
        )

        # Week range label — same format as formatweekview
        if start.month == end.month:
            label = f'{start.strftime("%B %d")} &ndash; {end.strftime("%d, %Y")}'
        else:
            label = f'{start.strftime("%b %d")} &ndash; {end.strftime("%b %d, %Y")}'

        day_abbr = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        days = [start + timedelta(days=i) for i in range(7)]

        # ── Header row ──────────────────────────────────────────────────────
        header_cells = '<th class="trk-label-th"></th>'  # empty top-left corner
        for i, day in enumerate(days):
            is_today  = (day == self.today)
            th_class  = 'trk-th'
            if is_today:  th_class += ' wk-today-head'
            elif i >= 5:  th_class += ' wk-weekend-head'
            num_class = 'wk-daynum wk-today-num' if is_today else 'wk-daynum'
            header_cells += (
                f'<th class="{th_class}">'
                f'<div class="wk-dayname">{day_abbr[i]}</div>'
                f'<span class="{num_class}">{day.day}</span>'
                f'</th>'
            )

        # ── Body rows — one per track ────────────────────────────────────────
        body_rows = ''
        for track in tracks:
            row = (
                f'<td class="trk-label-cell">'
                f'<span class="trk-name">{escape(track.name)}</span>'
                f'</td>'
            )
            for i, day in enumerate(days):
                td_classes = ['trk-td']
                if day == self.today: td_classes.append('today')
                if i >= 5:            td_classes.append('weekend')
                td_cls = ' '.join(td_classes)

                # Filter events for this track on this day.
                # ev.assets.all() uses the prefetch cache — no extra queries.
                day_events = sorted(
                    [
                        ev for ev in events
                        if ev.start_time.date() == day
                        and any(a.id == track.id for a in ev.assets.all())
                    ],
                    key=lambda ev: ev.start_time,
                )

                if day_events:
                    items = ''.join(
                        f'<li class="{self._event_classes(ev)}">{ev.get_html_url}</li>'
                        for ev in day_events
                    )
                    cell_content = f'<ul class="trk-events">{items}</ul>'
                else:
                    cell_content = '<span class="trk-gap">&#8212;</span>'

                row += f'<td class="{td_cls}">{cell_content}</td>'

            body_rows += f'<tr>{row}</tr>'

        if not body_rows:
            body_rows = (
                '<tr>'
                '<td colspan="8" class="trk-empty">No tracks configured.</td>'
                '</tr>'
            )

        return (
            f'<div class="calendar track-view">'
            f'<div class="week-label">{label}</div>'
            f'<div class="trk-scroll-wrap">'
            f'<table class="trk-table">'
            f'<thead><tr>{header_cells}</tr></thead>'
            f'<tbody>{body_rows}</tbody>'
            f'</table>'
            f'</div>'
            f'</div>'
        )
