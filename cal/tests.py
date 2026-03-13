import os
from datetime import datetime, timedelta, timezone as dt_timezone

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
        self.asset = Asset.objects.create(
            name='Test Track', asset_type=Asset.AssetType.TRACK
        )

    def _form_data(self, duration_minutes):
        end = self.start + timedelta(minutes=duration_minutes)
        return {
            'title': 'Test',
            'description': 'desc',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
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



class EventFormAssetRequiredTest(TestCase):
    """EventForm must require at least one asset to be selected."""

    def setUp(self):
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def test_no_assets_is_invalid(self):
        """Submitting EventForm with no assets selected must fail validation."""
        form = EventForm(data={
            'title': 'Test Event',
            'description': 'desc',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [],
        })
        self.assertFalse(form.is_valid())
        self.assertIn(
            'At least one asset (track, vehicle, or operator) must be selected.',
            form.errors.get('assets', []),
        )


# ── UI Redesign: global base.html + nav gating ────────────────────────────────

class GlobalBaseTemplateTest(TestCase):
    """The project-wide base.html must be discoverable and used by cal pages.

    These tests are RED before implementation (base.html does not exist yet,
    DIRS is not configured, and context processor is not registered).
    """

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )

    def test_calendar_page_uses_global_base(self):
        """Calendar page must be rendered via the project-wide base.html,
        and cal/base.html must no longer be used (it is deleted in the redesign).

        RED until: templates/base.html is created, DIRS includes BASE_DIR/'templates',
        and cal/base.html is deleted with cal templates extending base.html directly.
        """
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base.html')
        self.assertTemplateNotUsed(response, 'cal/base.html')

    def test_pending_count_in_calendar_context(self):
        """Calendar response context must include pending_count (from context processor).

        RED until: cal/context_processors.py is created and registered in settings.py.
        """
        self.client.login(username='admin', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertIn('pending_count', response.context)

    def test_authenticated_user_sees_calendar_nav_link(self):
        """Authenticated users must see a 'Calendar' nav link on the calendar page.

        RED until: base.html is created with nav links gated by is_authenticated.
        """
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertContains(response, 'Calendar')

    def test_authenticated_user_sees_assets_nav_link(self):
        """Authenticated users must see an 'Assets' nav link on the calendar page.

        RED until: base.html is created with nav links gated by is_authenticated.
        """
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertContains(response, 'Assets')

    def test_staff_sees_pending_nav_link(self):
        """Staff users must see a 'Pending' nav link on the calendar page.

        RED until: base.html is created with the staff-gated Pending link.
        """
        self.client.login(username='admin', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertContains(response, 'Pending')

    def test_non_staff_does_not_see_pending_nav_link(self):
        """Non-staff users must NOT see the 'Pending' nav link.

        RED until: base.html gates the Pending link with {% if request.user.is_staff %}.
        Note: currently cal/base.html already gates this correctly, but this test
        also ensures the global base.html continues to enforce it after promotion.
        """
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertNotContains(response, 'Pending Events')


class LoginPageNavTest(TestCase):
    """Login and register pages must use global base.html but show no authenticated nav.

    These tests are RED before implementation because users/login.html and
    users/register.html are currently standalone HTML (not extending base.html).
    """

    def test_login_page_uses_global_base(self):
        """Login page must render via the project-wide base.html.

        RED until: users/login.html is rewritten to extend 'base.html' and
        BASE_DIR/'templates' is in DIRS.
        """
        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base.html')

    def test_register_page_uses_global_base(self):
        """Register page must render via the project-wide base.html.

        RED until: users/register.html is rewritten to extend 'base.html'.
        """
        response = self.client.get(reverse('users:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base.html')

    def test_login_page_contains_brand(self):
        """Login page must show the site brand ('ASI Track Manager') from base.html.

        RED until: users/login.html extends base.html which includes the brand.
        """
        response = self.client.get(reverse('users:login'))
        self.assertContains(response, 'ASI Track Manager')

    def test_register_page_contains_brand(self):
        """Register page must show the site brand ('ASI Track Manager') from base.html.

        RED until: users/register.html extends base.html which includes the brand.
        """
        response = self.client.get(reverse('users:register'))
        self.assertContains(response, 'ASI Track Manager')

    def test_login_page_has_no_authenticated_nav_links(self):
        """Login page (unauthenticated) must NOT show any authenticated nav links.

        All nav links (Calendar, Assets, New Event, Pending) are inside
        {% if request.user.is_authenticated %} in base.html, so the login page
        must show brand only.
        RED until: base.html gates all nav links with is_authenticated.
        """
        response = self.client.get(reverse('users:login'))
        self.assertNotContains(response, 'New Event')
        self.assertNotContains(response, '>Calendar<')
        self.assertNotContains(response, '>Assets<')
        self.assertNotContains(response, '>Pending<')

    def test_register_page_has_no_authenticated_nav_links(self):
        """Register page (unauthenticated) must NOT show any authenticated nav links.

        RED until: base.html gates all nav links with is_authenticated.
        """
        response = self.client.get(reverse('users:register'))
        self.assertNotContains(response, 'New Event')
        self.assertNotContains(response, '>Calendar<')
        self.assertNotContains(response, '>Assets<')
        self.assertNotContains(response, '>Pending<')


# ── Bug fix tests ─────────────────────────────────────────────────────────────

class AssetListStaffLinkTest(TestCase):
    """Bug 1: 'New Asset' link in asset_list.html must only appear for staff."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')

    def test_staff_sees_new_asset_link(self):
        """Staff user must see the 'New Asset' link in the asset list."""
        self.client.login(username='admin', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('cal:asset_create'))

    def test_non_staff_does_not_see_new_asset_link(self):
        """Non-staff user must NOT see the asset create URL in the asset list."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('cal:asset_create'))


class EventFormDefaultDateTest(TestCase):
    """Bug 2: GET /cal/event/new/ response must contain 'defaultDate' in the JS."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')

    def test_event_new_renders_successfully(self):
        """GET /cal/event/new/ must return 200."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:event_new'))
        self.assertEqual(response.status_code, 200)

    def test_event_new_contains_default_date_js(self):
        """Response for GET /cal/event/new/ must include 'defaultDate' in the page source."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:event_new'))
        self.assertContains(response, 'defaultDate')


class DarkModeCSSTest(TestCase):
    """Bug 3: The CSS file must contain dark-theme overrides targeting .card."""

    def test_css_contains_dark_theme_card_overrides(self):
        """styles.css must have html.dark-theme rules targeting .card."""
        from django.conf import settings
        css_path = os.path.join(
            settings.BASE_DIR, 'cal', 'static', 'cal', 'css', 'styles.css'
        )
        with open(css_path, 'r') as f:
            css_content = f.read()
        self.assertIn('dark-theme', css_content)
        self.assertIn('.card', css_content)
        # Ensure there is a combined dark-theme + .card rule
        self.assertIn('html.dark-theme .card', css_content)


# ── Asset delete and grouped list ─────────────────────────────────────────────

class AssetDeleteStaffOnlyTest(TestCase):
    """cal:asset_delete must block non-staff users."""

    def setUp(self):
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')
        self.asset = Asset.objects.create(
            name='Track A', asset_type=Asset.AssetType.TRACK
        )

    def test_non_staff_post_is_blocked(self):
        """Non-staff POST to cal:asset_delete must redirect and NOT delete the asset."""
        self.client.login(username='employee', password='Testpass123!')
        url = reverse('cal:asset_delete', args=[self.asset.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())


class AssetDeleteRequiresPostTest(TestCase):
    """cal:asset_delete must require POST; GET must not delete the asset."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.asset = Asset.objects.create(
            name='Track B', asset_type=Asset.AssetType.TRACK
        )

    def test_staff_get_does_not_delete(self):
        """Staff GET to cal:asset_delete must not delete the asset."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:asset_delete', args=[self.asset.pk])
        self.client.get(url)
        self.assertTrue(Asset.objects.filter(pk=self.asset.pk).exists())

    def test_staff_post_deletes_and_redirects(self):
        """Staff POST to cal:asset_delete must delete the asset and redirect to cal:asset_list."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:asset_delete', args=[self.asset.pk])
        response = self.client.post(url)
        self.assertFalse(Asset.objects.filter(pk=self.asset.pk).exists())
        self.assertRedirects(response, reverse('cal:asset_list'))


class AssetListGroupedTest(TestCase):
    """GET cal:asset_list must pass grouped_assets in context, grouped by type."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        Asset.objects.create(name='Track Alpha', asset_type=Asset.AssetType.TRACK)
        Asset.objects.create(name='Vehicle One', asset_type=Asset.AssetType.VEHICLE)
        Asset.objects.create(name='Track Beta', asset_type=Asset.AssetType.TRACK)

    def test_grouped_assets_in_context(self):
        """Response context must include grouped_assets."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        self.assertIn('grouped_assets', response.context)

    def test_grouped_assets_is_list_of_3_tuples(self):
        """grouped_assets must be a list/sequence of (type_label, type_value, group) 3-tuples."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        grouped = response.context['grouped_assets']
        self.assertTrue(len(grouped) > 0)
        for item in grouped:
            self.assertEqual(len(item), 3, "Each group must be a 3-tuple of (type_label, type_value, assets)")

    def test_track_assets_grouped_together(self):
        """Both Track assets must appear in the same group."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        grouped = response.context['grouped_assets']
        track_group = next(
            (assets for label, type_val, assets in grouped if 'Track' in label or 'track' in label.lower()),
            None,
        )
        self.assertIsNotNone(track_group, "Expected a group for Track assets")
        names = [a.name for a in track_group]
        self.assertIn('Track Alpha', names)
        self.assertIn('Track Beta', names)


# ── Calendar UX Features: Hover Overlays & Track View ─────────────────────────

class HoverOverlayMonthTest(TestCase):
    """Month view must render hover-overlay markup for adding events."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_month_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertEqual(response.status_code, 200)

    def test_month_view_contains_day_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertContains(response, 'day-add-overlay')

    def test_month_view_contains_day_cell_header(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertContains(response, 'day-cell-header')

    def test_month_view_date_is_span_not_anchor(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertContains(response, '<span class="date"')

    def test_month_view_date_is_not_anchor(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertNotContains(response, '<a class="date"')


class HoverOverlayWeekTest(TestCase):
    """Week view must render hover-overlay markup in headers and body cells."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_week_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertEqual(response.status_code, 200)

    def test_week_view_contains_day_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'day-add-overlay')

    def test_week_view_contains_wk_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'wk-add-overlay')

    def test_week_view_contains_wk_body_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'wk-body-add-overlay')

    def test_week_view_contains_wk_th_inner(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'wk-th-inner')


