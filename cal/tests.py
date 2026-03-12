from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Asset, Event
from .forms import EventForm

User = get_user_model()


class CalAccessTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')

    def test_index_requires_login(self):
        response = self.client.get(reverse('cal:index'))
        self.assertRedirects(response, '/users/login/?next=/cal/')

    def test_calendar_requires_login(self):
        response = self.client.get(reverse('cal:calendar'))
        self.assertRedirects(response, '/users/login/?next=/cal/calendar/')

    def test_index_redirects_to_calendar_when_logged_in(self):
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:index'))
        self.assertRedirects(response, '/cal/calendar/')

    def test_calendar_accessible_when_logged_in(self):
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertEqual(response.status_code, 200)


# ── P1 Fix 1 & P2 Fix 10: Event model default ─────────────────────────────────

class EventModelDefaultTest(TestCase):
    """Fix 1: Event.is_approved must default to False."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def test_event_model_default_is_not_approved(self):
        """New Event created via ORM without setting is_approved must be False."""
        event = Event.objects.create(
            title='Test Event',
            description='desc',
            start_time=self.start,
            end_time=self.end,
            created_by=self.user,
        )
        self.assertFalse(event.is_approved)

    def test_event_str(self):
        """Event.__str__ should return the event title.
        NOTE: This test will FAIL until Event.__str__ is added to the model.
        """
        event = Event.objects.create(
            title='My Event Title',
            description='desc',
            start_time=self.start,
            end_time=self.end,
            created_by=self.user,
        )
        self.assertEqual(str(event), 'My Event Title')


# ── P1 Fix 2 & P2 Fix 10: event_approve view requires POST ────────────────────

class EventApproveViewTest(TestCase):
    """Fix 2: event_approve must reject GET with 405 and approve on POST (staff only)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.event = Event.objects.create(
            title='Pending Event',
            description='desc',
            start_time=self.start,
            end_time=self.end,
            created_by=self.regular,
            is_approved=False,
        )

    def test_event_approve_get_returns_405(self):
        """GET to event_approve must return 405 Method Not Allowed."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_event_approve_post_approves(self):
        """Staff POST to event_approve must set is_approved=True and redirect."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.post(url)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_approved)
        self.assertEqual(response.status_code, 302)

    def test_event_approve_post_non_staff_redirected(self):
        """Non-staff POST to event_approve is redirected (not 405 — staff check
        runs inside the view after the POST-only gate)."""
        self.client.login(username='employee', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_approved)


# ── P1 Fix 5 & P2 Fix 10: EventForm 1-hour minimum duration ──────────────────

class EventFormDurationTest(TestCase):
    """Fix 5: EventForm.clean() must enforce a 1-hour minimum duration."""

    def setUp(self):
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)

    def _form_data(self, duration_minutes):
        end = self.start + timedelta(minutes=duration_minutes)
        return {
            'title': 'Test',
            'description': 'desc',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [],
        }

    def test_event_form_30_minutes_is_invalid(self):
        """Duration of 30 minutes must fail validation."""
        form = EventForm(data=self._form_data(30))
        self.assertFalse(form.is_valid())

    def test_event_form_exactly_1_hour_is_valid(self):
        """Duration of exactly 60 minutes must pass validation."""
        form = EventForm(data=self._form_data(60))
        self.assertTrue(form.is_valid(), form.errors)

    def test_event_form_2_hours_is_valid(self):
        """Duration of 120 minutes must pass validation."""
        form = EventForm(data=self._form_data(120))
        self.assertTrue(form.is_valid(), form.errors)


# ── P1 Fix 6: Root URL redirect ───────────────────────────────────────────────

class RootUrlRedirectTest(TestCase):
    """Fix 6: GET '/' should redirect unauthenticated users to login, and
    authenticated users should ultimately reach the calendar view."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')

    def test_root_unauthenticated_redirects_to_login(self):
        """Unauthenticated GET / must end up at the login page (via redirect chain)."""
        response = self.client.get('/', follow=True)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else ''
        self.assertIn('/users/login/', final_url)

    def test_root_authenticated_reaches_calendar(self):
        """Authenticated GET / must follow redirects and land on the calendar (200)."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get('/', follow=True)
        self.assertEqual(response.status_code, 200)
        # The final URL must be the calendar
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else ''
        self.assertIn('/cal/calendar/', final_url)


# ── P2 Fix 10: Additional cal app coverage ────────────────────────────────────

class PendingEventsAdminOnlyTest(TestCase):
    """Non-staff users must be redirected away from the pending events page."""

    def setUp(self):
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )

    def test_pending_events_admin_only(self):
        """Non-staff GET to cal:pending_events is redirected."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:pending_events'))
        self.assertEqual(response.status_code, 302)

    def test_pending_events_accessible_to_staff(self):
        """Staff GET to cal:pending_events returns 200."""
        self.client.login(username='admin', password='Testpass123!')
        response = self.client.get(reverse('cal:pending_events'))
        self.assertEqual(response.status_code, 200)


class EventEditOwnershipTest(TestCase):
    """Regular users must not be able to edit another user's event."""

    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='Testpass123!')
        self.other = User.objects.create_user(username='other', password='Testpass123!')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.event = Event.objects.create(
            title='Owner Event',
            description='desc',
            start_time=self.start,
            end_time=self.end,
            created_by=self.owner,
            is_approved=True,
        )

    def test_event_edit_ownership(self):
        """Regular user cannot edit another user's event — must be redirected."""
        self.client.login(username='other', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_event_edit_owner_can_edit(self):
        """Event owner can access the edit view (200)."""
        self.client.login(username='owner', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class AssetListLoginRequiredTest(TestCase):
    """cal:asset_list requires authentication."""

    def test_asset_list_requires_login(self):
        """Unauthenticated GET to cal:asset_list must redirect to login."""
        response = self.client.get(reverse('cal:asset_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response['Location'])


class AssetCreateAdminOnlyTest(TestCase):
    """cal:asset_create is restricted to staff users."""

    def setUp(self):
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')

    def test_asset_create_admin_only(self):
        """Non-staff GET to cal:asset_create must be redirected."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_create'))
        self.assertEqual(response.status_code, 302)


class AssetToggleRequiresPostTest(TestCase):
    """cal:asset_toggle must reject GET with 405."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.asset = Asset.objects.create(
            name='Test Track', asset_type=Asset.AssetType.TRACK
        )

    def test_asset_toggle_requires_post(self):
        """GET to cal:asset_toggle must return 405 Method Not Allowed."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:asset_toggle', args=[self.asset.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
