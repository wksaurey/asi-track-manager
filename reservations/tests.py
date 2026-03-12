from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
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

    def test_valid_form_with_vehicle(self):
        form = ReservationForm(data={
            'tracks': [],
            'vehicles': [self.vehicle.pk],
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

    def test_form_rejects_end_before_start(self):
        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': (self.start - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())

    def test_double_booking_track_rejected(self):
        existing = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        existing.tracks.add(self.track)

        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': (self.start + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (self.end + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())

    def test_double_booking_vehicle_rejected(self):
        existing = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        existing.vehicles.add(self.vehicle)

        form = ReservationForm(data={
            'tracks': [],
            'vehicles': [self.vehicle.pk],
            'start_time': (self.start + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'),
            'end_time': (self.end + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())

    def test_non_overlapping_booking_allowed(self):
        existing = Reservation.objects.create(user=self.user, start_time=self.start, end_time=self.end)
        existing.tracks.add(self.track)

        after_end = self.end + timedelta(hours=1)
        form = ReservationForm(data={
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': after_end.strftime('%Y-%m-%dT%H:%M'),
            'end_time': (after_end + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertTrue(form.is_valid(), form.errors)


class ReservationAccessTest(TestCase):
    """Tests that unauthenticated users are redirected to login."""

    def test_list_requires_login(self):
        response = self.client.get(reverse('reservations:reservation_list'))
        self.assertRedirects(response, '/users/login/?next=/reservations/')

    def test_create_requires_login(self):
        response = self.client.get(reverse('reservations:reservation_create'))
        self.assertRedirects(response, '/users/login/?next=/reservations/new/')

    def test_detail_requires_login(self):
        user = User.objects.create_user(username='owner', password='Testpass123!')
        start = timezone.now() + timedelta(days=1)
        r = Reservation.objects.create(user=user, start_time=start, end_time=start + timedelta(hours=2))
        response = self.client.get(reverse('reservations:reservation_detail', args=[r.pk]))
        self.assertRedirects(response, f'/users/login/?next=/reservations/{r.pk}/')

    def test_delete_requires_login(self):
        user = User.objects.create_user(username='owner', password='Testpass123!')
        start = timezone.now() + timedelta(days=1)
        r = Reservation.objects.create(user=user, start_time=start, end_time=start + timedelta(hours=2))
        response = self.client.get(reverse('reservations:reservation_delete', args=[r.pk]))
        self.assertRedirects(response, f'/users/login/?next=/reservations/{r.pk}/delete/')


class ReservationViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Testpass123!')
        self.other_user = User.objects.create_user(username='otheruser', password='Testpass123!')
        self.track = Track.objects.create(name='Track A')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.client.login(username='testuser', password='Testpass123!')

    def _make_reservation(self, user=None):
        user = user or self.user
        r = Reservation.objects.create(user=user, start_time=self.start, end_time=self.end)
        r.tracks.add(self.track)
        return r

    def test_list_shows_own_reservations(self):
        r = self._make_reservation()
        response = self.client.get(reverse('reservations:reservation_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(r, response.context['reservations'])

    def test_list_hides_other_users_reservations(self):
        other_r = self._make_reservation(user=self.other_user)
        response = self.client.get(reverse('reservations:reservation_list'))
        self.assertNotIn(other_r, response.context['reservations'])

    def test_create_get(self):
        response = self.client.get(reverse('reservations:reservation_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reservations/reservation_form.html')

    def test_create_post_valid(self):
        response = self.client.post(reverse('reservations:reservation_create'), {
            'tracks': [self.track.pk],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertRedirects(response, reverse('reservations:reservation_list'))
        self.assertTrue(Reservation.objects.filter(user=self.user).exists())

    def test_create_post_invalid(self):
        response = self.client.post(reverse('reservations:reservation_create'), {
            'tracks': [],
            'vehicles': [],
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Reservation.objects.filter(user=self.user).exists())

    def test_detail_own_reservation(self):
        r = self._make_reservation()
        response = self.client.get(reverse('reservations:reservation_detail', args=[r.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reservations/reservation_detail.html')

    def test_detail_other_users_reservation_is_visible(self):
        other_r = self._make_reservation(user=self.other_user)
        response = self.client.get(reverse('reservations:reservation_detail', args=[other_r.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_own_reservation(self):
        r = self._make_reservation()
        response = self.client.post(reverse('reservations:reservation_delete', args=[r.pk]))
        self.assertRedirects(response, reverse('reservations:reservation_list'))
        self.assertFalse(Reservation.objects.filter(pk=r.pk).exists())

    def test_delete_other_users_reservation_returns_404(self):
        other_r = self._make_reservation(user=self.other_user)
        response = self.client.post(reverse('reservations:reservation_delete', args=[other_r.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Reservation.objects.filter(pk=other_r.pk).exists())
