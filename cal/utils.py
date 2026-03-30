"""
Calendar HTML rendering utilities.

Extends Python's ``calendar.HTMLCalendar`` to produce month, week, and day
views populated with Event data.  Each view supports optional asset filtering
and highlights today's date and weekends with CSS classes.
"""

from datetime import datetime, timedelta, date as date_type
from calendar import HTMLCalendar

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.timezone import localtime

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
        qs = Event.objects.select_related('created_by').prefetch_related('assets')
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
        return localtime(dt).strftime('%I:%M %p').lstrip('0') or '12:00 AM'

    @staticmethod
    def _assign_rows(events):
        """
        Assign each event to a sub-row index (0-based) such that no two events
        in the same sub-row overlap. O(N²), acceptable at this scale.
        Returns (assignments, n_rows) where assignments is a list of (event, row_idx).
        """
        def _ev_start(ev):
            """Return effective start time: start_time or actual_start."""
            return ev.start_time or ev.actual_start
        def _ev_end(ev):
            """Return effective end time: end_time or actual_end or now."""
            return ev.end_time or ev.actual_end or timezone.now()
        events = [ev for ev in events if _ev_start(ev) and _ev_end(ev)]
        assignments = []
        row_end_times = []
        for ev in sorted(events, key=lambda e: _ev_start(e)):
            placed = False
            ev_s = _ev_start(ev)
            ev_e = _ev_end(ev)
            for i, row_end in enumerate(row_end_times):
                if ev_s >= row_end:
                    assignments.append((ev, i))
                    row_end_times[i] = ev_e
                    placed = True
                    break
            if not placed:
                assignments.append((ev, len(row_end_times)))
                row_end_times.append(ev_e)
        return assignments, len(row_end_times)

    # ── Month view ─────────────────────────────────────────────────────────

    # Maximum events shown inline in a month cell before a "more" button appears.
    # Sized to fit within the 180px cell height (date header ~30px + 2 event tiles ~90px each).
    MONTH_VISIBLE_LIMIT = 2

    def formatday(self, day, events):
        """
        Render a single day cell for the month table.

        ``day=0`` represents a filler cell outside the current month.
        Real days receive 'today' and/or 'weekend' CSS classes as needed.

        Up to MONTH_VISIBLE_LIMIT events are shown inline.  If there are more,
        a "+N more" button is rendered; clicking it opens a modal (driven by JS
        in calendar.html) that lists all events for the day with times.
        """
        events_list = list(
            events.filter(
                Q(start_time__day=day) | Q(is_impromptu=True, actual_start__day=day)
            ).order_by('start_time', 'actual_start')
        )

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

            # Visible event tiles (capped at MONTH_VISIBLE_LIMIT)
            visible = events_list[:self.MONTH_VISIBLE_LIMIT]
            d = ''.join(
                f'<li class="{self._event_classes(ev)}">{ev.get_html_url}</li>'
                for ev in visible
            )

            # "+N more" button + hidden full list for the modal
            more_html = ''
            n_extra = len(events_list) - self.MONTH_VISIBLE_LIMIT
            if n_extra > 0:
                day_label = day_date.strftime('%A, %B %-d, %Y')
                all_items = ''.join(
                    f'<li class="{self._event_classes(ev)} event-modal-item">'
                    f'{ev.get_html_url}'
                    f'</li>'
                    for ev in events_list
                )
                more_html = (
                    f'<button class="day-more-btn"'
                    f' data-date="{day_date.isoformat()}"'
                    f' data-label="{escape(day_label)}">'
                    f'+{n_extra} more'
                    f'</button>'
                    f'<ul class="day-all-events" hidden>{all_items}</ul>'
                )

            return (
                f'<td{td_cls}>'
                f'<div class="day-cell-inner">'
                f'<div class="day-cell-header">{date_num}{add_link}</div>'
                f'<ul>{d}</ul>'
                f'{more_html}'
                f'</div>'
                f'</td>'
            )
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
        # Combine scheduled + impromptu events for the month.
        # Use Q-based OR so formatday can still call .filter() on the queryset.
        events = self._base_queryset().filter(
            Q(start_time__year=self.year, start_time__month=self.month)
            | Q(is_impromptu=True, actual_start__year=self.year, actual_start__month=self.month)
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
        Columns = full 24-hour time axis (midnight to midnight, 1440 minutes).

        Subtrack support:
        - Tracks with subtracks render one Gantt row per subtrack.
        - Full-track events (booked on the parent asset) span ALL subtrack
          rows using a CSS variable (--subtrack-span) and absolute positioning.
        - Tracks without subtracks render as a single row (unchanged).

        Events are rendered as proportional blocks: left% = start_min / 1440 * 100,
        width% = duration / 1440 * 100. Overlapping events on the same sub-row
        are stacked further via _assign_rows.
        Only track-type assets are shown; vehicle/operator events are not shown.

        The wrapper div includes data attributes (data-gantt-start, data-gantt-mins,
        data-event-earliest, data-event-latest) used by the JS auto-scroll logic.
        """
        GANTT_START = 0    # midnight
        GANTT_MINS  = 1440  # 24 hours

        is_today  = (day_date == self.today)
        today_pfx = 'Today &mdash; ' if is_today else ''
        title     = f'{today_pfx}{day_date.strftime("%A, %B %d, %Y")}'

        # Fetch only top-level tracks (parent=None), ordered by name.
        # Each track's subtracks are prefetched via 'subtracks'.
        parent_tracks = list(
            Asset.objects.filter(
                asset_type=Asset.AssetType.TRACK,
                parent__isnull=True,
            ).prefetch_related('subtracks').order_by('name')
        )

        if not parent_tracks:
            return (
                f'<div class="calendar day-view gantt-view">'
                f'<div class="day-view-title">{title}</div>'
                f'<div class="gantt-empty">No tracks configured.</div>'
                f'</div>'
            )

        # Single query for all track events on this day (both parent + subtrack assets).
        scheduled_events = Event.objects.filter(
            assets__asset_type=Asset.AssetType.TRACK,
            start_time__year=day_date.year,
            start_time__month=day_date.month,
            start_time__day=day_date.day,
        ).select_related('created_by').prefetch_related('assets').distinct()

        # Impromptu events (no start_time) — shown on the day they actually started.
        impromptu_events = Event.objects.filter(
            is_approved=True,
            is_impromptu=True,
            actual_start__date=day_date,
            assets__asset_type=Asset.AssetType.TRACK,
        ).select_related('created_by').prefetch_related('assets').distinct()

        # Combine scheduled + impromptu, dedup by pk
        seen_pks = set()
        all_events = []
        for ev in list(scheduled_events) + list(impromptu_events):
            if ev.pk not in seen_pks:
                seen_pks.add(ev.pk)
                all_events.append(ev)

        # Build a helper: event_asset_ids[ev.pk] = set of asset PKs for fast lookup
        event_asset_ids = {
            ev.pk: {a.pk for a in ev.assets.all()}
            for ev in all_events
        }

        timed_events = [ev for ev in all_events if (ev.start_time and ev.end_time) or ev.actual_start]
        if timed_events:
            earliest_dt = localtime(min(ev.start_time or ev.actual_start for ev in timed_events))
            latest_dt = localtime(max(ev.end_time or ev.actual_end or timezone.now() for ev in timed_events))
            data_earliest = earliest_dt.hour * 60 + earliest_dt.minute
            data_latest = latest_dt.hour * 60 + latest_dt.minute
        else:
            data_earliest = None
            data_latest = None

        # ── Time axis ────────────────────────────────────────────────
        axis_markers = ''
        for h in range(0, 24):
            pct   = round((h - GANTT_START) * 60 / GANTT_MINS * 100, 4)
            label = f'{h % 12 or 12}{"am" if h < 12 else "pm"}'
            axis_markers += (
                f'<div class="gantt-hour-marker" style="left:{pct}%">'
                f'<span class="gantt-hour-label">{label}</span>'
                f'</div>'
            )
        axis_row = (
            f'<div class="gantt-axis-row">'
            f'<div class="gantt-track-label gantt-axis-label" style="border-left:none;"></div>'
            f'<div class="gantt-sublabel-col gantt-axis-sublabel"></div>'
            f'<div class="gantt-axis">{axis_markers}</div>'
            f'</div>'
        )

        def _make_block(ev, extra_css='', track_color=None):
            """Build the HTML for a single Gantt event block.

            When an event has actual_start/actual_end, two blocks are returned:
            a ghost (scheduled) bar and a solid (actual) bar.  Otherwise a
            single solid bar is returned for the scheduled time.

            Impromptu events (no start_time/end_time) use actual_start for
            positioning, and actual_end or now() for the end.
            """
            # For impromptu events, use actual times for positioning
            if ev.start_time is None:
                if ev.actual_start is None:
                    return ''  # Can't render without any time reference
                effective_start = ev.actual_start
                effective_end = ev.actual_end or timezone.now()
                local_start = localtime(effective_start)
                local_end   = localtime(effective_end)
            elif ev.end_time is None:
                return ''
            else:
                local_start = localtime(ev.start_time)
                local_end   = localtime(ev.end_time)
            origin    = local_start.replace(hour=GANTT_START, minute=0, second=0, microsecond=0)
            edit_url  = reverse('cal:event_edit', args=(ev.id,))
            base_css  = self._event_classes(ev) + (f' {extra_css}' if extra_css else '')
            if getattr(ev, 'is_impromptu', False):
                base_css += ' event-impromptu'
            color_style = f'background:{track_color};' if track_color else ''
            end_iso   = (ev.end_time or ev.actual_end or timezone.now()).isoformat()
            creator_name = escape(ev.created_by.username) if ev.created_by else ''
            creator_attr = f' data-creator="{creator_name}"' if creator_name else ''
            title_suffix = f' — {creator_name}' if creator_name else ''

            has_actual = ev.actual_start or ev.actual_end

            # --- scheduled bar (ghost when actuals exist) ---
            start_off = max(0, int((local_start - origin).total_seconds()) // 60)
            end_off   = min(GANTT_MINS, int((local_end - origin).total_seconds()) // 60)
            width_m   = max(0, end_off - start_off)
            if width_m == 0 and not has_actual:
                return ''

            parts = []

            is_impromptu = getattr(ev, 'is_impromptu', False)

            if width_m > 0:
                left_pct  = round(start_off / GANTT_MINS * 100, 4)
                width_pct = round(width_m   / GANTT_MINS * 100, 4)
                t_start   = self._fmt_time(ev.start_time or ev.actual_start)
                t_end     = self._fmt_time(ev.end_time or ev.actual_end or timezone.now())
                ghost_cls = ' gantt-block--ghost' if (has_actual and not is_impromptu) else ''
                parts.append(
                    f'<a class="gantt-block {base_css}{ghost_cls}" href="{edit_url}"'
                    f' style="left:{left_pct}%;width:{width_pct}%;{color_style}"'
                    f' title="{escape(ev.title)}{title_suffix}"'
                    f' data-end="{end_iso}"{creator_attr}>'
                    f'<span class="gantt-block-title">{escape(ev.title)}</span>'
                    f'<span class="gantt-block-time">{t_start}&ndash;{t_end}</span>'
                    f'</a>'
                )

            # --- actual bar (solid) ---
            if has_actual and not is_impromptu:
                act_start = localtime(ev.actual_start) if ev.actual_start else (localtime(ev.start_time) if ev.start_time else None)
                act_end   = localtime(ev.actual_end) if ev.actual_end else (localtime(ev.end_time) if ev.end_time else localtime(timezone.now()))
                if act_start is None or act_end is None:
                    return ''.join(parts)
                a_start_off = max(0, int((act_start - origin).total_seconds()) // 60)
                a_end_off   = min(GANTT_MINS, int((act_end - origin).total_seconds()) // 60)
                a_width_m   = max(0, a_end_off - a_start_off)
                if a_width_m > 0:
                    a_left_pct  = round(a_start_off / GANTT_MINS * 100, 4)
                    a_width_pct = round(a_width_m   / GANTT_MINS * 100, 4)
                    a_t_start   = self._fmt_time(act_start)
                    a_t_end     = self._fmt_time(act_end)
                    parts.append(
                        f'<a class="gantt-block gantt-block--actual {base_css}" href="{edit_url}"'
                        f' style="left:{a_left_pct}%;width:{a_width_pct}%;{color_style}"'
                        f' title="{escape(ev.title)} (actual){title_suffix}"'
                        f' data-end="{end_iso}"{creator_attr}>'
                        f'<span class="gantt-block-title">{escape(ev.title)}</span>'
                        f'<span class="gantt-block-time">{a_t_start}&ndash;{a_t_end}</span>'
                        f'</a>'
                    )

            return ''.join(parts)

        # ── Track rows ───────────────────────────────────────────────
        rows_html = ''
        for track in parent_tracks:
            subtracks = list(track.subtracks.order_by('name'))

            if subtracks:
                # ── Track with subtracks ─────────────────────────────
                # Parent-booked events span all subtrack rows.
                # Subtrack-booked events appear only in their own row.

                # Events booked directly on the parent (full-track)
                parent_events = sorted(
                    [ev for ev in all_events if track.pk in event_asset_ids[ev.pk] and (ev.start_time or ev.actual_start)],
                    key=lambda ev: ev.start_time or ev.actual_start,
                )
                n_sub = len(subtracks)

                # Build one sub-row per subtrack (label lives in the track-label column)
                sub_rows_html = ''
                subtrack_names_html = ''
                for sub in subtracks:
                    sub_events = sorted(
                        [ev for ev in all_events if sub.pk in event_asset_ids[ev.pk] and (ev.start_time or ev.actual_start)],
                        key=lambda ev: ev.start_time or ev.actual_start,
                    )
                    assigned, n_rows = self._assign_rows(sub_events)
                    row_buckets = [[] for _ in range(max(n_rows, 1))]
                    for ev, row_idx in assigned:
                        row_buckets[row_idx].append(ev)

                    inner_rows = ''
                    for bucket in row_buckets:
                        blocks = ''.join(_make_block(ev, track_color=track.color) for ev in bucket)
                        inner_rows += f'<div class="gantt-sub-row">{blocks}</div>'

                    sub_rows_html += f'<div class="gantt-subtrack-row">{inner_rows}</div>'
                    subtrack_names_html += (
                        f'<span class="gantt-subtrack-name">{escape(sub.name)}</span>'
                    )

                # Full-track (parent) events rendered as an overlay spanning all sub-rows.
                parent_blocks = ''.join(_make_block(ev, 'gantt-fulltrack-block', track_color=track.color) for ev in parent_events)
                parent_overlay = (
                    f'<div class="gantt-fulltrack-overlay" style="--subtrack-count:{n_sub}">'
                    f'{parent_blocks}'
                    f'</div>'
                ) if parent_blocks else ''

                label_style = f'border-left:3px solid {track.color};' if track.color else ''
                rows_html += (
                    f'<div class="gantt-row gantt-row-has-subtracks" style="--sub-rows:{n_sub}">'
                    f'<div class="gantt-track-label" style="{label_style}">{escape(track.name)}</div>'
                    f'<div class="gantt-sublabel-col">{subtrack_names_html}</div>'
                    f'<div class="gantt-lane gantt-lane-subtracks">'
                    f'{parent_overlay}'
                    f'{sub_rows_html}'
                    f'</div>'
                    f'</div>'
                )
            else:
                # ── Track without subtracks (original behaviour) ──────
                track_events = sorted(
                    [ev for ev in all_events if track.pk in event_asset_ids[ev.pk] and (ev.start_time or ev.actual_start)],
                    key=lambda ev: ev.start_time or ev.actual_start,
                )
                assigned, n_rows = self._assign_rows(track_events)

                sub_rows = [[] for _ in range(max(n_rows, 1))]
                for ev, row_idx in assigned:
                    sub_rows[row_idx].append(ev)

                sub_rows_html = ''
                for sub_row_events in sub_rows:
                    blocks = ''.join(_make_block(ev, track_color=track.color) for ev in sub_row_events)
                    sub_rows_html += f'<div class="gantt-sub-row">{blocks}</div>'

                label_style = f'border-left:3px solid {track.color};' if track.color else ''
                rows_html += (
                    f'<div class="gantt-row" style="--sub-rows:{max(n_rows,1)}">'
                    f'<div class="gantt-track-label" style="{label_style}">{escape(track.name)}</div>'
                    f'<div class="gantt-sublabel-col"></div>'
                    f'<div class="gantt-lane">{sub_rows_html}</div>'
                    f'</div>'
                )

        data_attrs = f' data-gantt-start="{GANTT_START}" data-gantt-mins="{GANTT_MINS}"'
        if data_earliest is not None:
            data_attrs += f' data-event-earliest="{data_earliest}" data-event-latest="{data_latest}"'

        return (
            f'<div class="calendar day-view gantt-view"{data_attrs}>'
            f'<div class="day-view-title">{title}</div>'
            f'<div class="gantt-scroll-container">'
            f'{axis_row}'
            f'<div class="gantt-body">{rows_html}</div>'
            f'</div>'
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

        Subtrack support:
        - Tracks with subtracks render as TWO rows (one per subtrack), with
          the track name cell spanning both rows (rowspan=2).
        - Full-track events (booked on the parent) appear in a merged cell
          that spans both subtrack rows.
        - Tracks with no subtracks remain as single rows (unchanged).

        NOTE: Intentionally ignores self.asset_id — the track view shows all
        tracks regardless of the asset filter. Documented here for future maintainers.
        """
        start = start_date - timedelta(days=start_date.weekday())  # snap to Monday
        end   = start + timedelta(days=6)

        # Fetch only top-level tracks; prefetch their subtracks.
        parent_tracks = list(
            Asset.objects.filter(
                asset_type=Asset.AssetType.TRACK,
                parent__isnull=True,
            ).prefetch_related('subtracks').order_by('name')
        )

        # Single query for all track-related events this week.
        scheduled_wk = Event.objects.filter(
            assets__asset_type=Asset.AssetType.TRACK,
            start_time__date__gte=start,
            start_time__date__lte=end,
        ).select_related('created_by').prefetch_related('assets').distinct()

        # Impromptu events this week (no start_time, use actual_start).
        impromptu_wk = Event.objects.filter(
            is_approved=True,
            is_impromptu=True,
            actual_start__date__gte=start,
            actual_start__date__lte=end,
            assets__asset_type=Asset.AssetType.TRACK,
        ).select_related('created_by').prefetch_related('assets').distinct()

        # Combine scheduled + impromptu, dedup by pk
        _seen_wk = set()
        events = []
        for _ev in list(scheduled_wk) + list(impromptu_wk):
            if _ev.pk not in _seen_wk:
                _seen_wk.add(_ev.pk)
                events.append(_ev)

        # Build a lookup: event_asset_ids[ev.pk] = set of asset PKs
        event_asset_ids = {
            ev.pk: {a.pk for a in ev.assets.all()}
            for ev in events
        }

        # Week range label
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

        def _day_events_for_asset(asset_pk, day):
            """Return sorted events for a given asset PK on a given day."""
            return sorted(
                [
                    ev for ev in events
                    if (
                        (ev.start_time and localtime(ev.start_time).date() == day)
                        or (ev.is_impromptu and ev.actual_start and localtime(ev.actual_start).date() == day)
                    )
                    and asset_pk in event_asset_ids[ev.pk]
                ],
                key=lambda ev: ev.start_time or ev.actual_start,
            )

        def _cell_html(day_evs, td_cls):
            """Render a <td> cell with a list of events or a gap marker."""
            if day_evs:
                items = ''.join(
                    f'<li class="{self._event_classes(ev)}">{ev.get_html_url}</li>'
                    for ev in day_evs
                )
                content = f'<ul class="trk-events">{items}</ul>'
            else:
                content = '<span class="trk-gap">&#8212;</span>'
            return f'<td class="{td_cls}">{content}</td>'

        # ── Body rows — one per track ────────────────────────────────────────
        body_rows = ''
        for track in parent_tracks:
            subtracks = list(track.subtracks.order_by('name'))
            dot = (
                f'<span class="trk-color-dot" style="background:{track.color}"></span>'
                if track.color else ''
            )
            row = (
                f'<td class="trk-label-cell">'
                f'{dot}<span class="trk-name">{escape(track.name)}</span>'
                f'</td>'
            )
            for i, day in enumerate(days):
                td_classes = ['trk-td']
                if day == self.today: td_classes.append('today')
                if i >= 5:            td_classes.append('weekend')
                td_cls  = ' '.join(td_classes)
                # Collect events for the parent track and all its subtracks.
                all_pks = [track.pk] + [s.pk for s in subtracks]
                day_evs = sorted(
                    {ev for pk in all_pks for ev in _day_events_for_asset(pk, day)},
                    key=lambda ev: ev.start_time or ev.actual_start or datetime.max,
                )
                row += _cell_html(day_evs, td_cls)
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
