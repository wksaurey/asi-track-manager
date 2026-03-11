from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from asi_assets.models import Track, Vehicle
from .forms import ReservationForm
from .models import Reservation

User = get_user_model()


class ReservationModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass1234!')
        self.track = Track.objects.create(name='Track A')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def test_create_reservation(self):
        r = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        r.tracks.add(self.track)
        self.assertEqual(r.user, self.user)
        self.assertIn(self.track, r.tracks.all())

    def test_str(self):
        r = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        self.assertIn('testuser', str(r))

    def test_clean_rejects_short_reservation(self):
        from django.core.exceptions import ValidationError
        r = Reservation(user=self.user, start_time=self.start, end_time=self.start + timedelta(minutes=30))
        with self.assertRaises(ValidationError):
            r.clean()

    def test_clean_rejects_end_before_start(self):
        from django.core.exceptions import ValidationError
        r = Reservation(user=self.user, start_time=self.start, end_time=self.start - timedelta(hours=1))
        with self.assertRaises(ValidationError):
            r.clean()


class ReservationFormTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass1234!')
        self.track = Track.objects.create(name='Track A')
        self.vehicle = Vehicle.objects.create(name='Vehicle 1')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def test_valid_form_with_track(self):
        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_requires_track_or_vehicle(self):
        form = ReservationForm(data={
            'tracks': [],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())

    def test_form_rejects_short_duration(self):
        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': (self.start + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())

    def test_double_booking_rejected(self):
        # Create an existing reservation
        existing = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        existing.tracks.add(self.track)

        # Try to book overlapping time on the same track
        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': (self.start + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (self.end + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())
