"""
Calendar HTML rendering utilities.

Extends Python's ``calendar.HTMLCalendar`` to produce month, week, and day
views populated with Event data.  Each view supports optional asset filtering
and highlights today's date and weekends with CSS classes.
"""

from datetime import datetime, timedelta, date as date_type
from calendar import HTMLCalendar

from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.timezone import localtime

from cal.models import Asset, Event


def get_asset_conflicts(asset, start_time, end_time, exclude_event_id=None, approved_only=False):
    """
    Return a QuerySet of Events that conflict with the given asset/time range.
    Expands to parent/subtrack conflict IDs via Asset.conflicting_asset_ids().
    If approved_only=True, only checks approved events.
    """
    qs = Event.objects.filter(
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if approved_only:
        qs = qs.filter(is_approved=True)
    if exclude_event_id:
        qs = qs.exclude(pk=exclude_event_id)

    conflict_ids = asset.conflicting_asset_ids()
    return qs.filter(assets__in=conflict_ids).distinct()


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
        qs = Event.objects.select_related('created_by').prefetch_related('assets', 'segments')
        if self.asset_id:
            qs = qs.filter(assets__id=self.asset_id)
        return qs

    def _event_classes(self, event):
        """Build a CSS class string for an event (type colour + pending/operational state)."""
        classes = f'event {event.asset_css_class}'
        if not event.is_approved:
            classes += ' event-pending'
        else:
            now = timezone.now()
            is_past = event.end_time <= now
            if is_past:
                has_segments = len(event.segments.all()) > 0
                if has_segments:
                    classes += ' event-completed'
                else:
                    classes += ' event-noshow'
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
        events_list = list(events.filter(start_time__day=day).order_by('start_time'))

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
        all_events = list(
            Event.objects.filter(
                assets__asset_type=Asset.AssetType.TRACK,
                start_time__year=day_date.year,
                start_time__month=day_date.month,
                start_time__day=day_date.day,
            ).select_related('created_by').prefetch_related('assets', 'segments').distinct()
        )

        # Build a helper: event_asset_ids[ev.pk] = set of asset PKs for fast lookup
        event_asset_ids = {
            ev.pk: {a.pk for a in ev.assets.all()}
            for ev in all_events
        }

        if all_events:
            earliest_dt = localtime(min(ev.start_time for ev in all_events))
            latest_dt = localtime(max(ev.end_time for ev in all_events))
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

            Renders a single visual line per event with layered elements:
            - Scheduled bar (semi-transparent background, always visible)
            - Actual segment bars (solid, one per closed segment)
            - Active segment bar (solid + pulse animation, grows live)
            - Pause gaps (dotted outline between segments)
            - Overflow indicators (dotted borders when actuals exceed scheduled)
            """
            local_start = localtime(ev.start_time)
            local_end   = localtime(ev.end_time)
            origin    = local_start.replace(hour=GANTT_START, minute=0, second=0, microsecond=0)
            edit_url  = reverse('cal:event_edit', args=(ev.id,))
            # Strip asset-type classes that are overridden by inline track_color in Gantt
            base_css  = self._event_classes(ev)
            for cls in ('event-track', 'event-vehicle', 'event-operator', 'event-multi'):
                base_css = base_css.replace(cls, '')
            base_css = ' '.join(base_css.split())  # clean up double spaces
            if extra_css:
                base_css += f' {extra_css}'
            is_pending = not ev.is_approved
            color_style = f'--track-color:{track_color};' if track_color else ''
            bg_style    = f'background:{track_color};' if track_color and not is_pending else ''
            end_iso   = ev.end_time.isoformat()
            creator_name = escape(ev.created_by.username) if ev.created_by else ''
            creator_attr = f' data-creator="{creator_name}"' if creator_name else ''
            title_suffix = f' — {creator_name}' if creator_name else ''

            segs = list(ev.segments.all())  # prefetched
            has_segments = len(segs) > 0

            # --- scheduled bar offset ---
            start_off = max(0, int((local_start - origin).total_seconds()) // 60)
            end_off   = min(GANTT_MINS, int((local_end - origin).total_seconds()) // 60)
            width_m   = max(0, end_off - start_off)
            if width_m == 0 and not has_segments:
                return ''

            parts = []

            # --- Scheduled bar (always shown) ---
            if width_m > 0:
                left_pct  = round(start_off / GANTT_MINS * 100, 4)
                width_pct = round(width_m   / GANTT_MINS * 100, 4)
                t_start   = self._fmt_time(ev.start_time)
                t_end     = self._fmt_time(ev.end_time)
                sched_cls = ' gantt-block--scheduled' if has_segments else ''
                # When segments exist, text goes in a separate overlay
                # so it isn't trapped by opacity stacking contexts
                text_html = (
                    f'<span class="gantt-block-title">{escape(ev.title)}</span>'
                    f'<span class="gantt-block-time">{t_start}&ndash;{t_end}</span>'
                ) if not has_segments else ''
                parts.append(
                    f'<a class="gantt-block {base_css}{sched_cls}" href="{edit_url}"'
                    f' style="left:{left_pct}%;width:{width_pct}%;{color_style}{bg_style}"'
                    f' title="{escape(ev.title)}{title_suffix}"'
                    f' data-event-id="{ev.pk}"'
                    f' data-is-approved="{str(ev.is_approved).lower()}"'
                    f' data-end="{end_iso}"{creator_attr}>'
                    f'{text_html}'
                    f'</a>'
                )

            # --- Actual segment bars ---
            for i, seg in enumerate(segs):
                seg_start = localtime(seg.start)
                is_open = seg.end is None
                seg_end = localtime(seg.end) if seg.end else localtime(timezone.now())

                seg_start_off = max(0, int((seg_start - origin).total_seconds()) // 60)
                seg_end_off   = min(GANTT_MINS, int((seg_end - origin).total_seconds()) // 60)
                seg_width     = max(0, seg_end_off - seg_start_off)

                if seg_width > 0:
                    seg_left     = round(seg_start_off / GANTT_MINS * 100, 4)
                    seg_width_pct = round(seg_width / GANTT_MINS * 100, 4)

                    # Overflow detection
                    overflow_start = seg_start < local_start
                    overflow_end = (seg.end and localtime(seg.end) > local_end) or (is_open and localtime(timezone.now()) > local_end)
                    overflow_cls = ''
                    if overflow_start:
                        overflow_cls += ' gantt-block--overflow-start'
                    if overflow_end:
                        overflow_cls += ' gantt-block--overflow-end'

                    active_cls = ' gantt-block--active-segment' if is_open else ' gantt-block--actual-segment'
                    data_attrs = f' data-segment-start="{seg.start.isoformat()}"' if is_open else ''

                    parts.append(
                        f'<div class="gantt-block-segment{active_cls}{overflow_cls}"'
                        f' style="left:{seg_left}%;width:{seg_width_pct}%;{color_style}"'
                        f'{data_attrs}>'
                        f'</div>'
                    )

                # Pause gap between this segment and the next
                if i + 1 < len(segs) and seg.end:
                    next_seg = segs[i + 1]
                    gap_start = localtime(seg.end)
                    gap_end   = localtime(next_seg.start)
                    gap_start_off = max(0, int((gap_start - origin).total_seconds()) // 60)
                    gap_end_off   = min(GANTT_MINS, int((gap_end - origin).total_seconds()) // 60)
                    gap_width     = max(0, gap_end_off - gap_start_off)
                    if gap_width > 0:
                        gap_left     = round(gap_start_off / GANTT_MINS * 100, 4)
                        gap_width_pct = round(gap_width / GANTT_MINS * 100, 4)
                        parts.append(
                            f'<div class="gantt-block-segment gantt-block--pause-gap"'
                            f' style="left:{gap_left}%;width:{gap_width_pct}%;{color_style}">'
                            f'</div>'
                        )

            # --- Text overlay (above segments, avoids opacity stacking) ---
            if has_segments and width_m > 0:
                parts.append(
                    f'<a class="gantt-block-text" href="{edit_url}"'
                    f' style="left:{left_pct}%;width:{width_pct}%;"'
                    f' title="{escape(ev.title)}{title_suffix}">'
                    f'<span class="gantt-block-title">{escape(ev.title)}</span>'
                    f'<span class="gantt-block-time">{t_start}&ndash;{t_end}</span>'
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
                    [ev for ev in all_events if track.pk in event_asset_ids[ev.pk]],
                    key=lambda ev: ev.start_time,
                )
                n_sub = len(subtracks)

                # Build one sub-row per subtrack (label lives in the track-label column)
                sub_rows_html = ''
                subtrack_names_html = ''
                for sub in subtracks:
                    sub_events = sorted(
                        [ev for ev in all_events if sub.pk in event_asset_ids[ev.pk]],
                        key=lambda ev: ev.start_time,
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
                    [ev for ev in all_events if track.pk in event_asset_ids[ev.pk]],
                    key=lambda ev: ev.start_time,
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

        # Set legend context flags on the Calendar instance for the view to read.
        # Use current time-of-day projected onto the viewed date so that past
        # events on any viewed day are classified correctly.
        now_local = localtime(timezone.now())
        cutoff = now_local.replace(
            year=day_date.year, month=day_date.month, day=day_date.day,
        )
        self.gantt_has_pending = any(not ev.is_approved for ev in all_events)
        self.gantt_has_active = any(
            any(seg.end is None for seg in ev.segments.all())
            for ev in all_events
        )
        past_approved = [ev for ev in all_events if ev.end_time <= cutoff and ev.is_approved]
        self.gantt_has_completed = any(len(ev.segments.all()) > 0 for ev in past_approved)
        self.gantt_has_noshow = any(len(ev.segments.all()) == 0 for ev in past_approved)

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
        events = list(
            Event.objects.filter(
                assets__asset_type=Asset.AssetType.TRACK,
                start_time__date__gte=start,
                start_time__date__lte=end,
            ).select_related('created_by').prefetch_related('assets', 'segments').distinct()
        )

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
                    if localtime(ev.start_time).date() == day
                    and asset_pk in event_asset_ids[ev.pk]
                ],
                key=lambda ev: ev.start_time,
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
                    key=lambda ev: ev.start_time,
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
