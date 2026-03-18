import json
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
    """Week view (now per-track chip grid) must render track-grid markup."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_week_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertEqual(response.status_code, 200)

    def test_week_view_does_not_contain_wk_body_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertNotContains(response, 'wk-body-add-overlay')

    def test_week_view_does_not_contain_day_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertNotContains(response, 'day-add-overlay')

    def test_week_view_does_not_contain_wk_add_overlay(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertNotContains(response, 'wk-add-overlay')

    def test_week_view_does_not_contain_wk_th_inner(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertNotContains(response, 'wk-th-inner')

    def test_week_view_contains_track_view_class(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'track-view')


class TrackViewRenderTest(TestCase):
    """Track view (now week) must render with the track-view CSS class."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_track_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertEqual(response.status_code, 200)

    def test_track_view_contains_track_view_class(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
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
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'North Loop')

    def test_track_view_shows_south_loop(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertContains(response, 'South Loop')

    def test_track_view_hides_vehicle(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertNotContains(response, 'Test Vehicle')


class TrackViewEmptyTracksTest(TestCase):
    """Track view with no track assets must show an empty-state message."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        # Remove tracks seeded by migration so we can test the empty state
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK).delete()

    def test_track_view_shows_empty_message(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
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
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-9')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sprint Test')


class TrackViewTabVisibleTest(TestCase):
    """The Track tab link must NOT appear in calendar views."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_month_view_has_no_track_tab(self):
        response = self.client.get(reverse('cal:calendar') + '?view=month')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '?view=track')


class TrackViewNavTest(TestCase):
    """Track view navigation must link to prev/next week."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_track_view_nav_contains_view_param(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-9')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'view=week')

    def test_track_view_nav_prev_date(self):
        """Prev navigation link must reference the date 7 days earlier: 2026-3-2."""
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-9')
        self.assertContains(response, '2026-3-2')

    def test_track_view_nav_next_date(self):
        """Next navigation link must reference the date 7 days later: 2026-3-16."""
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-9')
        self.assertContains(response, '2026-3-16')


class AssetFilterHiddenInTrackViewTest(TestCase):
    """The asset filter form must not appear in the track view."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)

    def test_asset_filter_form_not_in_track_view(self):
        response = self.client.get(reverse('cal:calendar') + '?view=week')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'asset-filter-form')


# ── Calendar UX: Gantt Day View ───────────────────────────────────────────────