class TrackViewRenderTest(TestCase):
    """Track view must render with the track-view CSS class."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_track_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertEqual(response.status_code, 200)

    def test_track_view_contains_track_view_class(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertContains(response, 'track-view')


class TrackViewContainsTracksTest(TestCase):
    """Track view must show track assets and hide non-track assets."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        Asset.objects.create(name='North Loop', asset_type='track')
        Asset.objects.create(name='South Loop', asset_type='track')
        Asset.objects.create(name='Test Vehicle', asset_type='vehicle')

    def test_track_view_shows_north_loop(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'North Loop')

    def test_track_view_shows_south_loop(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertContains(response, 'South Loop')

    def test_track_view_hides_vehicle(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertNotContains(response, 'Test Vehicle')


class TrackViewEmptyTracksTest(TestCase):
    """Track view with no track assets must show an empty-state message."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_track_view_shows_empty_message(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No tracks configured')


class TrackViewEventAssignmentTest(TestCase):
    """Events assigned to a track asset must appear in the track view for that week."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(name='Test Track', asset_type='track')
        # Monday 2026-03-09 10:00 UTC
        start = datetime(2026, 3, 9, 10, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 3, 9, 12, 0, tzinfo=dt_timezone.utc)
        event = Event.objects.create(
            title='Sprint Test',
            description='desc',
            start_time=start,
            end_time=end,
            created_by=self.user,
            is_approved=True,
        )
        event.assets.add(self.track)

    def test_track_view_shows_event_title(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track&date=2026-3-9')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sprint Test')


class TrackViewTabVisibleTest(TestCase):
    """The Track tab link must appear in calendar views."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_month_view_has_track_tab(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '?view=track')


class TrackViewNavTest(TestCase):
    """Track view navigation must link to prev/next week."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_track_view_nav_contains_view_param(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track&date=2026-3-9')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'view=track')

    def test_track_view_nav_prev_date(self):
        """Prev navigation link must reference the date 7 days earlier: 2026-3-2."""
        response = self.client.get(reverse('cal:calendar') + '?view=track&date=2026-3-9')
        self.assertContains(response, '2026-3-2')

    def test_track_view_nav_next_date(self):
        """Next navigation link must reference the date 7 days later: 2026-3-16."""
        response = self.client.get(reverse('cal:calendar') + '?view=track&date=2026-3-9')
        self.assertContains(response, '2026-3-16')


class AssetFilterHiddenInTrackViewTest(TestCase):
    """The asset filter form must not appear in the track view."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_asset_filter_form_not_in_track_view(self):
        response = self.client.get(reverse('cal:calendar') + '?view=track')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'asset-filter-form')
