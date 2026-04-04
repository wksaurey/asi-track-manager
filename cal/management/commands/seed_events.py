"""
Management command to seed the database with realistic sample events.

Usage:
    python manage.py seed_events          # Default: 90 days of data
    python manage.py seed_events --days 30
    python manage.py seed_events --clear   # Wipe existing events first
"""

import random
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.timezone import get_current_timezone

from cal.models import Asset, Event
from users.models import User


# ── Realistic event templates ────────────────────────────────────────────────
# (title, description, duration_hours, frequency_weight)
# Higher weight = more likely to appear

EVENT_TEMPLATES = [
    # Autonomous vehicle testing
    ("AV Navigation Test", "Autonomous navigation system validation run", 2, 5),
    ("Obstacle Avoidance Trial", "Testing obstacle detection and avoidance at various speeds", 1.5, 4),
    ("Sensor Calibration", "LiDAR and camera sensor calibration and verification", 1, 6),
    ("GPS RTK Accuracy Test", "High-precision GPS testing across track waypoints", 1.5, 3),
    ("Emergency Stop Validation", "E-stop system testing under multiple scenarios", 1, 4),
    ("Path Planning Benchmark", "Evaluating new path planning algorithm performance", 2, 3),
    ("Speed Controller Tuning", "PID tuning for speed control module", 1.5, 3),
    ("Multi-Vehicle Coordination", "Testing fleet coordination and collision avoidance", 3, 2),
    ("Night Operations Test", "Sensor and navigation testing in low-light conditions", 2, 1),
    ("Weather Resilience Test", "System behavior validation in adverse weather simulation", 2, 1),

    # Vehicle maintenance & prep
    ("Vehicle Inspection", "Pre-test vehicle inspection and systems check", 1, 6),
    ("Battery Swap & Charge", "Replace and charge vehicle battery packs", 1, 4),
    ("Tire Pressure Check", "Check and adjust tire pressure for all test vehicles", 1, 3),
    ("Firmware Update", "Flash updated firmware to vehicle control unit", 1.5, 2),
    ("Hydraulic System Check", "Inspect hydraulic lines and fluid levels", 1, 2),

    # Track maintenance
    ("Track Grading", "Grade and level dirt track surface", 2, 2),
    ("Cone Setup - Slalom Course", "Set up slalom obstacle course with traffic cones", 1, 3),
    ("Track Marker Refresh", "Repaint lane markers and boundary lines", 2, 1),
    ("Debris Cleanup", "Clear debris and obstacles from track surface", 1, 2),

    # Data collection & demos
    ("Data Collection Run", "Structured data collection for ML training dataset", 3, 4),
    ("Client Demo - Track Tour", "Live demonstration for prospective client", 2, 3),
    ("Investor Demo", "Executive demonstration for investor group", 2, 1),
    ("Video Capture Session", "Record footage for marketing and documentation", 2, 2),
    ("Mapping Run", "HD map generation run for track digitization", 2, 2),

    # Team activities
    ("Safety Briefing", "Weekly team safety briefing and protocol review", 1, 3),
    ("New Operator Training", "Onboarding training for new vehicle operators", 3, 2),
    ("Engineering Review", "On-track engineering review and troubleshooting", 2, 3),
    ("R&D Experiment", "Research experiment - new actuator testing", 2, 2),
    ("Endurance Test", "Extended duration reliability and endurance run", 4, 1),
    ("Payload Capacity Test", "Test vehicle performance under various load conditions", 2, 2),
]

# Team member names for created_by variety
TEAM_MEMBERS = [
    "admin",
    "hollis",
    "kolter",
    "sarah",
    "mike",
    "jessica",
    "david",
    "emma",
]

# Typical working hours distribution (hour: relative_weight)
HOUR_WEIGHTS = {
    6: 1, 7: 3, 8: 8, 9: 10, 10: 10, 11: 8,
    12: 4, 13: 8, 14: 10, 15: 9, 16: 6, 17: 3, 18: 1,
}


