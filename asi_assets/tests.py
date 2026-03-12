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
		self.assertTrue(str(track))

class VehicleModelTest(TestCase):
	def test_create_vehicle(self):
		vehicle = Vehicle.objects.create(name="Vehicle X", description="A fast vehicle")
		self.assertEqual(vehicle.name, "Vehicle X")
		self.assertEqual(vehicle.description, "A fast vehicle")
		self.assertIsInstance(vehicle, Vehicle)

	def test_vehicle_str(self):
		vehicle = Vehicle.objects.create(name="Vehicle Y", description="A slow vehicle")
		self.assertTrue(str(vehicle))


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