class GanttDayViewTest(TestCase):
    """Day view (Gantt timeline) renders per-track horizontal blocks."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(name='North Loop', asset_type='track')

    def test_day_view_returns_200(self):
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertEqual(response.status_code, 200)

    def test_day_view_shows_gantt_view_class(self):
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'gantt-view')

    def test_day_view_no_tracks_shows_empty_message(self):
        Asset.objects.all().delete()
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'No tracks configured')

    def test_day_view_shows_track_name(self):
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'North Loop')

    def test_day_view_shows_event_in_gantt(self):
        start = datetime(2026, 3, 9, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 9, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Morning Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'Morning Test')
        self.assertContains(response, 'gantt-block')

    def test_day_view_event_position_in_html(self):
        """9am start = 180 min after 6am; 180/840*100 = 21.4286%."""
        start = datetime(2026, 3, 9, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 9, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Position Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'left:21.4286%')

    def test_day_view_event_outside_range_not_rendered(self):
        """Event entirely before 6am (4am-5am) must not produce a gantt-block."""
        start = datetime(2026, 3, 9, 4, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 9, 5, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Pre-Dawn Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertNotContains(response, 'Pre-Dawn Test')

    def test_day_view_asset_filter_hidden(self):
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertNotContains(response, 'asset-filter-form')

    def test_day_view_overlapping_events_use_multiple_sub_rows(self):
        """Two overlapping events on the same track appear in separate sub-rows."""
        start1 = datetime(2026, 3, 9, 9, 0, tzinfo=dt_timezone.utc)
        end1   = datetime(2026, 3, 9, 12, 0, tzinfo=dt_timezone.utc)
        start2 = datetime(2026, 3, 9, 10, 0, tzinfo=dt_timezone.utc)
        end2   = datetime(2026, 3, 9, 13, 0, tzinfo=dt_timezone.utc)
        for t, s, e in [('Event A', start1, end1), ('Event B', start2, end2)]:
            ev = Event.objects.create(
                title=t, description='', start_time=s, end_time=e,
                created_by=self.user, is_approved=True,
            )
            ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertGreaterEqual(response.content.decode().count('gantt-sub-row'), 2)


# ════════════════════════════════════════════════════════════════════════════════
# Subtrack tests
# ════════════════════════════════════════════════════════════════════════════════

class SubtrackModelTest(TestCase):
    """Tests for the parent FK on Asset (subtrack support)."""

    def test_subtrack_creation_and_parent_relationship(self):
        """A subtrack can be created with a parent track and the relationship is correct."""
        parent = Asset.objects.create(name='Test Main Track', asset_type=Asset.AssetType.TRACK)
        sub_north = Asset.objects.create(
            name='North', asset_type=Asset.AssetType.TRACK, parent=parent
        )
        sub_south = Asset.objects.create(
            name='South', asset_type=Asset.AssetType.TRACK, parent=parent
        )

        self.assertEqual(sub_north.parent, parent)
        self.assertEqual(sub_south.parent, parent)
        self.assertIsNone(parent.parent)

        subtracks = list(parent.subtracks.order_by('name'))
        self.assertIn(sub_north, subtracks)
        self.assertIn(sub_south, subtracks)
        self.assertEqual(len(subtracks), 2)

    def test_parent_track_has_no_parent(self):
        """A top-level parent track must have parent=None."""
        parent = Asset.objects.create(name='Top Track', asset_type=Asset.AssetType.TRACK)
        self.assertIsNone(parent.parent)

    def test_display_name_subtrack(self):
        """Subtrack display_name should be 'Parent – Subtrack'."""
        parent = Asset.objects.create(name='Test Main Track', asset_type=Asset.AssetType.TRACK)
        sub = Asset.objects.create(
            name='North', asset_type=Asset.AssetType.TRACK, parent=parent
        )
        self.assertEqual(sub.display_name, 'Test Main Track \u2013 North')

    def test_display_name_parent_with_subtracks(self):
        """Parent track display_name should be 'Name (whole)' when it has subtracks."""
        parent = Asset.objects.create(name='Test Main Track', asset_type=Asset.AssetType.TRACK)
        Asset.objects.create(name='North', asset_type=Asset.AssetType.TRACK, parent=parent)
        parent.refresh_from_db()
        self.assertEqual(parent.display_name, 'Test Main Track (whole)')

    def test_display_name_standalone_track(self):
        """A track with no subtracks and no parent should display just its name."""
        track = Asset.objects.create(name='Standalone', asset_type=Asset.AssetType.TRACK)
        self.assertEqual(track.display_name, 'Standalone')

    def test_subtrack_deleted_on_parent_delete(self):
        """Deleting a parent track also deletes its subtracks (CASCADE)."""
        parent = Asset.objects.create(name='Parent Track', asset_type=Asset.AssetType.TRACK)
        sub = Asset.objects.create(
            name='Sub Track', asset_type=Asset.AssetType.TRACK, parent=parent
        )
        parent.delete()
        self.assertFalse(Asset.objects.filter(pk=sub.pk).exists())


class SubtrackConflictDetectionTest(TestCase):
    """Tests for subtrack-aware conflict detection in EventForm."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.parent = Asset.objects.create(
            name='Test Main Track', asset_type=Asset.AssetType.TRACK
        )
        self.sub_north = Asset.objects.create(
            name='North', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_south = Asset.objects.create(
            name='South', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.start = datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc)
        self.end   = datetime(2026, 4, 1, 11, 0, tzinfo=dt_timezone.utc)

    def _make_event(self, asset, title='Existing Event'):
        ev = Event.objects.create(
            title=title,
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.user,
            is_approved=True,
        )
        ev.assets.add(asset)
        return ev

    def _form_data(self, asset, start=None, end=None):
        s = (start or self.start).strftime('%Y-%m-%dT%H:%M')
        e = (end or self.end).strftime('%Y-%m-%dT%H:%M')
        return {
            'title': 'New Event',
            'description': 'Test event description',
            'start_time': s,
            'end_time': e,
            'assets': [asset.pk],
        }

    def test_booking_subtrack_conflicts_with_existing_parent_booking(self):
        """Booking a subtrack must conflict if the parent track is already booked."""
        self._make_event(self.parent, 'Full Track Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertFalse(form.is_valid(), "Expected conflict with parent track booking")

    def test_booking_parent_conflicts_with_existing_subtrack_booking(self):
        """Booking the full (parent) track must conflict if any subtrack is already booked."""
        self._make_event(self.sub_north, 'North Sub Event')
        form = EventForm(data=self._form_data(self.parent))
        self.assertFalse(form.is_valid(), "Expected conflict with subtrack booking")

    def test_sibling_subtracks_do_not_conflict(self):
        """Booking North subtrack must NOT conflict with an existing South subtrack booking."""
        self._make_event(self.sub_south, 'South Sub Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertTrue(form.is_valid(), f"Sibling subtracks should not conflict. Errors: {form.errors}")

    def test_same_subtrack_conflicts_with_itself(self):
        """Booking a subtrack that is already booked at the same time must conflict."""
        self._make_event(self.sub_north, 'Existing North Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertFalse(form.is_valid(), "Expected conflict on same subtrack")

    def test_same_parent_track_conflicts_with_itself(self):
        """Booking the full parent track that is already fully booked must conflict."""
        self._make_event(self.parent, 'Existing Full Event')
        form = EventForm(data=self._form_data(self.parent))
        self.assertFalse(form.is_valid(), "Expected conflict on same parent track")

    def test_no_conflict_non_overlapping_times(self):
        """Even with parent/subtrack relationship, non-overlapping times must not conflict."""
        self._make_event(self.parent, 'Morning Full Event')
        afternoon_start = datetime(2026, 4, 1, 14, 0, tzinfo=dt_timezone.utc)
        afternoon_end   = datetime(2026, 4, 1, 16, 0, tzinfo=dt_timezone.utc)
        form = EventForm(data=self._form_data(self.sub_north, afternoon_start, afternoon_end))
        self.assertTrue(form.is_valid(), f"Non-overlapping time should not conflict. Errors: {form.errors}")


class SubtrackDayViewTest(TestCase):
    """Day view renders separate rows for subtracks."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        self.parent = Asset.objects.create(
            name='Test Main Track', asset_type=Asset.AssetType.TRACK
        )
        self.sub_north = Asset.objects.create(
            name='North', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_south = Asset.objects.create(
            name='South', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )

    def test_day_view_shows_subtrack_names(self):
        """Day view must show the subtrack names."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'North')
        self.assertContains(response, 'South')

    def test_day_view_subtrack_event_appears_in_correct_row(self):
        """An event booked on a subtrack must appear in the day view."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='North Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_north)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'North Test')
        self.assertContains(response, 'gantt-block')

    def test_day_view_full_track_event_shows_fulltrack_overlay(self):
        """A full-track (parent) event must render with the gantt-fulltrack-overlay class."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Full Track Event', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.parent)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'Full Track Event')
        self.assertContains(response, 'gantt-fulltrack-overlay')

    def test_day_view_standalone_track_unchanged(self):
        """A track with no subtracks renders normally (no subtrack row markup)."""
        standalone = Asset.objects.create(
            name='Standalone Track', asset_type=Asset.AssetType.TRACK
        )
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'Standalone Track')


class SubtrackWeekViewTest(TestCase):
    """Week view renders separate subtrack rows."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        self.parent = Asset.objects.create(
            name='Test Main Track', asset_type=Asset.AssetType.TRACK
        )
        self.sub_north = Asset.objects.create(
            name='North', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_south = Asset.objects.create(
            name='South', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )

    def test_week_view_shows_parent_track_name(self):
        """Week view shows the parent track name (subtracks collapsed into one row)."""
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Main Track')
        # Subtrack names are not shown in the simplified single-row week view.
        self.assertNotContains(response, 'trk-subtrack-row')

    def test_week_view_subtrack_event_appears(self):
        """An event booked on a subtrack must appear in the week view."""
        start = datetime(2026, 3, 30, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='North Week Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_north)
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        self.assertContains(response, 'North Week Test')

    def test_week_view_full_track_event_appears(self):
        """A full-track (parent) event must appear in the single parent-track row."""
        start = datetime(2026, 3, 30, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Full Track Week Event', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.parent)
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        self.assertContains(response, 'Full Track Week Event')

    def test_week_view_single_row_per_track(self):
        """The simplified week view renders exactly one row per parent track (no rowspans)."""
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        content = response.content.decode()
        # No rowspan attributes — each track is a single row.
        self.assertNotIn('rowspan=', content)

    def test_week_view_sibling_events_both_appear(self):
        """Two events on sibling subtracks on the same day must both appear."""
        start = datetime(2026, 3, 30, 9, 0, tzinfo=dt_timezone.utc)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=dt_timezone.utc)
        ev1 = Event.objects.create(
            title='North Event', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev1.assets.add(self.sub_north)
        ev2 = Event.objects.create(
            title='South Event', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev2.assets.add(self.sub_south)
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        self.assertContains(response, 'North Event')
        self.assertContains(response, 'South Event')


# ── Dashboard Events API Tests ───────────────────────────────────────────────

class DashboardEventsAPITest(TestCase):
    """Tests for /cal/api/dashboard-events/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='dashadmin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='dashuser', password='Testpass123!'
        )
        self.track = Asset.objects.create(
            name='API Track', asset_type=Asset.AssetType.TRACK
        )
        self.url = reverse('cal:dashboard_events_api')

    def test_admin_gets_200_with_tracks(self):
        self.client.login(username='dashadmin', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('tracks', data)
        self.assertIn('date', data)

    def test_non_admin_gets_403(self):
        self.client.login(username='dashuser', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_redirects(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_invalid_date_falls_back_to_today(self):
        self.client.login(username='dashadmin', password='Testpass123!')
        resp = self.client.get(self.url, {'date': 'not-a-date'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['date'], timezone.now().date().isoformat())

    def test_date_filtering_returns_events(self):
        self.client.login(username='dashadmin', password='Testpass123!')
        now = timezone.now()
        event = Event.objects.create(
            title='API Test Event', description='Test',
            start_time=now.replace(hour=10, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=12, minute=0, second=0, microsecond=0),
            is_approved=True,
        )
        event.assets.add(self.track)
        resp = self.client.get(self.url, {'date': now.date().isoformat()})
        data = resp.json()
        track_data = data['tracks'].get('API Track', {})
        self.assertGreaterEqual(len(track_data.get('events', [])), 1)


# ── Stamp Actual Time API Tests ──────────────────────────────────────────────

class StampActualAPITest(TestCase):
    """Tests for /cal/api/event/<id>/stamp/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='stampadmin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='stampuser', password='Testpass123!'
        )
        self.track = Asset.objects.create(
            name='Stamp Track', asset_type=Asset.AssetType.TRACK
        )
        now = timezone.now()
        self.event = Event.objects.create(
            title='Stamp Test Event', description='Test',
            start_time=now, end_time=now + timedelta(hours=2),
            is_approved=True, created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.url = reverse('cal:dashboard_stamp_actual', args=[self.event.pk])

    def _post_stamp(self, action, time=None):
        body = {'action': action}
        if time:
            body['time'] = time
        return self.client.post(
            self.url, data=json.dumps(body),
            content_type='application/json',
        )

    def test_admin_stamp_start(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        resp = self._post_stamp('start')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data['actual_start'])
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.actual_start)

    def test_admin_stamp_end(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        self._post_stamp('start')
        resp = self._post_stamp('end')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json()['actual_end'])

    def test_admin_clear_start(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        self._post_stamp('start')
        resp = self._post_stamp('clear_start')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['actual_start'])

    def test_admin_clear_end(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        self._post_stamp('end')
        resp = self._post_stamp('clear_end')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['actual_end'])

    def test_non_admin_gets_403(self):
        self.client.login(username='stampuser', password='Testpass123!')
        resp = self._post_stamp('start')
        self.assertEqual(resp.status_code, 403)

    def test_nonexistent_event_returns_404(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        url = reverse('cal:dashboard_stamp_actual', args=[99999])
        resp = self.client.post(
            url, data=json.dumps({'action': 'start'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_json_returns_400(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        resp = self.client.post(
            self.url, data='not json',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_action_returns_400(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        resp = self._post_stamp('invalid_action')
        self.assertEqual(resp.status_code, 400)

    def test_get_returns_405(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_stamp_with_custom_iso_time(self):
        self.client.login(username='stampadmin', password='Testpass123!')
        custom = timezone.now().replace(hour=9, minute=15, second=0, microsecond=0)
        resp = self._post_stamp('start', time=custom.isoformat())
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.actual_start.hour, custom.hour)
        self.assertEqual(self.event.actual_start.minute, custom.minute)


# ── Analytics API Tests ──────────────────────────────────────────────────────

class AnalyticsAPITest(TestCase):
    """Tests for /cal/api/analytics/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='analyticsadmin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='analyticsuser', password='Testpass123!'
        )
        self.url = reverse('cal:analytics_api')

    def test_admin_gets_200_with_expected_keys(self):
        self.client.login(username='analyticsadmin', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for key in ('track_utilization', 'schedule_accuracy', 'usage_trends',
                    'peak_hours', 'user_activity', 'asset_usage'):
            self.assertIn(key, data)

    def test_non_admin_gets_403(self):
        self.client.login(username='analyticsuser', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_date_range_params(self):
        self.client.login(username='analyticsadmin', password='Testpass123!')
        today = timezone.now().date()
        resp = self.client.get(self.url, {
            'start': today.isoformat(),
            'end': (today + timedelta(days=7)).isoformat(),
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['range']['start'], today.isoformat())

    def test_invalid_dates_fallback(self):
        self.client.login(username='analyticsadmin', password='Testpass123!')
        resp = self.client.get(self.url, {'start': 'bad', 'end': 'bad'})
        self.assertEqual(resp.status_code, 200)


# ── Dashboard & Analytics View Access ────────────────────────────────────────

class DashboardAnalyticsAccessTest(TestCase):
    """Admin-only view access checks for dashboard and analytics."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='viewadmin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='viewuser', password='Testpass123!'
        )

    def test_dashboard_admin_ok(self):
        self.client.login(username='viewadmin', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_non_admin_redirects(self):
        self.client.login(username='viewuser', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_analytics_admin_ok(self):
        self.client.login(username='viewadmin', password='Testpass123!')
        resp = self.client.get(reverse('cal:analytics'))
        self.assertEqual(resp.status_code, 200)

    def test_analytics_non_admin_redirects(self):
        self.client.login(username='viewuser', password='Testpass123!')
        resp = self.client.get(reverse('cal:analytics'))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_unauthenticated_redirects_to_login(self):
        resp = self.client.get(reverse('cal:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/users/login/', resp.url)