class Command(BaseCommand):
    help = "Seed the database with realistic sample events across all tracks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Number of days of data to generate (default: 90, centered on today)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing events before seeding",
        )
        parser.add_argument(
            "--events-per-day",
            type=int,
            default=0,
            help="Average events per day (0 = auto: 8-15 based on weekday)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        clear = options["clear"]
        epd = options["events_per_day"]

        # Ensure tracks exist
        tracks = list(Asset.objects.filter(asset_type=Asset.AssetType.TRACK))
        if not tracks:
            self.stderr.write(self.style.ERROR(
                "No tracks found! Run migrations first (seed_default_tracks)."
            ))
            return

        self.stdout.write(f"Found {len(tracks)} tracks: {', '.join(t.name for t in tracks)}")

        # Get or create users
        users = self._ensure_users()
        self.stdout.write(f"Using {len(users)} users for event assignment")

        if clear:
            count = Event.objects.count()
            Event.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing events"))

        # Generate events
        today = timezone.now().date()
        start_date = today - timedelta(days=days // 2)
        end_date = today + timedelta(days=days // 2)

        total_created = 0
        current = start_date

        while current <= end_date:
            weekday = current.weekday()  # 0=Mon, 6=Sun
            is_weekend = weekday >= 5

            # Determine how many events for this day
            if epd > 0:
                day_count = max(1, int(random.gauss(epd, 2)))
            elif is_weekend:
                day_count = random.randint(1, 4)  # Light weekend activity
            else:
                day_count = random.randint(6, 14)  # Busy weekdays

            created = self._generate_day_events(current, day_count, tracks, users)
            total_created += created
            current += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(
            f"\nCreated {total_created} events across {days} days "
            f"({start_date} to {end_date})"
        ))

        # Summary stats
        approved = Event.objects.filter(is_approved=True).count()
        pending = Event.objects.filter(is_approved=False).count()
        with_actual = Event.objects.filter(segments__isnull=False).distinct().count()
        self.stdout.write(f"  Approved: {approved}")
        self.stdout.write(f"  Pending:  {pending}")
        self.stdout.write(f"  With actual times: {with_actual}")

    def _ensure_users(self):
        """Get or create team member users."""
        users = []
        for username in TEAM_MEMBERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@asirobotics.com",
                    "is_staff": username == "admin",
                    "is_superuser": username == "admin",
                },
            )
            if created:
                user.set_password("testpass123")
                user.save()
                self.stdout.write(f"  Created user: {username}")
            users.append(user)
        return users

    def _generate_day_events(self, date, count, tracks, users):
        """Generate events for a single day, avoiding time conflicts per track."""
        created = 0
        # Track busy slots per track to avoid overlaps: {track_id: [(start_h, end_h), ...]}
        busy = {t.pk: [] for t in tracks}

        for _ in range(count):
            template = random.choices(
                EVENT_TEMPLATES,
                weights=[t[3] for t in EVENT_TEMPLATES],
                k=1,
            )[0]

            title, description, duration_h, _ = template
            track = random.choice(tracks)

            # Pick a start hour weighted toward business hours
            start_hour = random.choices(
                list(HOUR_WEIGHTS.keys()),
                weights=list(HOUR_WEIGHTS.values()),
                k=1,
            )[0]
            start_minute = random.choice([0, 15, 30, 45])

            end_hour = start_hour + int(duration_h)
            end_minute = start_minute + int((duration_h % 1) * 60)
            if end_minute >= 60:
                end_hour += 1
                end_minute -= 60

            # Check for conflicts on this track
            new_slot = (start_hour + start_minute / 60, end_hour + end_minute / 60)
            conflict = False
            for (bs, be) in busy[track.pk]:
                if new_slot[0] < be and new_slot[1] > bs:
                    conflict = True
                    break

            if conflict:
                continue  # Skip this one

            busy[track.pk].append(new_slot)

            # Create timezone-aware datetimes
            local_tz = get_current_timezone()
            start_dt = datetime(date.year, date.month, date.day, start_hour, start_minute, tzinfo=local_tz)
            end_dt = datetime(date.year, date.month, date.day, end_hour, end_minute, tzinfo=local_tz)

            user = random.choice(users)
            is_past = date < timezone.now().date()
            is_today = date == timezone.now().date()

            # Approval: most events approved, some pending for future dates
            if is_past:
                is_approved = True  # Past events always approved
            elif is_today:
                is_approved = random.random() < 0.9  # 90% approved today
            else:
                is_approved = random.random() < 0.75  # 75% approved future

            event = Event.objects.create(
                title=title,
                description=description,
                start_time=start_dt,
                end_time=end_dt,
                created_by=user,
                is_approved=is_approved,
            )
            event.assets.add(track)

            # Add actual times for past events (simulating real usage)
            if is_past and is_approved:
                self._add_actual_times(event, start_dt, end_dt)
            elif is_today and is_approved and random.random() < 0.4:
                # Some of today's events have already started
                self._add_actual_times(event, start_dt, end_dt, partial=True)

            created += 1

        return created

    def _add_actual_times(self, event, sched_start, sched_end, partial=False):
        """
        Add realistic actual start/end times as segments.
        Adds slight variance from scheduled times to simulate real-world conditions.
        """
        from cal.models import ActualTimeSegment
        # Actual start: usually within ±15 min of scheduled
        offset_min = random.gauss(0, 5)  # Normal distribution, stddev=5 min
        offset_min = max(-15, min(15, offset_min))  # Clamp
        actual_start = sched_start + timedelta(minutes=offset_min)
        actual_end = None

        if not partial:
            # Actual end: usually within ±20 min of scheduled
            end_offset = random.gauss(0, 7)
            end_offset = max(-20, min(30, end_offset))  # Can run slightly over
            actual_end = sched_end + timedelta(minutes=end_offset)

            # Ensure actual_end > actual_start
            if actual_end <= actual_start:
                actual_end = actual_start + timedelta(minutes=30)

        ActualTimeSegment.objects.create(event=event, start=actual_start, end=actual_end)
