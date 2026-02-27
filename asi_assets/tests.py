from django.test import TestCase
from .models import Track, Vehicle

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
