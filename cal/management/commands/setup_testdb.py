"""
Management command to set up a test database with seed data and realistic events.

Usage:
    python3 manage.py setup_testdb                # Fresh DB with 7 days of events
    python3 manage.py setup_testdb --days 30      # Wider date range
    python3 manage.py setup_testdb --no-events    # Just seed data, no events
    python3 manage.py setup_testdb --keep-db      # Add events without resetting
"""

import random
from datetime import datetime, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.timezone import get_current_timezone

from cal.models import Asset, Event
from users.models import User


# ── Event templates ──────────────────────────────────────────────────────────
# (title, description, duration_hours, weight, needs_vehicle)

EVENT_TEMPLATES = [
    # AV testing — usually need a vehicle + track
    ("AV Navigation Test", "Autonomous navigation system validation run", 2.0, 5, True),
    ("Obstacle Avoidance Trial", "Testing obstacle detection and avoidance", 1.5, 4, True),
    ("Sensor Calibration", "LiDAR and camera sensor calibration", 1.0, 6, True),
    ("GPS RTK Accuracy Test", "High-precision GPS testing across waypoints", 1.5, 3, True),
    ("Emergency Stop Validation", "E-stop system testing under multiple scenarios", 1.0, 4, True),
    ("Path Planning Benchmark", "New path planning algorithm performance eval", 2.0, 3, True),
    ("Speed Controller Tuning", "PID tuning for speed control module", 1.5, 3, True),
    ("Multi-Vehicle Coordination", "Fleet coordination and collision avoidance", 3.0, 2, True),
    ("Data Collection Run", "Structured data collection for ML training", 3.0, 4, True),
    ("Endurance Test", "Extended duration reliability run", 4.0, 1, True),
    ("Payload Capacity Test", "Vehicle performance under load conditions", 2.0, 2, True),

    # Track-only activities
    ("Track Grading", "Grade and level dirt track surface", 2.0, 2, False),
    ("Cone Setup - Slalom Course", "Set up slalom obstacle course", 1.0, 3, False),
    ("Track Marker Refresh", "Repaint lane markers and boundary lines", 2.0, 1, False),
    ("Debris Cleanup", "Clear debris from track surface", 1.0, 2, False),
    ("Safety Briefing", "Team safety briefing and protocol review", 1.0, 3, False),

    # Vehicle on track
    ("Vehicle Inspection", "Pre-test vehicle inspection and systems check", 1.0, 5, True),
    ("Firmware Update", "Flash updated firmware to vehicle control unit", 1.5, 2, True),

    # Demos
    ("Client Demo", "Live demonstration for prospective client", 2.0, 3, True),
    ("Investor Demo", "Executive demonstration for investor group", 2.0, 1, True),
    ("Video Capture Session", "Record footage for marketing", 2.0, 2, True),

    # Training & R&D
    ("New Operator Training", "Onboarding training for vehicle operators", 3.0, 2, True),
    ("Engineering Review", "On-track engineering review and troubleshooting", 2.0, 3, True),
    ("R&D Experiment", "Research experiment - new actuator testing", 2.0, 2, True),
    ("Mapping Run", "HD map generation run for track digitization", 2.0, 2, True),
]

EXTRA_USERS = ["hollis", "sarah", "mike", "jessica", "david", "emma"]

HOUR_WEIGHTS = {
    6: 1, 7: 3, 8: 8, 9: 10, 10: 10, 11: 8,
    12: 4, 13: 8, 14: 10, 15: 9, 16: 6, 17: 3, 18: 1,
}


