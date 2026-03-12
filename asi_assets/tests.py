from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Track, Vehicle

User = get_user_model()

class TrackModelTest(TestCase):
    def test_create_track(self):
        track = Track.objects.create(name="Test Track", description="A test track")
        self.assertEqual(track.name, "Test Track")
        self.assertEqual(track.description, "A test track")
        self.assertIsInstance(track, Track)

    def test_track_str(self):
        track = Track.objects.create(name="Track A", description="A sample track")
        self.assertEqual(str(track), 'Track A')

class VehicleModelTest(TestCase):
    def test_create_vehicle(self):
        vehicle = Vehicle.objects.create(name="Vehicle X", description="A fast vehicle")
        self.assertEqual(vehicle.name, "Vehicle X")
        self.assertEqual(vehicle.description, "A fast vehicle")
        self.assertIsInstance(vehicle, Vehicle)

    def test_vehicle_str(self):
        vehicle = Vehicle.objects.create(name="Vehicle Y", description="A slow vehicle")
        self.assertEqual(str(vehicle), 'Vehicle Y')


class AssetAccessTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.track = Track.objects.create(name='Track A', description='A track')
        self.vehicle = Vehicle.objects.create(name='Vehicle A', description='A vehicle')

    def test_index_requires_login(self):
        response = self.client.get(reverse('asi_assets:index'))
        self.assertRedirects(response, '/users/login/?next=/assets/')

    def test_track_detail_requires_login(self):
        response = self.client.get(reverse('asi_assets:track_detail', args=[self.track.pk]))
        self.assertRedirects(response, f'/users/login/?next=/assets/track/{self.track.pk}/')

    def test_vehicle_detail_requires_login(self):
        response = self.client.get(reverse('asi_assets:vehicle_detail', args=[self.vehicle.pk]))
        self.assertRedirects(response, f'/users/login/?next=/assets/vehicle/{self.vehicle.pk}/')

    def test_index_accessible_when_logged_in(self):
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('asi_assets:index'))
        self.assertEqual(response.status_code, 200)

    def test_track_detail_accessible_when_logged_in(self):
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('asi_assets:track_detail', args=[self.track.pk]))
        self.assertEqual(response.status_code, 200)

    def test_vehicle_detail_accessible_when_logged_in(self):
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('asi_assets:vehicle_detail', args=[self.vehicle.pk]))
        self.assertEqual(response.status_code, 200)


# ── P1 Fix 4: .get() → get_object_or_404 ─────────────────────────────────────

class AssetNotFoundTest(TestCase):
    """Fix 4: non-existent Track/Vehicle PKs must return 404, not 500."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.login(username='employee', password='Testpass123!')

    def test_nonexistent_track_returns_404(self):
        """GET /assets/track/<nonexistent-pk>/ must return 404."""
        nonexistent_pk = 99999
        response = self.client.get(
            reverse('asi_assets:track_detail', args=[nonexistent_pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_vehicle_returns_404(self):
        """GET /assets/vehicle/<nonexistent-pk>/ must return 404."""
        nonexistent_pk = 99999
        response = self.client.get(
            reverse('asi_assets:vehicle_detail', args=[nonexistent_pk])
        )
        self.assertEqual(response.status_code, 404)