class Command(BaseCommand):
    help = "Reset DB with seed assets/users and generate realistic test events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=7,
            help="Number of days to generate (centered on today, default: 7)",
        )
        parser.add_argument(
            "--no-events", action="store_true",
            help="Only load seed data, skip event generation",
        )
        parser.add_argument(
            "--keep-db", action="store_true",
            help="Don't reset — just add events to existing data",
        )
        parser.add_argument(
            "--events-per-day", type=int, default=0,
            help="Average events per weekday (0 = auto: 8-14)",
        )

    def handle(self, *args, **options):
        if not options["keep_db"]:
            self._reset_and_seed()
        else:
            self.stdout.write("Keeping existing database, adding events only")

        if not options["no_events"]:
            self._generate_events(options["days"], options["events_per_day"])

    def _reset_and_seed(self):
        """Flush DB and load seed fixture."""
        self.stdout.write(self.style.WARNING("Flushing database..."))
        call_command("flush", "--no-input", verbosity=0)

        self.stdout.write("Loading seed fixture (assets + users)...")
        call_command("loaddata", "seed.json", verbosity=0)

        assets = Asset.objects.count()
        users = User.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {assets} assets and {users} users"
        ))

    def _ensure_extra_users(self):
        """Create additional test users beyond the seed fixture."""
        users = list(User.objects.all())
        for username in EXTRA_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@asirobotics.com",
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
                self.stdout.write(f"  Created test user: {username}")
            users.append(user)
        return users

    def _generate_events(self, days, epd):
        """Generate realistic events across the date range."""
        users = self._ensure_extra_users()

        # Organize assets
        parent_tracks = list(Asset.objects.filter(
            asset_type=Asset.AssetType.TRACK, parent__isnull=True,
        ))
        vehicles = list(Asset.objects.filter(asset_type=Asset.AssetType.VEHICLE))

        # Build track group map: {parent: [subtracks]}
        track_groups = {}
        for parent in parent_tracks:
            subs = list(parent.subtracks.all())
            track_groups[parent] = subs

        self.stdout.write(
            f"Generating events: {len(parent_tracks)} track groups, "
            f"{len(vehicles)} vehicles, {len(users)} users"
        )

        today = timezone.now().date()
        start_date = today - timedelta(days=days // 2)
        end_date = today + timedelta(days=(days + 1) // 2)

        total = 0
        current = start_date
        while current <= end_date:
            is_weekend = current.weekday() >= 5
            if epd > 0:
                day_count = max(1, int(random.gauss(epd, 2)))
            elif is_weekend:
                day_count = random.randint(1, 4)
            else:
                day_count = random.randint(8, 14)

            created = self._generate_day(
                current, day_count, track_groups, vehicles, users,
            )
            total += created
            current += timedelta(days=1)

        # Stats
        approved = Event.objects.filter(is_approved=True).count()
        pending = Event.objects.filter(is_approved=False).count()
        stamped = Event.objects.exclude(actual_start=None).count()

        self.stdout.write(self.style.SUCCESS(
            f"\nCreated {total} events ({start_date} to {end_date})"
        ))
        self.stdout.write(f"  Approved: {approved}  |  Pending: {pending}")
        self.stdout.write(f"  With actual timestamps: {stamped}")

    def _generate_day(self, date, count, track_groups, vehicles, users):
        """Generate events for one day, respecting subtrack conflict rules."""
        created = 0
        # Busy slots: {asset_id: [(start_h, end_h), ...]}
        busy = {}

        for _ in range(count):
            tmpl = random.choices(
                EVENT_TEMPLATES, weights=[t[3] for t in EVENT_TEMPLATES], k=1,
            )[0]
            title, desc, duration_h, _, needs_vehicle = tmpl

            # Pick a track group and decide: book parent or subtracks
            parent = random.choice(list(track_groups.keys()))
            subtracks = track_groups[parent]

            if subtracks and random.random() < 0.7:
                # 70%: book one or more subtracks
                k = random.randint(1, min(len(subtracks), 2))
                track_assets = random.sample(subtracks, k)
            else:
                # 30%: book the whole parent track
                track_assets = [parent]

            # Pick start time
            start_hour = random.choices(
                list(HOUR_WEIGHTS.keys()),
                weights=list(HOUR_WEIGHTS.values()), k=1,
            )[0]
            start_minute = random.choice([0, 15, 30, 45])
            end_hour = start_hour + int(duration_h)
            end_minute = start_minute + int((duration_h % 1) * 60)
            if end_minute >= 60:
                end_hour += 1
                end_minute -= 60

            slot = (start_hour + start_minute / 60, end_hour + end_minute / 60)

            # Check conflicts: the booked assets + their conflicting assets
            conflict_ids = set()
            for a in track_assets:
                conflict_ids |= a.conflicting_asset_ids()

            has_conflict = False
            for aid in conflict_ids:
                for (bs, be) in busy.get(aid, []):
                    if slot[0] < be and slot[1] > bs:
                        has_conflict = True
                        break
                if has_conflict:
                    break

            if has_conflict:
                continue

            # Reserve the slot for all conflicting assets
            for aid in conflict_ids:
                busy.setdefault(aid, []).append(slot)

            # Build asset list
            event_assets = list(track_assets)
            if needs_vehicle and vehicles:
                event_assets.append(random.choice(vehicles))

            # Create event
            local_tz = get_current_timezone()
            start_dt = datetime(
                date.year, date.month, date.day,
                start_hour, start_minute, tzinfo=local_tz,
            )
            end_dt = datetime(
                date.year, date.month, date.day,
                end_hour, end_minute, tzinfo=local_tz,
            )

            user = random.choice(users)
            is_past = date < timezone.now().date()
            is_today = date == timezone.now().date()

            if is_past:
                is_approved = True
            elif is_today:
                is_approved = random.random() < 0.85
            else:
                is_approved = random.random() < 0.7

            event = Event.objects.create(
                title=title,
                description=desc,
                start_time=start_dt,
                end_time=end_dt,
                created_by=user,
                is_approved=is_approved,
            )
            event.assets.set(event_assets)

            # Actual timestamps for past/in-progress events
            if is_past and is_approved:
                self._stamp(event, start_dt, end_dt)
            elif is_today and is_approved and random.random() < 0.4:
                self._stamp(event, start_dt, end_dt, partial=True)

            created += 1

        return created

    def _stamp(self, event, sched_start, sched_end, partial=False):
        """Add realistic actual start/end timestamps."""
        offset = max(-15, min(15, random.gauss(0, 5)))
        event.actual_start = sched_start + timedelta(minutes=offset)

        if not partial:
            end_offset = max(-20, min(30, random.gauss(0, 7)))
            event.actual_end = sched_end + timedelta(minutes=end_offset)
            if event.actual_end <= event.actual_start:
                event.actual_end = event.actual_start + timedelta(minutes=30)

        event.save()
