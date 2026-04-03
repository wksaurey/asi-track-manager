import json
import os
from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import get_current_timezone

from .models import Asset, Event
from .forms import EventForm

_local_tz = get_current_timezone()

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


# ── EventForm duration validation ─────────────────────────────────────────────

class EventFormDurationTest(TestCase):
    """EventForm.clean() must require end time after start time (no minimum duration)."""

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

    def test_event_form_5_minutes_is_valid(self):
        """Short durations are allowed."""
        form = EventForm(data=self._form_data(5))
        self.assertTrue(form.is_valid(), form.errors)

    def test_event_form_30_minutes_is_valid(self):
        """Duration of 30 minutes must pass validation."""
        form = EventForm(data=self._form_data(30))
        self.assertTrue(form.is_valid(), form.errors)

    def test_event_form_end_before_start_is_invalid(self):
        """End time before start time must fail validation."""
        form = EventForm(data=self._form_data(-30))
        self.assertFalse(form.is_valid())


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
    """Regular users can view (read-only) but not edit another user's event."""

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

    def test_event_view_other_user_readonly(self):
        """Regular user can view another user's event in read-only mode."""
        self.client.login(username='other', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_edit'])

    def test_event_post_other_user_blocked(self):
        """Regular user cannot POST to another user's event."""
        self.client.login(username='other', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.post(url, {
            'title': 'Hacked',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Owner Event')

    def test_event_edit_owner_can_edit(self):
        """Event owner can access the edit view with full edit rights."""
        self.client.login(username='owner', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_edit'])


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
        start = datetime(2026, 3, 9, 10, 0, tzinfo=_local_tz)
        end = datetime(2026, 3, 9, 12, 0, tzinfo=_local_tz)
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
        start = datetime(2026, 3, 9, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 9, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Morning Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'Morning Test')
        self.assertContains(response, 'gantt-block')

    def test_day_view_event_position_in_html(self):
        """9am start in 24h range: 540/1440*100 = 37.5%."""
        start = datetime(2026, 3, 9, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 9, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Position Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'left:37.5%')

    def test_day_view_early_morning_event_rendered(self):
        """Event at 4am-5am is visible in the 24h gantt view."""
        start = datetime(2026, 3, 9, 4, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 9, 5, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Pre-Dawn Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'Pre-Dawn Test')

    def test_day_view_asset_filter_hidden(self):
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertNotContains(response, 'asset-filter-form')

    def test_day_view_overlapping_events_use_multiple_sub_rows(self):
        """Two overlapping events on the same track appear in separate sub-rows."""
        start1 = datetime(2026, 3, 9, 9, 0, tzinfo=_local_tz)
        end1   = datetime(2026, 3, 9, 12, 0, tzinfo=_local_tz)
        start2 = datetime(2026, 3, 9, 10, 0, tzinfo=_local_tz)
        end2   = datetime(2026, 3, 9, 13, 0, tzinfo=_local_tz)
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
        """Parent track display_name should be just the name (no suffix)."""
        parent = Asset.objects.create(name='Test Main Track', asset_type=Asset.AssetType.TRACK)
        Asset.objects.create(name='North', asset_type=Asset.AssetType.TRACK, parent=parent)
        parent.refresh_from_db()
        self.assertEqual(parent.display_name, 'Test Main Track')

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
    """v1.1: Subtrack conflict detection — form saves with warnings, enforcement at approval."""

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
        self.start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        self.end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)

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

    def test_booking_subtrack_with_parent_booked_saves_with_warning(self):
        """v1.1: Booking subtrack when parent booked saves but warns."""
        self._make_event(self.parent, 'Full Track Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertTrue(form.is_valid(), f"v1.1: should save with warning. Errors: {form.errors}")
        self.assertTrue(len(form._conflict_warnings) > 0, "Should warn about parent conflict")

    def test_booking_parent_with_subtrack_booked_saves_with_warning(self):
        """v1.1: Booking parent when subtrack booked saves but warns."""
        self._make_event(self.sub_north, 'North Sub Event')
        form = EventForm(data=self._form_data(self.parent))
        self.assertTrue(form.is_valid(), f"v1.1: should save with warning. Errors: {form.errors}")
        self.assertTrue(len(form._conflict_warnings) > 0, "Should warn about subtrack conflict")

    def test_sibling_subtracks_do_not_conflict(self):
        """Booking North subtrack must NOT conflict with an existing South subtrack booking."""
        self._make_event(self.sub_south, 'South Sub Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertTrue(form.is_valid(), f"Sibling subtracks should not conflict. Errors: {form.errors}")

    def test_same_subtrack_saves_with_warning(self):
        """v1.1: Booking same subtrack at same time saves but warns."""
        self._make_event(self.sub_north, 'Existing North Event')
        form = EventForm(data=self._form_data(self.sub_north))
        self.assertTrue(form.is_valid(), f"v1.1: should save with warning. Errors: {form.errors}")
        self.assertTrue(len(form._conflict_warnings) > 0, "Should warn about same subtrack conflict")

    def test_same_parent_track_saves_with_warning(self):
        """v1.1: Booking same parent track at same time saves but warns."""
        self._make_event(self.parent, 'Existing Full Event')
        form = EventForm(data=self._form_data(self.parent))
        self.assertTrue(form.is_valid(), f"v1.1: should save with warning. Errors: {form.errors}")
        self.assertTrue(len(form._conflict_warnings) > 0, "Should warn about same parent conflict")

    def test_no_conflict_non_overlapping_times(self):
        """Even with parent/subtrack relationship, non-overlapping times must not conflict."""
        self._make_event(self.parent, 'Morning Full Event')
        afternoon_start = datetime(2026, 4, 1, 14, 0, tzinfo=_local_tz)
        afternoon_end   = datetime(2026, 4, 1, 16, 0, tzinfo=_local_tz)
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
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='North Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_north)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'North Test')
        self.assertContains(response, 'gantt-block')

    def test_day_view_full_track_event_shows_parent_lane(self):
        """A full-track (parent) event must render in the gantt-parent-lane."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Full Track Event', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.parent)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'Full Track Event')
        self.assertContains(response, 'gantt-parent-lane')

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
        start = datetime(2026, 3, 30, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='North Week Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_north)
        response = self.client.get(reverse('cal:calendar') + '?view=week&date=2026-3-30')
        self.assertContains(response, 'North Week Test')

    def test_week_view_full_track_event_appears(self):
        """A full-track (parent) event must appear in the single parent-track row."""
        start = datetime(2026, 3, 30, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=_local_tz)
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
        start = datetime(2026, 3, 30, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 3, 30, 11, 0, tzinfo=_local_tz)
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
        from django.utils.timezone import localtime
        self.assertEqual(data['date'], localtime(timezone.now()).date().isoformat())

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

    def test_track_includes_color_key(self):
        """Each track dict in the API response must include a 'color' key."""
        self.client.login(username='dashadmin', password='Testpass123!')
        resp = self.client.get(self.url)
        data = resp.json()
        for track_name, track_info in data['tracks'].items():
            self.assertIn('color', track_info,
                          f"Track '{track_name}' missing 'color' key in API response")

    def test_track_color_matches_model(self):
        """When a track has a color set, the API response must return that exact value."""
        self.track.color = '#e11d48'
        self.track.save()
        self.client.login(username='dashadmin', password='Testpass123!')
        resp = self.client.get(self.url)
        data = resp.json()
        track_data = data['tracks'].get('API Track', {})
        self.assertEqual(track_data.get('color'), '#e11d48')


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


# ── Radio Channel API Tests ─────────────────────────────────────────────────

class RadioChannelAPITest(TestCase):
    """Tests for /cal/api/track/<id>/channel/ endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='channeladmin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='channeluser', password='Testpass123!'
        )
        self.track = Asset.objects.create(
            name='Channel Track', asset_type=Asset.AssetType.TRACK
        )
        self.url = reverse('cal:set_radio_channel', args=[self.track.pk])

    def test_admin_can_set_channel(self):
        self.client.login(username='channeladmin', password='Testpass123!')
        resp = self.client.post(
            self.url, data=json.dumps({'channel': 12}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.track.refresh_from_db()
        self.assertEqual(self.track.radio_channel, 12)

    def test_admin_can_clear_channel(self):
        self.track.radio_channel = 14
        self.track.save()
        self.client.login(username='channeladmin', password='Testpass123!')
        resp = self.client.post(
            self.url, data=json.dumps({'channel': None}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.track.refresh_from_db()
        self.assertIsNone(self.track.radio_channel)

    def test_rejects_out_of_range(self):
        self.client.login(username='channeladmin', password='Testpass123!')
        resp = self.client.post(
            self.url, data=json.dumps({'channel': 5}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_admin_gets_403(self):
        self.client.login(username='channeluser', password='Testpass123!')
        resp = self.client.post(
            self.url, data=json.dumps({'channel': 11}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_get_returns_405(self):
        self.client.login(username='channeladmin', password='Testpass123!')
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_dashboard_api_includes_radio_channel(self):
        self.track.radio_channel = 15
        self.track.save()
        self.client.login(username='channeladmin', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        data = resp.json()
        track_data = data['tracks'].get('Channel Track', {})
        self.assertEqual(track_data.get('radio_channel'), 15)


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


# ── P1: Event.description optional ──────────────────────────────────────────

class EventDescriptionOptionalTest(TestCase):
    """Event.description must be optional (blank=True)."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.asset = Asset.objects.create(
            name='Test Track', asset_type=Asset.AssetType.TRACK
        )

    def test_model_saves_with_empty_description(self):
        """Event created with description='' saves without raising."""
        event = Event.objects.create(
            title='No Desc',
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.user,
        )
        event.full_clean()  # must not raise ValidationError
        self.assertEqual(event.description, '')

    def test_form_valid_without_description(self):
        """EventForm with empty description must be valid."""
        form = EventForm(data={
            'title': 'Test',
            'description': '',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_view_post_empty_description_redirects(self):
        """POST to event/new/ with description='' returns 302 redirect."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.post(reverse('cal:event_new'), {
            'title': 'Test Event',
            'description': '',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        })
        self.assertEqual(response.status_code, 302)


# ── P2: Post-approval redirect ──────────────────────────────────────────────

class EventApproveRedirectTest(TestCase):
    """event_approve must respect the 'next' POST param for redirect, but reject external URLs."""

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

    def test_approve_with_next_redirects_to_next(self):
        """POST with next=/cal/calendar/ must redirect there after approval."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.post(url, {'next': '/cal/calendar/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/cal/calendar/')
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_approved)

    def test_approve_with_external_next_falls_back_to_pending(self):
        """POST with next=http://evil.com must NOT redirect externally."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.post(url, {'next': 'http://evil.com'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/events/pending/', response['Location'])
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_approved)

    def test_approve_with_protocol_relative_next_falls_back(self):
        """//evil.com is a protocol-relative URL — must be rejected."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[self.event.pk])
        response = self.client.post(url, {'next': '//evil.com'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/events/pending/', response['Location'])


# ── P3: Gantt data-end attribute + event-past CSS ────────────────────────────

class GanttDataEndAttributeTest(TestCase):
    """Task 3: Gantt blocks must include a data-end attribute with ISO end time."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(name='North Loop', asset_type='track')

    def test_gantt_block_has_data_end_attribute(self):
        """Day view Gantt blocks include data-end with the event end time."""
        start = datetime(2026, 3, 9, 9, 0, tzinfo=_local_tz)
        end = datetime(2026, 3, 9, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Data End Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        ev.refresh_from_db()
        self.assertContains(response, f'data-end="{ev.end_time.isoformat()}"')

    def test_event_past_css_rule_exists(self):
        """styles.css must contain the .event-past rule with opacity.

        STALE NOTE: This test will need to be updated as part of the Gantt
        redesign.  The .event-past class is being superseded by event-completed
        and event-noshow.  Once the redesign lands, either update this test to
        assert .event-past is gone (if removed) or assert it is redefined, and
        delete this comment.
        """
        css_path = os.path.join(
            os.path.dirname(__file__), 'static', 'cal', 'css', 'styles.css'
        )
        with open(css_path) as f:
            css = f.read()
        self.assertIn('.event-past', css)
        self.assertIn('opacity', css[css.index('.event-past'):css.index('.event-past') + 200])


# ── P3: Pending badge visibility ─────────────────────────────────────────────

class PendingBadgeTest(TestCase):
    """Task 6: Pending badge must appear for unapproved events and not for approved ones."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.start = timezone.now() + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def test_pending_event_has_pending_badge(self):
        """get_html_url for a PENDING event contains 'pending-badge'."""
        ev = Event.objects.create(
            title='Pending Ev', description='', start_time=self.start, end_time=self.end,
            created_by=self.user, is_approved=False,
        )
        self.assertIn('pending-badge', ev.get_html_url)

    def test_approved_event_no_pending_badge(self):
        """get_html_url for an APPROVED event must NOT contain 'pending-badge'."""
        ev = Event.objects.create(
            title='Approved Ev', description='', start_time=self.start, end_time=self.end,
            created_by=self.user, is_approved=True,
        )
        self.assertNotIn('pending-badge', ev.get_html_url)


# ── Test Gap 3: Event auto-approval ──────────────────────────────────────────

class EventAutoApprovalTest(TestCase):
    """v1.1: ALL events default to unapproved regardless of creator role."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')
        self.asset = Asset.objects.create(
            name='Approval Track', asset_type=Asset.AssetType.TRACK
        )
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def _post_data(self):
        return {
            'title': 'Auto Approval Test',
            'description': 'desc',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        }

    def test_staff_created_event_is_not_auto_approved(self):
        """v1.1: Staff user POSTs -> event.is_approved is False (no auto-approve)."""
        self.client.login(username='admin', password='Testpass123!')
        response = self.client.post(reverse('cal:event_new'), self._post_data())
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Auto Approval Test')
        self.assertFalse(event.is_approved)

    def test_non_staff_created_event_is_pending(self):
        """Regular user POSTs -> event.is_approved is False."""
        self.client.login(username='employee', password='Testpass123!')
        response = self.client.post(reverse('cal:event_new'), self._post_data())
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Auto Approval Test')
        self.assertFalse(event.is_approved)


# ── Test Gap 4: Touching vs overlapping times ────────────────────────────────

class EventTouchingTimesTest(TestCase):
    """Touching times (end == start) do not conflict; overlapping times do."""

    def setUp(self):
        self.user = User.objects.create_user(username='employee', password='Testpass123!')
        self.asset = Asset.objects.create(
            name='Touch Track', asset_type=Asset.AssetType.TRACK
        )
        self.nine_am = datetime(2026, 5, 1, 9, 0, tzinfo=_local_tz)
        self.ten_am = datetime(2026, 5, 1, 10, 0, tzinfo=_local_tz)
        self.eleven_am = datetime(2026, 5, 1, 11, 0, tzinfo=_local_tz)
        self.noon = datetime(2026, 5, 1, 12, 0, tzinfo=_local_tz)
        # Existing event: 9 AM - 10 AM
        ev = Event.objects.create(
            title='First Block', description='',
            start_time=self.nine_am, end_time=self.ten_am,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.asset)

    def test_touching_times_do_not_conflict(self):
        """Event1 is 9-10 AM, event2 tries 10-11 AM on same asset -> form IS valid."""
        form = EventForm(data={
            'title': 'Touching Block',
            'description': '',
            'start_time': self.ten_am.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.eleven_am.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        })
        self.assertTrue(form.is_valid(), f"Touching times should not conflict. Errors: {form.errors}")

    def test_overlapping_times_save_with_warning(self):
        """v1.1: Overlapping times no longer block save — form IS valid (warning only)."""
        # Update existing event to 9-11 AM
        ev = Event.objects.get(title='First Block')
        ev.end_time = self.eleven_am
        ev.save()
        form = EventForm(data={
            'title': 'Overlapping Block',
            'description': '',
            'start_time': self.ten_am.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.noon.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        })
        self.assertTrue(form.is_valid(), f"v1.1: overlapping events should save. Errors: {form.errors}")
        self.assertTrue(len(form._conflict_warnings) > 0, "Should have conflict warning")


# ── Test Gap 5: Asset form POST ──────────────────────────────────────────────

class AssetFormPostTest(TestCase):
    """Tests for creating and editing assets via POST."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.client.login(username='admin', password='Testpass123!')

    def test_staff_can_create_track_via_post(self):
        """Staff POSTs to cal:asset_create with name + asset_type=track -> 302, asset created."""
        response = self.client.post(reverse('cal:asset_create'), {
            'name': 'Brand New Track',
            'asset_type': 'track',
            'description': '',
            'parent': '',
            'color': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Asset.objects.filter(name='Brand New Track').exists())

    def test_subtrack_creation_via_parent_param(self):
        """Staff POSTs with parent field set to existing parent track ID -> subtrack created."""
        parent = Asset.objects.create(
            name='Parent Track', asset_type=Asset.AssetType.TRACK
        )
        response = self.client.post(reverse('cal:asset_create'), {
            'name': 'East Lane',
            'asset_type': 'track',
            'description': '',
            'parent': parent.pk,
            'color': '',
        })
        self.assertEqual(response.status_code, 302)
        subtrack = Asset.objects.get(name='East Lane')
        self.assertEqual(subtrack.parent_id, parent.pk)

    def test_staff_can_edit_asset_via_post(self):
        """Staff POSTs to cal:asset_edit with updated name -> asset name changed."""
        asset = Asset.objects.create(
            name='Old Name', asset_type=Asset.AssetType.TRACK
        )
        url = reverse('cal:asset_edit', args=[asset.pk])
        response = self.client.post(url, {
            'name': 'New Name',
            'asset_type': 'track',
            'description': '',
            'parent': '',
            'color': asset.color,
        })
        self.assertEqual(response.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual(asset.name, 'New Name')


# ── Test Gap 6: Analytics computation ─────────────────────────────────────────

class AnalyticsComputationTest(TestCase):
    """Tests for analytics_api computation correctness."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='analyticsstaff', password='Testpass123!', is_staff=True
        )
        self.client.login(username='analyticsstaff', password='Testpass123!')
        self.url = reverse('cal:analytics_api')
        self.track = Asset.objects.create(
            name='Analytics Track', asset_type=Asset.AssetType.TRACK
        )

    def test_track_utilization_computation(self):
        """Create a 2h approved event -> scheduled_hours matches expected value."""
        start = datetime(2026, 5, 4, 9, 0, tzinfo=_local_tz)
        end = datetime(2026, 5, 4, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Util Test', description='',
            start_time=start, end_time=end,
            created_by=self.admin, is_approved=True,
        )
        ev.assets.add(self.track)
        resp = self.client.get(self.url, {'start': '2026-05-04', 'end': '2026-05-04'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        track_entry = next(
            (t for t in data['track_utilization'] if t['name'] == self.track.display_name),
            None,
        )
        self.assertIsNotNone(track_entry, "Expected track in utilization data")
        self.assertEqual(track_entry['scheduled_hours'], 2.0)

    def test_schedule_accuracy_computation(self):
        """Create event with actual_start 15 min late -> avg_start_delta_minutes is 15."""
        from cal.models import ActualTimeSegment
        start = datetime(2026, 5, 4, 9, 0, tzinfo=_local_tz)
        end = datetime(2026, 5, 4, 11, 0, tzinfo=_local_tz)
        actual_start = datetime(2026, 5, 4, 9, 15, tzinfo=_local_tz)
        actual_end = datetime(2026, 5, 4, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Accuracy Test', description='',
            start_time=start, end_time=end,
            created_by=self.admin, is_approved=True,
        )
        ActualTimeSegment.objects.create(event=ev, start=actual_start, end=actual_end)
        ev.assets.add(self.track)
        resp = self.client.get(self.url, {'start': '2026-05-04', 'end': '2026-05-04'})
        data = resp.json()
        self.assertEqual(data['schedule_accuracy']['avg_start_delta_minutes'], 15.0)
        self.assertEqual(data['schedule_accuracy']['avg_end_delta_minutes'], 0)

    def test_empty_range_returns_zeros(self):
        """Call analytics_api with a date range that has no events -> all metrics are 0/empty."""
        resp = self.client.get(self.url, {'start': '2099-01-01', 'end': '2099-01-07'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['schedule_accuracy']['avg_start_delta_minutes'], 0)
        self.assertEqual(data['schedule_accuracy']['avg_end_delta_minutes'], 0)
        self.assertEqual(data['schedule_accuracy']['events_with_actuals'], 0)
        self.assertEqual(data['schedule_accuracy']['total_events'], 0)


# ── Test Gap 7: Asset color auto-assignment ───────────────────────────────────

from .models import TRACK_COLOR_PALETTE


class AssetColorAutoAssignmentTest(TestCase):
    """Tests for automatic color assignment to new track assets."""

    def test_first_track_gets_first_palette_color(self):
        """Create a track without setting color -> color equals first color in TRACK_COLOR_PALETTE."""
        # Clear any tracks seeded by migrations
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK).delete()
        track = Asset.objects.create(
            name='Color Test Track 1', asset_type=Asset.AssetType.TRACK
        )
        self.assertEqual(track.color, TRACK_COLOR_PALETTE[0])

    def test_second_track_gets_second_color(self):
        """Create two tracks -> second gets second palette color."""
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK).delete()
        Asset.objects.create(name='Color Track A', asset_type=Asset.AssetType.TRACK)
        track2 = Asset.objects.create(name='Color Track B', asset_type=Asset.AssetType.TRACK)
        self.assertEqual(track2.color, TRACK_COLOR_PALETTE[1])

    def test_color_cycles_after_palette_exhausted(self):
        """Create 17 tracks -> 17th cycles back to a palette color."""
        Asset.objects.filter(asset_type=Asset.AssetType.TRACK).delete()
        palette_len = len(TRACK_COLOR_PALETTE)
        for i in range(palette_len):
            Asset.objects.create(
                name=f'Palette Track {i}', asset_type=Asset.AssetType.TRACK
            )
        # 17th track (index 16 = palette_len) should cycle
        track_17 = Asset.objects.create(
            name='Cycle Track', asset_type=Asset.AssetType.TRACK
        )
        self.assertIn(track_17.color, TRACK_COLOR_PALETTE)


# ── Dark Mode CSS Integrity Tests ────────────────────────────────────────────

class DarkModeDashboardCSSTest(TestCase):
    """Ensure dark-theme overrides in dashboard.css don't break background-image rules.

    Regression: dark-theme rules that set background-image without also setting
    background-repeat/position/size cause SVG arrows to tile across the element.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.conf import settings
        css_path = os.path.join(
            settings.BASE_DIR, 'cal', 'static', 'cal', 'css', 'dashboard.css'
        )
        with open(css_path, 'r') as f:
            cls.css = f.read()
        # Parse CSS into rule blocks: list of (selector, body) tuples
        import re
        cls.blocks = []
        # Match selectors followed by { body }
        for m in re.finditer(
            r'([^{}]+?)\s*\{([^{}]*)\}', cls.css
        ):
            selector = m.group(1).strip()
            body = m.group(2).strip()
            cls.blocks.append((selector, body))

    def _dark_blocks(self):
        """Return all (selector, body) tuples for html.dark-theme rules."""
        return [(s, b) for s, b in self.blocks if 'dark-theme' in s]

    def _parse_props(self, body):
        """Parse a CSS body string into a dict of property -> value."""
        import re
        props = {}
        for decl in re.split(r';\s*', body):
            decl = decl.strip()
            if ':' in decl:
                prop, _, val = decl.partition(':')
                props[prop.strip()] = val.strip()
        return props

    def test_background_image_has_no_repeat(self):
        """Any rule with background-image must also set background-repeat: no-repeat
        (either in the same block or via its base selector)."""
        import re
        # Collect base (non-dark) selectors that already set background-repeat
        base_selectors_with_repeat = set()
        for selector, body in self.blocks:
            if 'dark-theme' not in selector:
                props = self._parse_props(body)
                if props.get('background-repeat') == 'no-repeat':
                    base_selectors_with_repeat.add(selector)

        for selector, body in self._dark_blocks():
            props = self._parse_props(body)
            if 'background-image' not in props:
                continue
            # Check this block has background-repeat
            if props.get('background-repeat') == 'no-repeat':
                continue
            # Check if shorthand 'background' includes no-repeat
            bg = props.get('background', '')
            if 'no-repeat' in bg:
                continue
            # Check if a base selector for the same element has it
            # Extract the element selector (strip "html.dark-theme " prefix)
            base_sel = re.sub(r'html\.dark-theme\s+', '', selector).strip()
            if base_sel in base_selectors_with_repeat:
                continue
            self.fail(
                f"Dark-theme rule '{selector}' sets background-image but "
                f"does not ensure background-repeat: no-repeat. "
                f"This causes SVG arrows to tile across the element."
            )

    def test_background_image_has_position(self):
        """Any rule with background-image must also set background-position
        (either in the same block or via its base selector)."""
        import re
        base_selectors_with_position = set()
        for selector, body in self.blocks:
            if 'dark-theme' not in selector:
                props = self._parse_props(body)
                if 'background-position' in props:
                    base_selectors_with_position.add(selector)

        for selector, body in self._dark_blocks():
            props = self._parse_props(body)
            if 'background-image' not in props:
                continue
            if 'background-position' in props:
                continue
            bg = props.get('background', '')
            if 'center' in bg or 'left' in bg or 'right' in bg:
                continue
            base_sel = re.sub(r'html\.dark-theme\s+', '', selector).strip()
            if base_sel in base_selectors_with_position:
                continue
            self.fail(
                f"Dark-theme rule '{selector}' sets background-image but "
                f"does not ensure background-position is set."
            )

    def test_background_image_has_size(self):
        """Any rule with background-image must also set background-size
        (either in the same block or via its base selector)."""
        import re
        base_selectors_with_size = set()
        for selector, body in self.blocks:
            if 'dark-theme' not in selector:
                props = self._parse_props(body)
                if 'background-size' in props:
                    base_selectors_with_size.add(selector)

        for selector, body in self._dark_blocks():
            props = self._parse_props(body)
            if 'background-image' not in props:
                continue
            if 'background-size' in props:
                continue
            base_sel = re.sub(r'html\.dark-theme\s+', '', selector).strip()
            if base_sel in base_selectors_with_size:
                continue
            self.fail(
                f"Dark-theme rule '{selector}' sets background-image but "
                f"does not ensure background-size is set."
            )

    def test_dark_theme_hover_preserves_background_image(self):
        """Dark-theme hover/focus rules must not use shorthand 'background'
        if the base rule uses background-image (shorthand resets the image)."""
        import re
        # Find dark-theme base rules that use background-image
        dark_selectors_with_image = set()
        for selector, body in self._dark_blocks():
            props = self._parse_props(body)
            if 'background-image' in props:
                # Normalize: "html.dark-theme select.foo" -> "select.foo"
                base_sel = re.sub(r'html\.dark-theme\s+', '', selector).strip()
                dark_selectors_with_image.add(base_sel)

        for selector, body in self._dark_blocks():
            if ':hover' not in selector and ':focus' not in selector:
                continue
            props = self._parse_props(body)
            if 'background' not in props:
                continue
            # This rule uses shorthand 'background' — check if it
            # would clobber a background-image from the base rule
            base_sel = re.sub(
                r'html\.dark-theme\s+', '', selector
            ).strip()
            # Strip :hover/:focus to get the base selector
            base_sel = re.sub(r':(hover|focus)', '', base_sel).strip()
            # Remove double commas and trailing commas from multi-selectors
            base_sel = re.sub(r',\s*,', ',', base_sel).strip().rstrip(',')
            for img_sel in dark_selectors_with_image:
                if img_sel in base_sel or base_sel in img_sel:
                    self.fail(
                        f"Dark-theme rule '{selector}' uses shorthand "
                        f"'background' which resets background-image set "
                        f"by '{img_sel}'. Use 'background-color' instead."
                    )

    def test_styles_css_dark_theme_rules_exist(self):
        """styles.css must contain dark-theme overrides for core UI elements."""
        from django.conf import settings
        css_path = os.path.join(
            settings.BASE_DIR, 'cal', 'static', 'cal', 'css', 'styles.css'
        )
        with open(css_path, 'r') as f:
            styles_css = f.read()
        # Core elements that must have dark-theme rules
        for selector in [
            'html.dark-theme .card',
            'html.dark-theme .cal-nav-arrow',
        ]:
            self.assertIn(
                selector, styles_css,
                f"styles.css missing dark-theme rule for: {selector}"
            )

    def test_dashboard_css_dark_theme_coverage(self):
        """Dashboard CSS must have dark-theme rules for key interactive elements."""
        required_selectors = [
            'html.dark-theme select.event-channel-badge',
            'html.dark-theme .radio-channel-select',
            'html.dark-theme .event-item',
            'html.dark-theme .track-card',
            'html.dark-theme .track-card__header',
        ]
        for selector in required_selectors:
            self.assertIn(
                selector, self.css,
                f"dashboard.css missing dark-theme rule for: {selector}"
            )


# ── Timezone Consistency Tests ───────────────────────────────────────────────

class TimezoneConsistencyTest(TestCase):
    """
    Regression tests ensuring all times display in the app's configured
    timezone (settings.TIME_ZONE), NOT UTC and NOT the server's system
    timezone.  Catches the bug where a server in Mountain Time but
    TIME_ZONE='America/New_York' caused a 2-hour offset.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='tzadmin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(
            name='TZ Track', asset_type=Asset.AssetType.TRACK
        )
        # Create event at a known UTC time: 2026-03-30 16:00 UTC
        self.known_utc = datetime(2026, 3, 30, 16, 0, 0,
                                  tzinfo=dt_timezone.utc)
        self.event = Event.objects.create(
            title='TZ Test Event',
            description='Timezone regression test',
            start_time=self.known_utc,
            end_time=self.known_utc + timedelta(hours=2),
            is_approved=True,
            created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.client.login(username='tzadmin', password='Testpass123!')

    def test_dashboard_api_returns_app_timezone(self):
        """Dashboard API must return ISO times with the app timezone offset,
        not raw UTC (+00:00)."""
        url = reverse('cal:dashboard_events_api')
        resp = self.client.get(url, {'date': '2026-03-30'})
        data = resp.json()
        events = data['tracks'].get('TZ Track', {}).get('events', [])
        self.assertEqual(len(events), 1)

        start_iso = events[0]['start_time']
        # Must NOT end with +00:00 (raw UTC)
        self.assertNotIn('+00:00', start_iso,
                         'API returned UTC instead of app timezone')
        # Parse and verify it represents the correct moment
        from django.utils.timezone import localtime
        expected = localtime(self.known_utc)
        self.assertIn(expected.strftime('%H:%M'), start_iso,
                      f'Expected {expected.strftime("%H:%M")} in {start_iso}')

    def test_stamp_api_returns_app_timezone(self):
        """Stamp API response must return times in the app timezone."""
        url = reverse('cal:dashboard_stamp_actual', args=[self.event.pk])
        resp = self.client.post(
            url, data=json.dumps({'action': 'start'}),
            content_type='application/json',
        )
        data = resp.json()
        actual_start = data['actual_start']
        self.assertIsNotNone(actual_start)
        # Must contain the app timezone offset, not +00:00
        self.assertNotIn('+00:00', actual_start,
                         'Stamp API returned UTC instead of app timezone')

    def test_stamp_roundtrip_time_matches(self):
        """Stamping 'start' then reading the API should show the same time
        for the actual bar as the moment the stamp was placed."""
        stamp_url = reverse('cal:dashboard_stamp_actual', args=[self.event.pk])
        before = timezone.now()
        self.client.post(
            stamp_url, data=json.dumps({'action': 'start'}),
            content_type='application/json',
        )
        after = timezone.now()

        # Read back from dashboard API
        api_url = reverse('cal:dashboard_events_api')
        resp = self.client.get(api_url, {'date': '2026-03-30'})
        events = resp.json()['tracks'].get('TZ Track', {}).get('events', [])
        actual_iso = events[0]['actual_start']
        actual_dt = datetime.fromisoformat(actual_iso)

        # The stamped time must be between before and after (same moment)
        self.assertGreaterEqual(actual_dt, before,
                                'Stamp time is before the request')
        self.assertLessEqual(actual_dt, after,
                             'Stamp time is after the request')

    def test_day_view_gantt_bar_uses_local_time(self):
        """Gantt bar CSS position must reflect the app timezone, not UTC.
        For 2026-03-30T16:00Z with TIME_ZONE=America/Denver, the bar
        should be at 10:00 AM MDT, not 4:00 PM UTC."""
        from django.utils.timezone import localtime
        local_start = localtime(self.known_utc)
        expected_hour = local_start.hour  # 10 for America/Denver

        url = reverse('cal:calendar')
        resp = self.client.get(url, {'view': 'day', 'date': '2026-3-30'})
        content = resp.content.decode()

        # The Gantt block time label should show the local hour
        expected_time = local_start.strftime('%I:%M %p').lstrip('0')
        self.assertIn(expected_time, content,
                      f'Day view missing local time {expected_time}; '
                      f'may be showing UTC instead')

    def test_is_today_uses_local_date(self):
        """The 'is_today' flag and gantt-now-line must use the local date,
        not UTC.  Simulates a time when UTC and local dates differ."""
        from django.utils.timezone import localtime, override as tz_override
        import zoneinfo

        # 2026-03-30 23:30 MDT = 2026-03-31 05:30 UTC
        # Local date is March 30, UTC date is March 31
        fake_now = datetime(2026, 3, 31, 5, 30, 0, tzinfo=dt_timezone.utc)

        with unittest.mock.patch('django.utils.timezone.now', return_value=fake_now):
            url = reverse('cal:calendar')
            resp = self.client.get(url, {'view': 'day', 'date': '2026-3-30'})
            content = resp.content.decode()
            # The now-line JS should be present because local date IS today
            self.assertIn('gantt-now-line', content,
                          'Now line missing — is_today may be using UTC date')

    def test_is_today_false_for_different_local_date(self):
        """When viewing a day that is NOT today in local time, no now-line."""
        url = reverse('cal:calendar')
        resp = self.client.get(url, {'view': 'day', 'date': '2026-3-29'})
        content = resp.content.decode()
        self.assertNotIn('gantt-now-line', content)

    def test_event_form_interprets_naive_time_as_app_timezone(self):
        """When a user submits '14:00' via the event form, it must be stored
        as 2:00 PM in the app timezone, not 2:00 PM UTC."""
        from django.utils.timezone import localtime
        url = reverse('cal:event_new')
        resp = self.client.post(url, {
            'title': 'TZ Form Test',
            'description': '',
            'start_time': '2026-04-01T14:00',
            'end_time': '2026-04-01T15:00',
            'assets': [self.track.pk],
        })
        self.assertEqual(resp.status_code, 302)  # redirect on success
        ev = Event.objects.get(title='TZ Form Test')
        local_start = localtime(ev.start_time)
        self.assertEqual(local_start.hour, 14,
                         f'Form time 14:00 stored as {local_start.hour}:00 '
                         f'local — naive time not interpreted in app timezone')
        self.assertEqual(local_start.minute, 0)

    def test_api_times_consistent_with_gantt(self):
        """The dashboard API and the day-view Gantt must show the same
        hour for the same event — no JS-vs-server timezone split."""
        from django.utils.timezone import localtime

        # Get the local time the Gantt should show
        local_start = localtime(self.known_utc)
        expected_hhmm = local_start.strftime('%H:%M')

        # Dashboard API
        api_url = reverse('cal:dashboard_events_api')
        resp = self.client.get(api_url, {'date': '2026-03-30'})
        events = resp.json()['tracks'].get('TZ Track', {}).get('events', [])
        api_start = events[0]['start_time']
        self.assertIn(expected_hhmm, api_start,
                      f'API time {api_start} does not contain '
                      f'expected local {expected_hhmm}')

        # Day view Gantt
        cal_url = reverse('cal:calendar')
        resp = self.client.get(cal_url, {'view': 'day', 'date': '2026-3-30'})
        content = resp.content.decode()
        display_time = local_start.strftime('%I:%M %p').lstrip('0')
        self.assertIn(display_time, content,
                      f'Gantt missing {display_time} — times may diverge')

    def test_dashboard_api_default_date_is_local(self):
        """When no ?date= param is given, the API must default to the local
        date, not UTC date."""
        from django.utils.timezone import localtime
        fake_now = datetime(2026, 3, 31, 5, 30, 0, tzinfo=dt_timezone.utc)
        local_date = localtime(fake_now).date()  # March 30 MDT

        with unittest.mock.patch('django.utils.timezone.now', return_value=fake_now):
            url = reverse('cal:dashboard_events_api')
            resp = self.client.get(url)
            data = resp.json()
            self.assertEqual(data['date'], local_date.isoformat(),
                             'API default date is UTC, not local')


import unittest.mock


# ════════════════════════════════════════════════════════════════════════════════
# v1.1 TDD Test Suite
# All tests below are written BEFORE implementation and are expected to FAIL
# until the corresponding features are implemented.
# ════════════════════════════════════════════════════════════════════════════════


# ── Task 1: ActualTimeSegment Model ──────────────────────────────────────────

class ActualTimeSegmentModelTest(TestCase):
    """Tests for the new ActualTimeSegment model (replaces flat actual_start/actual_end)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='seg_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='Segment Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.event = Event.objects.create(
            title='Segment Test Event',
            description='',
            start_time=now,
            end_time=now + timedelta(hours=2),
            is_approved=True,
            created_by=self.admin,
        )
        self.event.assets.add(self.track)

    def test_event_has_is_stopped_field_default_false(self):
        """Event.is_stopped must exist and default to False."""
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_stopped)

    def test_current_segment_returns_none_when_no_segments(self):
        """current_segment property returns None when no segments exist."""
        self.assertIsNone(self.event.current_segment)

    def test_is_currently_active_false_with_no_segments(self):
        """is_currently_active is False when there are no segments."""
        self.assertFalse(self.event.is_currently_active)

    def test_total_actual_seconds_zero_with_no_segments(self):
        """total_actual_seconds is 0 when no segments exist."""
        self.assertEqual(self.event.total_actual_seconds, 0)

    def test_create_segment_open(self):
        """Creating a segment with end=None creates an open segment."""
        from cal.models import ActualTimeSegment
        seg = ActualTimeSegment.objects.create(event=self.event, start=timezone.now(), end=None)
        self.assertIsNone(seg.end)
        self.assertEqual(self.event.segments.count(), 1)

    def test_current_segment_returns_open_segment(self):
        """current_segment returns the segment with end=None."""
        from cal.models import ActualTimeSegment
        seg = ActualTimeSegment.objects.create(event=self.event, start=timezone.now(), end=None)
        self.assertEqual(self.event.current_segment, seg)

    def test_is_currently_active_true_with_open_segment(self):
        """is_currently_active is True when an open segment exists."""
        from cal.models import ActualTimeSegment
        ActualTimeSegment.objects.create(event=self.event, start=timezone.now(), end=None)
        self.assertTrue(self.event.is_currently_active)

    def test_current_segment_returns_none_when_all_closed(self):
        """current_segment returns None when all segments have an end time."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        ActualTimeSegment.objects.create(event=self.event, start=now - timedelta(hours=1), end=now)
        self.assertIsNone(self.event.current_segment)

    def test_is_currently_active_false_when_all_segments_closed(self):
        """is_currently_active is False when all segments are closed."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        ActualTimeSegment.objects.create(event=self.event, start=now - timedelta(hours=1), end=now)
        self.assertFalse(self.event.is_currently_active)

    def test_total_actual_seconds_sums_closed_segments(self):
        """total_actual_seconds sums durations of all closed segments."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        # Two segments: 30 min each = 3600 total
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=2),
            end=now - timedelta(hours=2) + timedelta(minutes=30),
        )
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=1),
            end=now - timedelta(hours=1) + timedelta(minutes=30),
        )
        self.assertEqual(self.event.total_actual_seconds, 3600)

    def test_total_actual_seconds_excludes_open_segment(self):
        """total_actual_seconds does not count an open (end=None) segment."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(minutes=30),
            end=now,
        )
        ActualTimeSegment.objects.create(event=self.event, start=now, end=None)
        self.assertEqual(self.event.total_actual_seconds, 1800)

    def test_actual_start_property_returns_first_segment_start(self):
        """actual_start property returns the start time of the first segment."""
        from cal.models import ActualTimeSegment
        first_start = timezone.now() - timedelta(hours=2)
        ActualTimeSegment.objects.create(event=self.event, start=first_start, end=first_start + timedelta(hours=1))
        ActualTimeSegment.objects.create(event=self.event, start=timezone.now() - timedelta(minutes=10), end=None)
        self.assertEqual(self.event.actual_start, first_start)

    def test_actual_end_property_returns_last_closed_segment_end(self):
        """actual_end property returns the end time of the last closed segment."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=2),
            end=now - timedelta(hours=1),
        )
        last_end = now - timedelta(minutes=5)
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(minutes=30),
            end=last_end,
        )
        self.assertEqual(self.event.actual_end, last_end)

    def test_actual_start_none_when_no_segments(self):
        """actual_start returns None when no segments exist."""
        self.assertIsNone(self.event.actual_start)

    def test_actual_end_none_when_no_closed_segments(self):
        """actual_end returns None when no closed segments exist."""
        from cal.models import ActualTimeSegment
        ActualTimeSegment.objects.create(event=self.event, start=timezone.now(), end=None)
        self.assertIsNone(self.event.actual_end)

    def test_play_pause_play_stop_lifecycle(self):
        """Full play/pause/play/stop lifecycle produces correct segment state."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        # Play
        seg1 = ActualTimeSegment.objects.create(event=self.event, start=now - timedelta(minutes=60), end=None)
        # Pause (close segment 1)
        seg1.end = now - timedelta(minutes=30)
        seg1.save()
        # Play again
        seg2 = ActualTimeSegment.objects.create(event=self.event, start=now - timedelta(minutes=20), end=None)
        # Stop (close segment 2 + mark stopped)
        seg2.end = now
        seg2.save()
        self.event.is_stopped = True
        self.event.save()

        self.event.refresh_from_db()
        self.assertTrue(self.event.is_stopped)
        self.assertIsNone(self.event.current_segment)
        # 30 min + 20 min = 50 min = 3000 seconds
        self.assertEqual(self.event.total_actual_seconds, 3000)
        self.assertEqual(self.event.actual_start, now - timedelta(minutes=60))
        self.assertEqual(self.event.actual_end, now)


# ── Task 2: Asset.is_active ──────────────────────────────────────────────────

class AssetIsActiveFieldTest(TestCase):
    """Tests for the new Asset.is_active boolean field."""

    def test_asset_is_active_defaults_false(self):
        """New track asset must have is_active=False by default."""
        track = Asset.objects.create(name='Active Test Track', asset_type=Asset.AssetType.TRACK)
        self.assertFalse(track.is_active)

    def test_vehicle_is_active_defaults_false(self):
        """Non-track assets also default to is_active=False."""
        vehicle = Asset.objects.create(name='Test Vehicle', asset_type=Asset.AssetType.VEHICLE)
        self.assertFalse(vehicle.is_active)

    def test_can_set_is_active_true(self):
        """is_active can be set to True and persists."""
        track = Asset.objects.create(name='Active Track', asset_type=Asset.AssetType.TRACK)
        track.is_active = True
        track.save()
        track.refresh_from_db()
        self.assertTrue(track.is_active)


class TrackActiveToggleAPITest(TestCase):
    """Tests for POST /cal/api/track/<id>/active/ toggle endpoint."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='active_admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='active_user', password='Testpass123!'
        )
        self.track = Asset.objects.create(name='Toggle Track', asset_type=Asset.AssetType.TRACK)
        self.url = reverse('cal:track_active_toggle', args=[self.track.pk])

    def test_admin_can_toggle_active_on(self):
        """Admin POST sets is_active=True on an inactive track."""
        self.client.login(username='active_admin', password='Testpass123!')
        resp = self.client.post(self.url, content_type='application/json', data=json.dumps({}))
        self.assertEqual(resp.status_code, 200)
        self.track.refresh_from_db()
        self.assertTrue(self.track.is_active)

    def test_admin_can_toggle_active_off(self):
        """Admin POST toggles is_active=False on an active track."""
        self.track.is_active = True
        self.track.save()
        self.client.login(username='active_admin', password='Testpass123!')
        resp = self.client.post(self.url, content_type='application/json', data=json.dumps({}))
        self.assertEqual(resp.status_code, 200)
        self.track.refresh_from_db()
        self.assertFalse(self.track.is_active)

    def test_non_admin_gets_403(self):
        """Non-admin user POST to toggle endpoint returns 403."""
        self.client.login(username='active_user', password='Testpass123!')
        resp = self.client.post(self.url, content_type='application/json', data=json.dumps({}))
        self.assertEqual(resp.status_code, 403)

    def test_non_track_asset_rejected(self):
        """Toggling active state on a non-track asset returns 400 or 404."""
        vehicle = Asset.objects.create(name='Test Vehicle', asset_type=Asset.AssetType.VEHICLE)
        url = reverse('cal:track_active_toggle', args=[vehicle.pk])
        self.client.login(username='active_admin', password='Testpass123!')
        resp = self.client.post(url, content_type='application/json', data=json.dumps({}))
        self.assertIn(resp.status_code, [400, 404])

    def test_dashboard_api_includes_is_active(self):
        """Dashboard API response includes is_active field for each track."""
        self.track.is_active = True
        self.track.save()
        self.client.login(username='active_admin', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        data = resp.json()
        track_data = data['tracks'].get('Toggle Track', {})
        self.assertIn('is_active', track_data)
        self.assertTrue(track_data['is_active'])

    def test_subtrack_toggle_also_works(self):
        """Toggle API works for subtracks as well as parent tracks."""
        parent = Asset.objects.create(name='Parent Track', asset_type=Asset.AssetType.TRACK)
        sub = Asset.objects.create(name='Sub North', asset_type=Asset.AssetType.TRACK, parent=parent)
        url = reverse('cal:track_active_toggle', args=[sub.pk])
        self.client.login(username='active_admin', password='Testpass123!')
        resp = self.client.post(url, content_type='application/json', data=json.dumps({}))
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)


# ── Task 3: Event.is_impromptu ───────────────────────────────────────────────

class EventIsImpromptyFieldTest(TestCase):
    """Tests for the new Event.is_impromptu boolean field."""

    def setUp(self):
        self.user = User.objects.create_user(username='impro_user', password='Testpass123!')
        now = timezone.now()
        self.event = Event.objects.create(
            title='Impromptu Test',
            description='',
            start_time=now,
            end_time=now + timedelta(hours=1),
            created_by=self.user,
        )

    def test_is_impromptu_defaults_false(self):
        """Event.is_impromptu defaults to False."""
        self.assertFalse(self.event.is_impromptu)

    def test_is_impromptu_can_be_set_true(self):
        """is_impromptu can be set to True and persists."""
        self.event.is_impromptu = True
        self.event.save()
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_impromptu)


# ── Task 4: All events default unapproved (remove admin auto-approve) ─────────
# NOTE: These tests REPLACE existing EventAutoApprovalTest.test_staff_created_event_is_auto_approved
# The existing test for staff auto-approve will need to be updated/removed once task 4 ships.

class AdminEventNoLongerAutoApprovedTest(TestCase):
    """Task 4: Admin-created events must default to is_approved=False (no auto-approve)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='task4_admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='task4_user', password='Testpass123!')
        self.asset = Asset.objects.create(name='Task4 Track', asset_type=Asset.AssetType.TRACK)
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def _post_data(self, title='Task4 Event'):
        return {
            'title': title,
            'description': '',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.asset.pk],
        }

    def test_admin_creates_event_gets_unapproved(self):
        """Admin user POSTs to cal:event_new -> event.is_approved is False (task 4 change)."""
        self.client.login(username='task4_admin', password='Testpass123!')
        resp = self.client.post(reverse('cal:event_new'), self._post_data('Admin Task4 Event'))
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Admin Task4 Event')
        self.assertFalse(event.is_approved, 'Admin event should NOT be auto-approved in v1.1')

    def test_regular_user_creates_event_still_unapproved(self):
        """Regular user event remains unapproved (unchanged behavior)."""
        self.client.login(username='task4_user', password='Testpass123!')
        resp = self.client.post(reverse('cal:event_new'), self._post_data('User Task4 Event'))
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='User Task4 Event')
        self.assertFalse(event.is_approved)

    def test_approve_workflow_still_works(self):
        """Admin can still explicitly approve an event via event_approve."""
        event = Event.objects.create(
            title='To Approve',
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.regular,
            is_approved=False,
        )
        self.client.login(username='task4_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[event.pk])
        resp = self.client.post(url)
        event.refresh_from_db()
        self.assertTrue(event.is_approved)

    def test_unapprove_workflow_still_works(self):
        """Admin can still unapprove an approved event."""
        event = Event.objects.create(
            title='To Unapprove',
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.regular,
            is_approved=True,
        )
        self.client.login(username='task4_admin', password='Testpass123!')
        url = reverse('cal:event_unapprove', args=[event.pk])
        resp = self.client.post(url)
        event.refresh_from_db()
        self.assertFalse(event.is_approved)


# ── Task 5: Conflict Detection Overhaul ──────────────────────────────────────

class ConflictDetectionOverhaulTest(TestCase):
    """
    Task 5: Conflict detection now allows overlapping unapproved events.
    - Two unapproved events on same track/time: both save (no hard block)
    - Approved + new unapproved on same track/time: saves with warning
    - Hard-block approval if conflicts with another approved event
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='conflict_admin', password='Testpass123!', is_staff=True
        )
        self.user = User.objects.create_user(username='conflict_user', password='Testpass123!')
        self.track = Asset.objects.create(name='Conflict Track', asset_type=Asset.AssetType.TRACK)
        self.parent = Asset.objects.create(name='Conflict Parent', asset_type=Asset.AssetType.TRACK)
        self.sub_a = Asset.objects.create(
            name='Sub A', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_b = Asset.objects.create(
            name='Sub B', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.start = datetime(2027, 6, 1, 9, 0, tzinfo=_local_tz)
        self.end = datetime(2027, 6, 1, 11, 0, tzinfo=_local_tz)

    def _make_event(self, asset, title='Existing', approved=True):
        ev = Event.objects.create(
            title=title,
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.admin,
            is_approved=approved,
        )
        ev.assets.add(asset)
        return ev

    def _form_data(self, asset, title='New Event'):
        return {
            'title': title,
            'description': '',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [asset.pk],
        }

    def test_two_unapproved_events_same_track_both_save(self):
        """Two unapproved events on the same track/time must both save (no hard block)."""
        self._make_event(self.track, 'Unapproved First', approved=False)
        form = EventForm(data=self._form_data(self.track, 'Unapproved Second'))
        # Should be valid — unapproved-vs-unapproved is not a hard block
        self.assertTrue(form.is_valid(), f'Unapproved conflicts should be allowed. Errors: {form.errors}')

    def test_unapproved_event_over_approved_saves_with_warning(self):
        """Unapproved event overlapping an approved one saves but triggers a warning."""
        self._make_event(self.track, 'Approved Existing', approved=True)
        form = EventForm(data=self._form_data(self.track, 'New Unapproved'))
        # Should be valid (saves), but may set a warning flag or non-field error
        # The key behavior: the form does NOT hard-block submission
        self.assertTrue(form.is_valid(), f'Unapproved event over approved should save with warning. Errors: {form.errors}')

    def test_approve_blocked_when_approved_conflict_exists(self):
        """Approving an event must fail if another approved event occupies the same slot."""
        self._make_event(self.track, 'Already Approved', approved=True)
        pending = self._make_event(self.track, 'Pending Event', approved=False)
        self.client.login(username='conflict_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[pending.pk])
        resp = self.client.post(url)
        pending.refresh_from_db()
        # Must NOT have been approved
        self.assertFalse(pending.is_approved, 'Approval should be blocked due to conflict')

    def test_approve_blocked_response_includes_conflicting_event_name(self):
        """Approve failure response or redirect must communicate the conflicting event name."""
        approved = self._make_event(self.track, 'Blocking Event', approved=True)
        pending = self._make_event(self.track, 'Blocked Pending', approved=False)
        self.client.login(username='conflict_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[pending.pk])
        resp = self.client.post(url, follow=True)
        # Response content should reference the conflicting event title
        self.assertContains(resp, 'Blocking Event')

    def test_approve_succeeds_when_no_approved_conflict(self):
        """Approving an event succeeds when no approved events conflict."""
        pending = self._make_event(self.track, 'Clean Pending', approved=False)
        self.client.login(username='conflict_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[pending.pk])
        resp = self.client.post(url)
        pending.refresh_from_db()
        self.assertTrue(pending.is_approved)

    def test_conflict_check_respects_subtrack_parent_rule(self):
        """Approving a subtrack event is blocked if parent track is approved in same slot."""
        self._make_event(self.parent, 'Parent Approved', approved=True)
        pending = self._make_event(self.sub_a, 'Sub Pending', approved=False)
        self.client.login(username='conflict_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[pending.pk])
        resp = self.client.post(url)
        pending.refresh_from_db()
        self.assertFalse(pending.is_approved, 'Subtrack approval blocked by parent conflict')

    def test_sibling_subtracks_dont_block_each_other_on_approve(self):
        """Approving sub_a is not blocked by an approved event on sibling sub_b."""
        self._make_event(self.sub_b, 'Sub B Approved', approved=True)
        pending = self._make_event(self.sub_a, 'Sub A Pending', approved=False)
        self.client.login(username='conflict_admin', password='Testpass123!')
        url = reverse('cal:event_approve', args=[pending.pk])
        resp = self.client.post(url)
        pending.refresh_from_db()
        self.assertTrue(pending.is_approved, 'Sibling subtracks should not block each other')

    def test_get_asset_conflicts_utility_exists(self):
        """get_asset_conflicts() utility function exists and returns correct conflicts."""
        from cal.utils import get_asset_conflicts
        approved = self._make_event(self.track, 'Conflict Source', approved=True)
        conflicts = get_asset_conflicts(self.track, self.start, self.end, approved_only=True)
        self.assertIn(approved, list(conflicts))

    def test_get_asset_conflicts_excludes_unapproved_when_approved_only(self):
        """get_asset_conflicts(approved_only=True) excludes unapproved events."""
        from cal.utils import get_asset_conflicts
        self._make_event(self.track, 'Unapproved Event', approved=False)
        conflicts = get_asset_conflicts(self.track, self.start, self.end, approved_only=True)
        self.assertEqual(list(conflicts), [])


# ── Task 6 & Task 2: Dashboard Active/Inactive Toggle ────────────────────────

class DashboardActiveToggleAPITest(TestCase):
    """Dashboard: toggle track active/inactive state via API."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='dash_active_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='Dashboard Active Track', asset_type=Asset.AssetType.TRACK)
        self.url = reverse('cal:track_active_toggle', args=[self.track.pk])
        self.client.login(username='dash_active_admin', password='Testpass123!')

    def test_toggle_sets_is_active_true(self):
        """Toggling an inactive track sets is_active=True."""
        resp = self.client.post(self.url, content_type='application/json', data=json.dumps({}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('is_active'))

    def test_toggle_response_includes_id_and_is_active(self):
        """Toggle response JSON includes id and is_active."""
        resp = self.client.post(self.url, content_type='application/json', data=json.dumps({}))
        data = resp.json()
        self.assertIn('id', data)
        self.assertIn('is_active', data)

    def test_dashboard_api_is_active_false_by_default(self):
        """Dashboard API returns is_active=False for tracks that haven't been toggled."""
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        data = resp.json()
        track_data = data['tracks'].get('Dashboard Active Track', {})
        self.assertIn('is_active', track_data)
        self.assertFalse(track_data['is_active'])


# ── Task 7: Quick Approve on Dashboard ──────────────────────────────────────

class DashboardQuickApproveTest(TestCase):
    """Dashboard: Approve button for unapproved events checks for conflicts."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='qa_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='QA Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.pending_event = Event.objects.create(
            title='Quick Approve Event',
            description='',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            is_approved=False,
            created_by=self.admin,
        )
        self.pending_event.assets.add(self.track)
        self.client.login(username='qa_admin', password='Testpass123!')

    def test_approve_event_with_no_conflicts_succeeds(self):
        """Approving an event via event_approve with no conflicts succeeds."""
        url = reverse('cal:event_approve', args=[self.pending_event.pk])
        resp = self.client.post(url)
        self.pending_event.refresh_from_db()
        self.assertTrue(self.pending_event.is_approved)

    def test_approve_blocked_if_approved_conflict(self):
        """Approving fails if an already-approved event conflicts."""
        conflict = Event.objects.create(
            title='Existing Approved',
            description='',
            start_time=self.pending_event.start_time,
            end_time=self.pending_event.end_time,
            is_approved=True,
            created_by=self.admin,
        )
        conflict.assets.add(self.track)
        url = reverse('cal:event_approve', args=[self.pending_event.pk])
        resp = self.client.post(url, follow=True)
        self.pending_event.refresh_from_db()
        self.assertFalse(self.pending_event.is_approved)

    def test_approve_error_response_names_conflicting_event(self):
        """Error message after failed approval includes the conflicting event title."""
        conflict = Event.objects.create(
            title='Blocking Approved Event',
            description='',
            start_time=self.pending_event.start_time,
            end_time=self.pending_event.end_time,
            is_approved=True,
            created_by=self.admin,
        )
        conflict.assets.add(self.track)
        url = reverse('cal:event_approve', args=[self.pending_event.pk])
        resp = self.client.post(url, follow=True)
        self.assertContains(resp, 'Blocking Approved Event')


# ── Task 8: Play/Pause/Stop Controls ────────────────────────────────────────

class PlayPauseStopAPITest(TestCase):
    """Tests for the new play/pause/stop/clear actions on the stamp API."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='pps_admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='pps_user', password='Testpass123!')
        self.track = Asset.objects.create(name='PPS Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.event = Event.objects.create(
            title='PPS Test Event',
            description='',
            start_time=now,
            end_time=now + timedelta(hours=4),
            is_approved=True,
            created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.url = reverse('cal:dashboard_stamp_actual', args=[self.event.pk])
        self.client.login(username='pps_admin', password='Testpass123!')

    def _post(self, action, time=None):
        body = {'action': action}
        if time is not None:
            body['time'] = time
        return self.client.post(
            self.url, data=json.dumps(body), content_type='application/json'
        )

    def test_play_creates_open_segment(self):
        """play action creates an ActualTimeSegment with start=now, end=None."""
        from cal.models import ActualTimeSegment
        resp = self._post('play')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.event.segments.count(), 1)
        seg = self.event.segments.first()
        self.assertIsNone(seg.end)

    def test_play_fails_if_open_segment_exists(self):
        """play action returns 400 if an open segment already exists."""
        self._post('play')  # first play
        resp = self._post('play')  # second play
        self.assertEqual(resp.status_code, 400)

    def test_play_fails_if_is_stopped(self):
        """play action returns 400 if event.is_stopped=True."""
        self.event.is_stopped = True
        self.event.save()
        resp = self._post('play')
        self.assertEqual(resp.status_code, 400)

    def test_pause_closes_open_segment(self):
        """pause action sets end on the currently open segment."""
        from cal.models import ActualTimeSegment
        self._post('play')
        resp = self._post('pause')
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        seg = self.event.segments.first()
        self.assertIsNotNone(seg.end)

    def test_pause_fails_if_no_open_segment(self):
        """pause action returns 400 if no open segment exists."""
        resp = self._post('pause')
        self.assertEqual(resp.status_code, 400)

    def test_stop_closes_segment_and_sets_is_stopped(self):
        """stop action closes current segment and sets event.is_stopped=True."""
        self._post('play')
        resp = self._post('stop')
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_stopped)
        self.assertIsNone(self.event.current_segment)

    def test_stop_fails_if_no_open_segment(self):
        """stop action returns 400 if no open segment exists."""
        resp = self._post('stop')
        self.assertEqual(resp.status_code, 400)

    def test_clear_deletes_all_segments_and_resets_is_stopped(self):
        """clear action deletes all segments and sets is_stopped=False."""
        from cal.models import ActualTimeSegment
        self._post('play')
        self._post('stop')
        resp = self._post('clear')
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_stopped)
        self.assertEqual(self.event.segments.count(), 0)

    def test_play_with_custom_time(self):
        """play with custom ISO time parameter uses that time as segment start."""
        custom_time = (timezone.now() - timedelta(minutes=15)).isoformat()
        resp = self._post('play', time=custom_time)
        self.assertEqual(resp.status_code, 200)
        seg = self.event.segments.first()
        # The segment start should be close to custom_time
        from django.utils.dateparse import parse_datetime
        expected = parse_datetime(custom_time)
        self.assertAlmostEqual(
            seg.start.timestamp(), expected.timestamp(), delta=5
        )

    def test_pause_with_custom_time(self):
        """pause with custom ISO time parameter closes segment at that time."""
        self._post('play')
        custom_time = timezone.now().isoformat()
        resp = self._post('pause', time=custom_time)
        self.assertEqual(resp.status_code, 200)
        seg = self.event.segments.first()
        self.assertIsNotNone(seg.end)

    def test_non_admin_gets_403(self):
        """Non-admin POST to stamp endpoint returns 403."""
        self.client.logout()
        self.client.login(username='pps_user', password='Testpass123!')
        resp = self._post('play')
        self.assertEqual(resp.status_code, 403)

    def test_full_play_pause_play_stop_lifecycle(self):
        """Full lifecycle: play → pause → play → stop produces 2 closed segments."""
        self._post('play')
        self._post('pause')
        self._post('play')
        resp = self._post('stop')
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_stopped)
        self.assertEqual(self.event.segments.count(), 2)
        for seg in self.event.segments.all():
            self.assertIsNotNone(seg.end)

    def test_response_includes_segments(self):
        """Stamp API response includes current segment data."""
        resp = self._post('play')
        data = resp.json()
        self.assertIn('segments', data)

    def test_response_includes_is_stopped(self):
        """Stamp API response includes is_stopped field."""
        resp = self._post('play')
        data = resp.json()
        self.assertIn('is_stopped', data)


# ── Task 10: Dashboard API Changes ──────────────────────────────────────────

class DashboardAPIV11Test(TestCase):
    """Task 10: Dashboard API returns all events (not just approved), includes new fields."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='api11_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='API11 Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.approved_event = Event.objects.create(
            title='Approved Event',
            description='',
            start_time=now.replace(hour=10, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=12, minute=0, second=0, microsecond=0),
            is_approved=True,
            created_by=self.admin,
        )
        self.approved_event.assets.add(self.track)
        self.unapproved_event = Event.objects.create(
            title='Unapproved Event',
            description='',
            start_time=now.replace(hour=14, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=16, minute=0, second=0, microsecond=0),
            is_approved=False,
            created_by=self.admin,
        )
        self.unapproved_event.assets.add(self.track)
        self.url = reverse('cal:dashboard_events_api')
        self.client.login(username='api11_admin', password='Testpass123!')

    def test_unapproved_events_included_in_response(self):
        """Dashboard API returns unapproved events alongside approved ones."""
        resp = self.client.get(self.url, {'date': timezone.now().date().isoformat()})
        data = resp.json()
        track_data = data['tracks'].get('API11 Track', {})
        event_titles = [e['title'] for e in track_data.get('events', [])]
        self.assertIn('Unapproved Event', event_titles)

    def test_response_includes_is_impromptu_on_events(self):
        """Each event in the API response includes is_impromptu field."""
        resp = self.client.get(self.url, {'date': timezone.now().date().isoformat()})
        data = resp.json()
        track_data = data['tracks'].get('API11 Track', {})
        for ev in track_data.get('events', []):
            self.assertIn('is_impromptu', ev, f"Event {ev['title']} missing is_impromptu")

    def test_response_includes_segments_on_events(self):
        """Each event in the API response includes segments list."""
        resp = self.client.get(self.url, {'date': timezone.now().date().isoformat()})
        data = resp.json()
        track_data = data['tracks'].get('API11 Track', {})
        for ev in track_data.get('events', []):
            self.assertIn('segments', ev, f"Event {ev['title']} missing segments")

    def test_response_includes_is_stopped_on_events(self):
        """Each event in the API response includes is_stopped field."""
        resp = self.client.get(self.url, {'date': timezone.now().date().isoformat()})
        data = resp.json()
        track_data = data['tracks'].get('API11 Track', {})
        for ev in track_data.get('events', []):
            self.assertIn('is_stopped', ev, f"Event {ev['title']} missing is_stopped")

    def test_response_is_active_field_present_on_tracks(self):
        """Dashboard API includes is_active on track objects."""
        resp = self.client.get(self.url)
        data = resp.json()
        track_data = data['tracks'].get('API11 Track', {})
        self.assertIn('is_active', track_data)


# ── Task 13: Delete Redirect Bug Fix ────────────────────────────────────────

class DeleteRedirectTest(TestCase):
    """Task 13: Delete event respects ?next= parameter for redirect."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='del_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='Delete Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.event = Event.objects.create(
            title='To Delete',
            description='',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            is_approved=True,
            created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.client.login(username='del_admin', password='Testpass123!')

    def _fresh_event(self, title='Fresh Delete'):
        now = timezone.now()
        ev = Event.objects.create(
            title=title, description='',
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1) + timedelta(hours=2),
            is_approved=True, created_by=self.admin,
        )
        ev.assets.add(self.track)
        return ev

    def test_delete_with_next_dashboard_redirects_to_dashboard(self):
        """DELETE with ?next=/cal/dashboard/ must redirect to dashboard."""
        ev = self._fresh_event('Dashboard Delete')
        url = reverse('cal:event_delete', args=[ev.pk]) + '?next=/cal/dashboard/'
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/cal/dashboard/')

    def test_delete_with_next_calendar_redirects_to_calendar(self):
        """DELETE with ?next=/cal/calendar/ must redirect to calendar."""
        ev = self._fresh_event('Calendar Delete')
        url = reverse('cal:event_delete', args=[ev.pk]) + '?next=/cal/calendar/'
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/cal/calendar/')

    def test_delete_with_no_next_redirects_to_calendar(self):
        """DELETE with no ?next= defaults to calendar."""
        ev = self._fresh_event('Default Delete')
        url = reverse('cal:event_delete', args=[ev.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/cal/calendar/', resp['Location'])

    def test_approve_with_next_dashboard_redirects_correctly(self):
        """Approve with ?next=/cal/dashboard/ redirects to dashboard."""
        ev = self._fresh_event('Approve Redirect')
        ev.is_approved = False
        ev.save()
        url = reverse('cal:event_approve', args=[ev.pk])
        resp = self.client.post(url, {'next': '/cal/dashboard/'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/cal/dashboard/')

    def test_unapprove_with_next_dashboard_redirects_correctly(self):
        """Unapprove with ?next=/cal/dashboard/ redirects to dashboard."""
        ev = self._fresh_event('Unapprove Redirect')
        url = reverse('cal:event_unapprove', args=[ev.pk])
        resp = self.client.post(url, {'next': '/cal/dashboard/'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/cal/dashboard/')

    def test_delete_with_external_next_falls_back_to_calendar(self):
        """DELETE with external next= URL falls back to calendar (open redirect protection)."""
        ev = self._fresh_event('External Redirect Delete')
        url = reverse('cal:event_delete', args=[ev.pk]) + '?next=http://evil.com'
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp['Location'])


# ── Task 14: Impromptu Event Creation ────────────────────────────────────────

class QuickEventCreateAPITest(TestCase):
    """POST /cal/api/event/create/ — impromptu and scheduled event creation."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='impro_admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='impro_reg', password='Testpass123!')
        self.track = Asset.objects.create(name='Impro Track', asset_type=Asset.AssetType.TRACK)
        self.url = reverse('cal:api_event_create')
        self.client.login(username='impro_admin', password='Testpass123!')

    def _post(self, data):
        return self.client.post(
            self.url, data=json.dumps(data), content_type='application/json'
        )

    def _impromptu_payload(self):
        return {
            'title': 'Quick Test Run',
            'asset_ids': [self.track.pk],
            'is_impromptu': True,
        }

    def _scheduled_payload(self):
        now = timezone.now()
        return {
            'title': 'Scheduled Test Run',
            'asset_ids': [self.track.pk],
            'start_time': now.isoformat(),
            'end_time': (now + timedelta(hours=2)).isoformat(),
        }

    def test_create_impromptu_returns_201(self):
        """Creating an impromptu event returns 201."""
        resp = self._post(self._impromptu_payload())
        self.assertEqual(resp.status_code, 201)

    def test_impromptu_event_is_impromptu_and_approved(self):
        """Impromptu event has is_impromptu=True and is_approved=True."""
        resp = self._post(self._impromptu_payload())
        self.assertEqual(resp.status_code, 201)
        ev = Event.objects.get(title='Quick Test Run')
        self.assertTrue(ev.is_impromptu)
        self.assertTrue(ev.is_approved)

    def test_impromptu_event_opens_segment(self):
        """Impromptu event auto-opens an ActualTimeSegment."""
        from cal.models import ActualTimeSegment
        resp = self._post(self._impromptu_payload())
        self.assertEqual(resp.status_code, 201)
        ev = Event.objects.get(title='Quick Test Run')
        segs = ActualTimeSegment.objects.filter(event=ev)
        self.assertEqual(segs.count(), 1)
        self.assertIsNone(segs.first().end)

    def test_created_event_has_correct_track(self):
        """Created event is linked to the specified track."""
        resp = self._post(self._impromptu_payload())
        self.assertEqual(resp.status_code, 201)
        ev = Event.objects.get(title='Quick Test Run')
        self.assertIn(self.track, ev.assets.all())

    def test_scheduled_event_with_conflicts_returns_400(self):
        """Scheduled event with conflicts returns 400 with error."""
        now = timezone.now()
        blocking = Event.objects.create(
            title='Blocking Event', description='',
            start_time=now,
            end_time=now + timedelta(hours=2),
            is_approved=True, created_by=self.admin,
        )
        blocking.assets.add(self.track)
        resp = self._post(self._scheduled_payload())
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertIn('error', data)
        self.assertFalse(Event.objects.filter(title='Scheduled Test Run').exists())

    def test_scheduled_event_no_conflicts_returns_201(self):
        """Scheduled event with no conflicts returns 201."""
        resp = self._post(self._scheduled_payload())
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Event.objects.filter(title='Scheduled Test Run').exists())

    def test_non_admin_gets_403(self):
        """Non-admin POST returns 403."""
        self.client.logout()
        self.client.login(username='impro_reg', password='Testpass123!')
        resp = self._post(self._impromptu_payload())
        self.assertEqual(resp.status_code, 403)

    def test_missing_title_returns_400(self):
        """Missing title returns 400."""
        resp = self._post({'asset_ids': [self.track.pk], 'is_impromptu': True})
        self.assertEqual(resp.status_code, 400)

    def test_missing_assets_returns_400(self):
        """Missing asset_ids returns 400."""
        resp = self._post({'title': 'No Assets', 'is_impromptu': True})
        self.assertEqual(resp.status_code, 400)

    def test_invalid_asset_id_returns_400(self):
        """Invalid asset ID returns 400."""
        resp = self._post({
            'title': 'Bad Asset',
            'asset_ids': [99999],
            'is_impromptu': True,
        })
        self.assertEqual(resp.status_code, 400)

    def test_scheduled_missing_times_returns_400(self):
        """Scheduled event without start/end times returns 400."""
        resp = self._post({
            'title': 'No Times',
            'asset_ids': [self.track.pk],
        })
        self.assertEqual(resp.status_code, 400)

    def test_invalid_datetime_returns_400(self):
        """Invalid datetime string returns 400."""
        resp = self._post({
            'title': 'Bad Time',
            'asset_ids': [self.track.pk],
            'start_time': 'not-a-datetime',
            'end_time': 'also-not-a-datetime',
        })
        self.assertEqual(resp.status_code, 400)


# ── Task 15: Event View Segment Display ─────────────────────────────────────

class EventViewSegmentDisplayTest(TestCase):
    """Task 15: Event detail/edit page displays actual time segments read-only."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='seg_view_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='Seg View Track', asset_type=Asset.AssetType.TRACK)
        now = timezone.now()
        self.event = Event.objects.create(
            title='Segment Display Event',
            description='',
            start_time=now,
            end_time=now + timedelta(hours=2),
            is_approved=True,
            created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.client.login(username='seg_view_admin', password='Testpass123!')

    def test_event_detail_context_includes_segments(self):
        """Event edit/detail view context includes segments data."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=1),
            end=now,
        )
        url = reverse('cal:event_edit', args=[self.event.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('segments', resp.context)

    def test_event_detail_renders_segment_times(self):
        """Event detail page renders segment start/end times in the HTML."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        seg = ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=1),
            end=now,
        )
        url = reverse('cal:event_edit', args=[self.event.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Page should contain some representation of the segment
        content = resp.content.decode()
        self.assertIn('actual-segment', content)

    def test_event_detail_no_segments_shows_no_segment_markup(self):
        """Event with no segments does not show segment markup."""
        url = reverse('cal:event_edit', args=[self.event.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn('actual-segment', content)


# ════════════════════════════════════════════════════════════════════════════════
# Gantt Redesign: Event State Classification, Bar Rendering, Legend, CSS
# (TDD — these tests are written BEFORE implementation and should fail initially)
# ════════════════════════════════════════════════════════════════════════════════

import re as _re
from datetime import timezone as _dt_tz


class GanttEventClassificationTest(TestCase):
    """
    Tests for _event_classes() returning the correct state classes for the
    new operational axis: event-completed, event-noshow, and the updated
    event-pending handling.

    All tests exercise Calendar._event_classes() directly by constructing
    a Calendar instance and calling the method with a crafted Event object.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='cls_user', password='Testpass123!')
        self.track = Asset.objects.create(name='Cls Track', asset_type=Asset.AssetType.TRACK)
        # Import Calendar locally to keep the import at the top of the test suite.
        from cal.utils import Calendar
        self.cal = Calendar(2026, 4)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_event(self, *, approved, start_offset_hours, duration_hours=2):
        """Return an unsaved Event with start relative to now by offset hours."""
        now = timezone.now().replace(second=0, microsecond=0)
        start = now + timedelta(hours=start_offset_hours)
        end = start + timedelta(hours=duration_hours)
        ev = Event(
            title='Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=approved,
        )
        ev.save()
        ev.assets.add(self.track)
        return ev

    def _add_segment(self, event, *, open_segment=False, start_offset_hours=-2):
        """Attach a closed (or open) ActualTimeSegment to event."""
        from cal.models import ActualTimeSegment
        now = timezone.now()
        seg_start = now + timedelta(hours=start_offset_hours)
        seg_end = None if open_segment else now + timedelta(hours=start_offset_hours + 1)
        return ActualTimeSegment.objects.create(event=event, start=seg_start, end=seg_end)

    # ── a) Approved upcoming event → no special operational state class ───────

    def test_approved_upcoming_no_operational_state_class(self):
        """Approved future event should not carry event-completed or event-noshow."""
        ev = self._make_event(approved=True, start_offset_hours=2)
        classes = self.cal._event_classes(ev)
        self.assertNotIn('event-completed', classes)
        self.assertNotIn('event-noshow', classes)
        self.assertNotIn('event-pending', classes)

    # ── b) Approved past event WITH segments → event-completed ───────────────

    def test_approved_past_with_segments_is_completed(self):
        """Approved event in the past that has segments must get event-completed."""
        ev = self._make_event(approved=True, start_offset_hours=-4, duration_hours=2)
        self._add_segment(ev, start_offset_hours=-3)
        ev.refresh_from_db()
        classes = self.cal._event_classes(ev)
        self.assertIn('event-completed', classes)
        self.assertNotIn('event-noshow', classes)

    # ── c) Approved past event WITHOUT segments → event-noshow ───────────────

    def test_approved_past_without_segments_is_noshow(self):
        """Approved event whose start time has passed and has no segments is a no-show."""
        ev = self._make_event(approved=True, start_offset_hours=-4, duration_hours=2)
        # No segments added
        classes = self.cal._event_classes(ev)
        self.assertIn('event-noshow', classes)
        self.assertNotIn('event-completed', classes)

    # ── d) Approved future event WITH segments (active right now) → not noshow ─

    def test_approved_active_event_is_not_noshow(self):
        """An event whose scheduled window spans now and has an open segment is active, not noshow."""
        ev = self._make_event(approved=True, start_offset_hours=-1, duration_hours=3)
        self._add_segment(ev, open_segment=True, start_offset_hours=-1)
        ev.refresh_from_db()
        classes = self.cal._event_classes(ev)
        self.assertNotIn('event-noshow', classes)

    # ── e) Pending event → event-pending ─────────────────────────────────────

    def test_pending_event_has_pending_class(self):
        """Unapproved upcoming event must have event-pending and nothing else operational."""
        ev = self._make_event(approved=False, start_offset_hours=2)
        classes = self.cal._event_classes(ev)
        self.assertIn('event-pending', classes)
        self.assertNotIn('event-completed', classes)
        self.assertNotIn('event-noshow', classes)

    # ── f) Pending expired event → still event-pending ───────────────────────

    def test_pending_expired_event_still_has_pending_class(self):
        """Unapproved event whose window has passed is still event-pending (never activated)."""
        ev = self._make_event(approved=False, start_offset_hours=-6, duration_hours=2)
        classes = self.cal._event_classes(ev)
        self.assertIn('event-pending', classes)

    # ── g) event-completed implies NOT event-noshow ───────────────────────────

    def test_completed_and_noshow_are_mutually_exclusive(self):
        """An event cannot be both completed and noshow."""
        ev = self._make_event(approved=True, start_offset_hours=-4, duration_hours=2)
        self._add_segment(ev, start_offset_hours=-3)
        ev.refresh_from_db()
        classes = self.cal._event_classes(ev)
        self.assertFalse(
            'event-completed' in classes and 'event-noshow' in classes,
            f'Both completed and noshow in classes: {classes!r}',
        )


class GanttBlockRenderingTest(TestCase):
    """
    Tests for _make_block() HTML output under the new design.

    Verifies:
    - Pending blocks do NOT carry type color classes (event-track etc.) in Gantt
    - Scheduled ghost bar uses opacity 0.4 when segments exist
    - Active segment carries gantt-block--active-segment + data-segment-start
    - Completed event block carries event-completed class
    - No-show event block carries event-noshow class
    - Pause gap carries gantt-block--pause-gap
    - Dead CSS type classes (event-track / event-vehicle etc.) are absent from
      Gantt block HTML (inline background is used instead)
    """

    def setUp(self):
        self.user = User.objects.create_user(username='blk_user', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(
            name='Render Track', asset_type=Asset.AssetType.TRACK, color='#dc2626'
        )

    def _day_html(self, date_str='2026-4-1'):
        resp = self.client.get(reverse('cal:calendar') + f'?view=day&date={date_str}')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _make_event(self, *, title, approved, start, end):
        ev = Event.objects.create(
            title=title, description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=approved,
        )
        ev.assets.add(self.track)
        return ev

    def _add_segment(self, event, seg_start, seg_end=None):
        from cal.models import ActualTimeSegment
        return ActualTimeSegment.objects.create(event=event, start=seg_start, end=seg_end)

    # ── Dead-code removal: type classes absent from Gantt HTML ────────────────

    def test_gantt_block_does_not_contain_event_track_class(self):
        """Gantt blocks must NOT carry event-track class (overridden by inline bg)."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        self._make_event(title='Track Class Test', approved=True, start=start, end=end)
        html = self._day_html()
        # gantt-block anchors should not carry event-track
        for m in _re.finditer(r'class="gantt-block([^"]*)"', html):
            classes = m.group(1)
            self.assertNotIn('event-track', classes,
                             'event-track found on a gantt-block element')

    def test_gantt_block_does_not_contain_event_vehicle_class(self):
        """Gantt blocks must NOT carry event-vehicle class."""
        vehicle = Asset.objects.create(name='Van', asset_type=Asset.AssetType.VEHICLE)
        start = datetime(2026, 4, 1, 10, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 12, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Vehicle Class Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(vehicle)
        html = self._day_html()
        for m in _re.finditer(r'class="gantt-block([^"]*)"', html):
            self.assertNotIn('event-vehicle', m.group(1),
                             'event-vehicle found on a gantt-block element')

    def test_gantt_block_does_not_contain_event_multi_class(self):
        """Gantt blocks must NOT carry event-multi class."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        vehicle = Asset.objects.create(name='Mixed Van', asset_type=Asset.AssetType.VEHICLE)
        ev = Event.objects.create(
            title='Multi Class Test', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        ev.assets.add(vehicle)
        html = self._day_html()
        for m in _re.finditer(r'class="gantt-block([^"]*)"', html):
            self.assertNotIn('event-multi', m.group(1),
                             'event-multi found on a gantt-block element')

    # ── Pending block: event-pending class present ────────────────────────────

    def test_pending_block_has_event_pending_class(self):
        """Gantt block for a pending event must carry event-pending."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        self._make_event(title='Pending Block', approved=False, start=start, end=end)
        html = self._day_html()
        self.assertIn('event-pending', html)

    # ── Scheduled ghost bar opacity when segments present ─────────────────────

    def test_scheduled_ghost_bar_has_scheduled_class(self):
        """When an event has segments, the scheduled bar gets gantt-block--scheduled."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = self._make_event(title='Ghost Bar', approved=True, start=start, end=end)
        self._add_segment(ev, seg_start=start + timedelta(minutes=5),
                          seg_end=start + timedelta(minutes=65))
        html = self._day_html()
        self.assertIn('gantt-block--scheduled', html)

    # ── Active segment: class and data-segment-start ──────────────────────────

    def test_active_segment_has_active_segment_class_and_data_attr(self):
        """Open segment renders with gantt-block--active-segment and data-segment-start."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = self._make_event(title='Active Seg', approved=True, start=start, end=end)
        from cal.models import ActualTimeSegment
        seg = ActualTimeSegment.objects.create(
            event=ev,
            start=start + timedelta(minutes=10),
            end=None,  # open
        )
        html = self._day_html()
        self.assertIn('gantt-block--active-segment', html)
        self.assertIn('data-segment-start=', html)

    # ── Pause gap between segments ────────────────────────────────────────────

    def test_pause_gap_rendered_between_two_segments(self):
        """Two closed segments with a gap between them must produce gantt-block--pause-gap."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = self._make_event(title='Gap Event', approved=True, start=start, end=end)
        # Segment 1: 9:05 – 9:30
        self._add_segment(ev,
                          seg_start=start + timedelta(minutes=5),
                          seg_end=start + timedelta(minutes=30))
        # Segment 2: 9:45 – 10:15  (gap = 9:30-9:45)
        self._add_segment(ev,
                          seg_start=start + timedelta(minutes=45),
                          seg_end=start + timedelta(minutes=75))
        html = self._day_html()
        self.assertIn('gantt-block--pause-gap', html)

    # ── Completed event block ─────────────────────────────────────────────────

    def test_completed_event_block_has_completed_class(self):
        """Past approved event with segments gets event-completed on its Gantt block."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        ev = self._make_event(title='Completed Event', approved=True, start=start, end=end)
        self._add_segment(ev,
                          seg_start=start + timedelta(minutes=5),
                          seg_end=start + timedelta(minutes=90))
        # Use a past date so the event is definitively in the past
        html = self.client.get(
            reverse('cal:calendar') + '?view=day&date=2026-4-1'
        ).content.decode()
        # event-completed class must appear somewhere in the rendered block
        self.assertIn('event-completed', html)

    # ── No-show event block ───────────────────────────────────────────────────

    def test_noshow_event_block_has_noshow_class(self):
        """Past approved event with NO segments gets event-noshow on its Gantt block."""
        start = datetime(2026, 4, 1, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 1, 11, 0, tzinfo=_local_tz)
        self._make_event(title='No Show Event', approved=True, start=start, end=end)
        # No segments — viewed on a later day so the event is definitively past
        html = self.client.get(
            reverse('cal:calendar') + '?view=day&date=2026-4-1'
        ).content.decode()
        self.assertIn('event-noshow', html)


class GanttLegendContextTest(TestCase):
    """
    Tests for the contextual legend: the view must pass boolean flags
    (has_pending, has_active, has_completed, has_noshow) to the template so
    the legend only shows the states present in the current day's data.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='lgnd_user', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(
            name='Legend Track', asset_type=Asset.AssetType.TRACK, color='#0284c7'
        )

    def _get_day(self, date_str='2026-4-2'):
        return self.client.get(reverse('cal:calendar') + f'?view=day&date={date_str}')

    # ── has_pending flag ──────────────────────────────────────────────────────

    def test_view_passes_has_pending_true_when_pending_event_present(self):
        """Day view context must include has_pending=True when there is a pending event."""
        start = datetime(2026, 4, 2, 10, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 12, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Pending', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=False,
        )
        ev.assets.add(self.track)
        resp = self._get_day()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get('has_pending'),
                        'has_pending not True in context with a pending event')

    def test_view_passes_has_pending_false_when_no_pending_events(self):
        """Day view context must have has_pending=False (or absent) when no pending events."""
        start = datetime(2026, 4, 2, 10, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 12, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Approved', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        resp = self._get_day()
        self.assertFalse(resp.context.get('has_pending'),
                         'has_pending is True despite no pending events')

    # ── has_active flag ───────────────────────────────────────────────────────

    def test_view_passes_has_active_true_when_open_segment_present(self):
        """Day view context must include has_active=True when any event has an open segment."""
        from cal.models import ActualTimeSegment
        start = datetime(2026, 4, 2, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Active', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        ActualTimeSegment.objects.create(event=ev, start=start + timedelta(minutes=5), end=None)
        resp = self._get_day()
        self.assertTrue(resp.context.get('has_active'),
                        'has_active not True in context with an open segment')

    def test_view_passes_has_active_false_when_no_open_segments(self):
        """Day view context must have has_active=False when no open segments exist."""
        start = datetime(2026, 4, 2, 10, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 12, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='No Active', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        resp = self._get_day()
        self.assertFalse(resp.context.get('has_active'),
                         'has_active is True despite no open segments')

    # ── has_completed flag ────────────────────────────────────────────────────

    def test_view_passes_has_completed_true_when_past_event_has_segments(self):
        """Day view context must include has_completed=True for past events with segments."""
        from cal.models import ActualTimeSegment
        start = datetime(2026, 4, 2, 2, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 4, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Completed', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        ActualTimeSegment.objects.create(
            event=ev,
            start=start + timedelta(minutes=5),
            end=start + timedelta(minutes=90),
        )
        resp = self._get_day()
        self.assertTrue(resp.context.get('has_completed'),
                        'has_completed not True when a completed event is present')

    # ── has_noshow flag ───────────────────────────────────────────────────────

    def test_view_passes_has_noshow_true_when_past_event_has_no_segments(self):
        """Day view context must include has_noshow=True for past events with no segments."""
        start = datetime(2026, 4, 2, 2, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 4, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='No Show', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        resp = self._get_day()
        self.assertTrue(resp.context.get('has_noshow'),
                        'has_noshow not True when a no-show event is present')

    def test_view_passes_has_noshow_false_when_all_events_have_segments(self):
        """has_noshow must be False when every past approved event has at least one segment."""
        from cal.models import ActualTimeSegment
        start = datetime(2026, 4, 2, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='With Segs', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        ActualTimeSegment.objects.create(
            event=ev,
            start=start + timedelta(minutes=10),
            end=start + timedelta(minutes=60),
        )
        resp = self._get_day()
        self.assertFalse(resp.context.get('has_noshow'),
                         'has_noshow is True even though every event has segments')

    # ── Legend HTML reflects contextual flags ─────────────────────────────────

    def test_legend_always_shows_pending_swatch(self):
        """Legend always shows all six state swatches including pending."""
        resp = self._get_day()
        content = resp.content.decode()
        self.assertIn('legend-swatch-pending', content)

    def test_legend_always_shows_completed_swatch(self):
        """Legend always shows all six state swatches including completed."""
        resp = self._get_day()
        content = resp.content.decode()
        self.assertIn('legend-swatch-completed', content)

    def test_legend_shows_completed_swatch_when_has_completed(self):
        """When has_completed=True the legend must include a completed swatch."""
        from cal.models import ActualTimeSegment
        start = datetime(2026, 4, 2, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='Comp Lgnd', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        ActualTimeSegment.objects.create(
            event=ev,
            start=start + timedelta(minutes=5),
            end=start + timedelta(minutes=90),
        )
        resp = self._get_day()
        content = resp.content.decode()
        self.assertIn('legend-swatch-completed', content)

    def test_legend_shows_noshow_swatch_when_has_noshow(self):
        """When has_noshow=True the legend must include a no-show swatch."""
        start = datetime(2026, 4, 2, 9, 0, tzinfo=_local_tz)
        end   = datetime(2026, 4, 2, 11, 0, tzinfo=_local_tz)
        ev = Event.objects.create(
            title='NoShow Lgnd', description='', start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        resp = self._get_day()
        content = resp.content.decode()
        self.assertIn('legend-swatch-noshow', content)


class GanttCSSIntegrityTest(TestCase):
    """
    CSS integrity tests for the new Gantt bar design.

    These are file-read tests: they parse styles.css and assert that the
    expected selectors and properties exist.  No server round-trip needed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.conf import settings
        css_path = os.path.join(
            settings.BASE_DIR, 'cal', 'static', 'cal', 'css', 'styles.css'
        )
        with open(css_path) as f:
            cls.css = f.read()

    # ── Pending bar: outline-only ─────────────────────────────────────────────

    def test_event_pending_has_transparent_background(self):
        """event-pending rule must set a transparent background (outline-only bar)."""
        self.assertIn('.event-pending', self.css)
        # Find the block for .event-pending
        idx = self.css.index('.gantt-block.event-pending')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertIn('transparent', block,
                      '.gantt-block.event-pending must use transparent background')

    def test_event_pending_has_color_border(self):
        """event-pending rule must set a border (track color border, not dashed white)."""
        idx = self.css.index('.gantt-block.event-pending')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertIn('border', block,
                      '.gantt-block.event-pending must have a border declaration')

    def test_event_pending_removes_dashed_white_border(self):
        """Old dashed rgba(255,255,255,0.85) border must be replaced."""
        idx = self.css.index('.gantt-block.event-pending')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertNotIn('rgba(255,255,255,0.85)', block,
                         'Old dashed white border still present on event-pending')

    # ── Scheduled ghost bar opacity ───────────────────────────────────────────

    def test_scheduled_ghost_bar_opacity_is_0_4(self):
        """gantt-block--scheduled must set opacity: 0.4 (was 0.25)."""
        self.assertIn('.gantt-block--scheduled', self.css)
        idx = self.css.index('.gantt-block.gantt-block--scheduled')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertIn('0.4', block,
                      '.gantt-block--scheduled opacity must be 0.4')
        self.assertNotIn('0.25', block,
                         '.gantt-block--scheduled opacity 0.25 not updated')

    # ── Pause gap: diagonal stripe ────────────────────────────────────────────

    def test_pause_gap_uses_repeating_linear_gradient(self):
        """gantt-block--pause-gap must use repeating-linear-gradient for diagonal stripe."""
        self.assertIn('.gantt-block--pause-gap', self.css)
        idx = self.css.index('.gantt-block--pause-gap')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertIn('repeating-linear-gradient', block,
                      '.gantt-block--pause-gap must use repeating-linear-gradient')

    def test_pause_gap_removes_dashed_border(self):
        """Old 1px dashed border on pause gap must be removed."""
        idx = self.css.index('.gantt-block--pause-gap')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertNotIn('1px dashed', block,
                         'Old 1px dashed border still on gantt-block--pause-gap')

    # ── event-completed ───────────────────────────────────────────────────────

    def test_event_completed_css_rule_exists(self):
        """.event-completed (or .gantt-block.event-completed) must be defined in CSS."""
        self.assertIn('event-completed', self.css,
                      '.event-completed selector missing from styles.css')

    def test_event_completed_has_opacity(self):
        """event-completed rule must set opacity (reduced, ~0.7)."""
        idx = self.css.index('event-completed')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertIn('opacity', block,
                      '.event-completed must set opacity')

    # ── event-noshow ──────────────────────────────────────────────────────────

    def test_event_noshow_css_rule_exists(self):
        """.event-noshow (or .gantt-block.event-noshow) must be defined in CSS."""
        self.assertIn('event-noshow', self.css,
                      '.event-noshow selector missing from styles.css')

    # ── Legend swatches for new states ────────────────────────────────────────

    def test_legend_swatch_completed_css_exists(self):
        """.legend-swatch-completed must be defined in styles.css."""
        self.assertIn('legend-swatch-completed', self.css,
                      '.legend-swatch-completed missing from styles.css')

    def test_legend_swatch_noshow_css_exists(self):
        """.legend-swatch-noshow must be defined in styles.css."""
        self.assertIn('legend-swatch-noshow', self.css,
                      '.legend-swatch-noshow missing from styles.css')

    # ── Active segment: pulse is on leading-edge element, not whole bar ───────

    def test_gantt_pulse_animation_only_on_active_segment(self):
        """gantt-pulse animation must NOT be on .gantt-block itself; only on segment/indicator."""
        # The main .gantt-block rule must not carry the pulse animation
        idx = self.css.index('.gantt-block {')
        block_end = self.css.index('}', idx)
        block = self.css[idx:block_end]
        self.assertNotIn('gantt-pulse', block,
                         'gantt-pulse animation should not be on the base .gantt-block rule')

    # ── Dark mode: new states have dark-theme overrides ───────────────────────

    def test_dark_theme_has_event_completed_override(self):
        """html.dark-theme must have a rule covering event-completed bars."""
        self.assertIn('dark-theme', self.css)
        # Look for a dark-theme rule that references event-completed
        self.assertRegex(
            self.css,
            r'html\.dark-theme[^{]*event-completed',
            'No dark-theme override found for event-completed',
        )

    def test_dark_theme_has_event_noshow_override(self):
        """html.dark-theme must have a rule covering event-noshow bars."""
        self.assertRegex(
            self.css,
            r'html\.dark-theme[^{]*event-noshow',
            'No dark-theme override found for event-noshow',
        )

    def test_dark_theme_has_event_pending_override(self):
        """html.dark-theme must have a rule covering the redesigned pending bars."""
        self.assertRegex(
            self.css,
            r'html\.dark-theme[^{]*event-pending',
            'No dark-theme override found for redesigned event-pending',
        )


# ════════════════════════════════════════════════════════════════════════════════
# New tests: Visual extent row stacking, multi-subtrack promotion, future time
# validation, Gantt tooltip data, connector lines, scheduled boundary markers.
# ════════════════════════════════════════════════════════════════════════════════


# ── 1. Visual-extent row stacking (_assign_rows) ─────────────────────────────

class AssignRowsVisualExtentTest(TestCase):
    """
    _assign_rows() uses _visual_extent() which considers actual segments as well
    as scheduled times.  Events that look non-overlapping on the schedule may
    still require separate rows if their actuals overlap.
    """

    def setUp(self):
        from cal.models import ActualTimeSegment as _ATS
        self.ATS = _ATS
        from cal.utils import Calendar
        self.cal = Calendar(2026, 4)
        self.user = User.objects.create_user(username='row_user', password='Testpass123!')
        self.track = Asset.objects.create(
            name='Row Track', asset_type=Asset.AssetType.TRACK
        )

    def _make_event(self, start, end, title='Event'):
        ev = Event.objects.create(
            title=title, description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        return ev

    def _add_seg(self, ev, seg_start, seg_end=None):
        return self.ATS.objects.create(event=ev, start=seg_start, end=seg_end)

    # ── Non-overlapping schedules but overlapping actuals → separate rows ─────

    def test_overlapping_actuals_get_separate_rows(self):
        """
        Event A scheduled 9-10, Event B scheduled 11-12.
        If A's segment runs until 11:30 it overlaps B's visual extent.
        Both should be placed in different rows.
        """
        base = datetime(2026, 4, 5, 0, 0, tzinfo=_local_tz)
        ev_a = self._make_event(base.replace(hour=9), base.replace(hour=10), 'A')
        ev_b = self._make_event(base.replace(hour=11), base.replace(hour=12), 'B')
        # A's actual segment runs into B's scheduled window
        self._add_seg(ev_a,
                      seg_start=base.replace(hour=9),
                      seg_end=base.replace(hour=11, minute=30))
        # Force queryset prefetch so _visual_extent sees the segments
        events = list(
            Event.objects.filter(pk__in=[ev_a.pk, ev_b.pk])
            .prefetch_related('segments')
        )
        assignments, n_rows = self.cal._assign_rows(events)
        row_map = {ev.pk: row for ev, row in assignments}
        self.assertNotEqual(
            row_map[ev_a.pk], row_map[ev_b.pk],
            'Events with overlapping actuals must be in different rows',
        )
        self.assertEqual(n_rows, 2)

    # ── Non-overlapping visual extents share a row ────────────────────────────

    def test_non_overlapping_extents_share_row(self):
        """
        Event A scheduled 9-10 with actual 9:05-9:50 (extent ends 9:50).
        Event B scheduled 11-12 with actual 11:10-11:50.
        Extents do not overlap → both land in row 0.
        """
        base = datetime(2026, 4, 5, 0, 0, tzinfo=_local_tz)
        ev_a = self._make_event(base.replace(hour=9), base.replace(hour=10), 'A')
        ev_b = self._make_event(base.replace(hour=11), base.replace(hour=12), 'B')
        self._add_seg(ev_a,
                      seg_start=base.replace(hour=9, minute=5),
                      seg_end=base.replace(hour=9, minute=50))
        self._add_seg(ev_b,
                      seg_start=base.replace(hour=11, minute=10),
                      seg_end=base.replace(hour=11, minute=50))
        events = list(
            Event.objects.filter(pk__in=[ev_a.pk, ev_b.pk])
            .prefetch_related('segments')
        )
        assignments, n_rows = self.cal._assign_rows(events)
        row_map = {ev.pk: row for ev, row in assignments}
        self.assertEqual(
            row_map[ev_a.pk], row_map[ev_b.pk],
            'Non-overlapping visual extents should share a row',
        )
        self.assertEqual(n_rows, 1)

    # ── Open segment uses current time as visual end ──────────────────────────

    def test_open_segment_extends_visual_extent(self):
        """
        Event A scheduled 9-10 with an open segment (end=None).
        Event B scheduled 10:05-11 should be pushed to a separate row because
        A's visual extent now extends to 'now' (which is past 10:05 for any
        realistic 'now').
        """
        now = timezone.now()
        # Anchor events around 'now' so the open segment always overlaps B.
        ev_a = self._make_event(now - timedelta(hours=2), now - timedelta(hours=1), 'A Open')
        ev_b = self._make_event(now - timedelta(minutes=30), now + timedelta(hours=1), 'B')
        # Open segment that started before B and is still running
        self._add_seg(ev_a, seg_start=now - timedelta(hours=2), seg_end=None)
        events = list(
            Event.objects.filter(pk__in=[ev_a.pk, ev_b.pk])
            .prefetch_related('segments')
        )
        assignments, n_rows = self.cal._assign_rows(events)
        row_map = {ev.pk: row for ev, row in assignments}
        self.assertNotEqual(
            row_map[ev_a.pk], row_map[ev_b.pk],
            'Open segment should extend visual extent and force B to a separate row',
        )

    # ── No-segment events still work correctly ────────────────────────────────

    def test_no_segments_uses_scheduled_extent_only(self):
        """Events without segments use scheduled start/end as their visual extent."""
        base = datetime(2026, 4, 5, 0, 0, tzinfo=_local_tz)
        ev_a = self._make_event(base.replace(hour=9), base.replace(hour=10), 'A')
        ev_b = self._make_event(base.replace(hour=10), base.replace(hour=11), 'B')
        # A ends exactly when B starts — no overlap, share a row
        events = list(
            Event.objects.filter(pk__in=[ev_a.pk, ev_b.pk])
            .prefetch_related('segments')
        )
        assignments, n_rows = self.cal._assign_rows(events)
        row_map = {ev.pk: row for ev, row in assignments}
        self.assertEqual(row_map[ev_a.pk], row_map[ev_b.pk],
                         'Butting events (no overlap) should share a row')
        self.assertEqual(n_rows, 1)

    def test_single_event_always_row_zero(self):
        """A single event is always assigned to row 0."""
        base = datetime(2026, 4, 5, 9, 0, tzinfo=_local_tz)
        ev = self._make_event(base, base + timedelta(hours=1))
        events = list(Event.objects.filter(pk=ev.pk).prefetch_related('segments'))
        assignments, n_rows = self.cal._assign_rows(events)
        self.assertEqual(assignments[0][1], 0)
        self.assertEqual(n_rows, 1)


# ── 2. Multi-subtrack event promotion ────────────────────────────────────────

class MultiSubtrackPromotionDayViewTest(TestCase):
    """
    An event booked on 2+ subtracks of the same parent must be promoted to the
    parent's full-track lane in the day view (not appear in individual subtrack rows).
    """

    def setUp(self):
        self.user = User.objects.create_user(username='promo_user', password='Testpass123!')
        self.client.force_login(self.user)
        self.parent = Asset.objects.create(
            name='Promo Parent', asset_type=Asset.AssetType.TRACK
        )
        self.sub_a = Asset.objects.create(
            name='Sub A', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_b = Asset.objects.create(
            name='Sub B', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.start = datetime(2026, 4, 1, 10, 0, tzinfo=_local_tz)
        self.end   = datetime(2026, 4, 1, 12, 0, tzinfo=_local_tz)

    def _day_html(self):
        resp = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def test_multi_subtrack_event_appears_in_parent_lane(self):
        """
        Event on 2 subtracks must appear in the gantt-parent-lane (full-track overlay).
        """
        ev = Event.objects.create(
            title='Multi Sub Event', description='',
            start_time=self.start, end_time=self.end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_a)
        ev.assets.add(self.sub_b)
        html = self._day_html()
        self.assertIn('Multi Sub Event', html)
        # The parent lane container must be present
        self.assertIn('gantt-parent-lane', html)

    def test_multi_subtrack_event_title_in_parent_lane_section(self):
        """
        When an event spans 2 subtracks, the title should appear inside the
        gantt-parent-lane block rather than only inside a subtrack row.
        The parent lane label 'All' should be present.
        """
        ev = Event.objects.create(
            title='FullTrackEvent', description='',
            start_time=self.start, end_time=self.end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_a)
        ev.assets.add(self.sub_b)
        html = self._day_html()
        # The "All" label appears when the parent lane is rendered
        self.assertIn('gantt-parent-lane-label', html)

    def test_single_subtrack_event_not_promoted(self):
        """
        An event on only ONE subtrack must not be promoted to the parent lane.
        The parent lane should not appear if there are no full-track bookings.
        """
        ev = Event.objects.create(
            title='Single Sub Only', description='',
            start_time=self.start, end_time=self.end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.sub_a)
        html = self._day_html()
        self.assertIn('Single Sub Only', html)
        # No parent-lane label since the event only covers one subtrack
        self.assertNotIn('gantt-parent-lane-label', html)


class MultiSubtrackPromotionDashboardAPITest(TestCase):
    """
    Dashboard events API: an event booked on 2+ subtracks of the same parent
    must appear in the parent track's events list, not in the individual
    subtrack events lists.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='promo_api_admin', password='Testpass123!', is_staff=True
        )
        self.parent = Asset.objects.create(
            name='API Promo Parent', asset_type=Asset.AssetType.TRACK
        )
        self.sub_a = Asset.objects.create(
            name='Sub Alpha', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.sub_b = Asset.objects.create(
            name='Sub Beta', asset_type=Asset.AssetType.TRACK, parent=self.parent
        )
        self.client.login(username='promo_api_admin', password='Testpass123!')
        self.url = reverse('cal:dashboard_events_api')
        now = timezone.now()
        self.today = now.date()

    def _get_today(self):
        resp = self.client.get(self.url, {'date': self.today.isoformat()})
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_multi_subtrack_event_in_parent_events(self):
        """
        Event booked on both Sub Alpha and Sub Beta appears in the parent
        track's events list.
        """
        now = timezone.now()
        ev = Event.objects.create(
            title='Promo API Event', description='',
            start_time=now.replace(hour=9, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=11, minute=0, second=0, microsecond=0),
            is_approved=True,
        )
        ev.assets.add(self.sub_a)
        ev.assets.add(self.sub_b)
        data = self._get_today()
        parent_data = data['tracks']['API Promo Parent']
        parent_event_ids = [e['id'] for e in parent_data['events']]
        self.assertIn(ev.pk, parent_event_ids,
                      'Multi-subtrack event must appear in parent track events')

    def test_multi_subtrack_event_absent_from_subtrack_events(self):
        """
        Event booked on both Sub Alpha and Sub Beta must NOT appear in
        either subtrack's individual events list.
        """
        now = timezone.now()
        ev = Event.objects.create(
            title='Promo Absent Test', description='',
            start_time=now.replace(hour=9, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=11, minute=0, second=0, microsecond=0),
            is_approved=True,
        )
        ev.assets.add(self.sub_a)
        ev.assets.add(self.sub_b)
        data = self._get_today()
        parent_data = data['tracks']['API Promo Parent']
        subtracks = parent_data.get('subtracks', {})
        for sub_name, sub_data in subtracks.items():
            sub_event_ids = [e['id'] for e in sub_data['events']]
            self.assertNotIn(
                ev.pk, sub_event_ids,
                f'Multi-subtrack event must not appear in subtrack "{sub_name}" events',
            )

    def test_single_subtrack_event_stays_in_subtrack(self):
        """
        An event on only one subtrack must remain in that subtrack's events list
        and not appear in the parent's events list.
        """
        now = timezone.now()
        ev = Event.objects.create(
            title='Single Sub API', description='',
            start_time=now.replace(hour=13, minute=0, second=0, microsecond=0),
            end_time=now.replace(hour=14, minute=0, second=0, microsecond=0),
            is_approved=True,
        )
        ev.assets.add(self.sub_a)
        data = self._get_today()
        parent_data = data['tracks']['API Promo Parent']
        parent_event_ids = [e['id'] for e in parent_data['events']]
        self.assertNotIn(ev.pk, parent_event_ids,
                         'Single-subtrack event must NOT be promoted to parent events')
        subtracks = parent_data.get('subtracks', {})
        sub_alpha_events = subtracks.get('Sub Alpha', {}).get('events', [])
        sub_alpha_ids = [e['id'] for e in sub_alpha_events]
        self.assertIn(ev.pk, sub_alpha_ids,
                      'Single-subtrack event must stay in its own subtrack events list')


# ── 3. Future time validation ─────────────────────────────────────────────────

class StampAPIFutureTimeTest(TestCase):
    """
    The stamp API rejects custom times that are in the future.
    Setting a current or past time must succeed.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username='future_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(
            name='Future Track', asset_type=Asset.AssetType.TRACK
        )
        now = timezone.now()
        self.event = Event.objects.create(
            title='Future Time Event', description='',
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(hours=2),
            is_approved=True, created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.client.login(username='future_admin', password='Testpass123!')
        self.url = reverse('cal:dashboard_stamp_actual', args=[self.event.pk])

    def _stamp(self, action, time_iso=None):
        body = {'action': action}
        if time_iso is not None:
            body['time'] = time_iso
        return self.client.post(
            self.url, data=json.dumps(body),
            content_type='application/json',
        )

    def test_future_custom_time_returns_400(self):
        """Stamp with a custom_time in the future must return 400."""
        future = (timezone.now() + timedelta(minutes=30)).isoformat()
        resp = self._stamp('start', time_iso=future)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('future', resp.json()['error'].lower())

    def test_future_custom_time_does_not_create_segment(self):
        """A rejected future-time stamp must not create any segment."""
        future = (timezone.now() + timedelta(hours=1)).isoformat()
        self._stamp('start', time_iso=future)
        self.assertEqual(self.event.segments.count(), 0)

    def test_past_custom_time_succeeds(self):
        """Stamp with a past custom_time must succeed (200)."""
        past = (timezone.now() - timedelta(minutes=45)).isoformat()
        resp = self._stamp('start', time_iso=past)
        self.assertEqual(resp.status_code, 200)

    def test_now_custom_time_succeeds(self):
        """Stamp with a time at 'now' (within a few seconds) must succeed."""
        # Use a time 1 second in the past to avoid sub-second race conditions
        just_now = (timezone.now() - timedelta(seconds=1)).isoformat()
        resp = self._stamp('start', time_iso=just_now)
        self.assertEqual(resp.status_code, 200)

    def test_no_custom_time_always_succeeds(self):
        """Stamp with no custom_time (uses server now) must always succeed."""
        resp = self._stamp('start')
        self.assertEqual(resp.status_code, 200)


class SegmentEditFutureTimeTest(TestCase):
    """
    The segment edit API rejects start or end times that are in the future.
    """

    def setUp(self):
        from cal.models import ActualTimeSegment
        self.admin = User.objects.create_user(
            username='seg_edit_admin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(
            name='Seg Edit Track', asset_type=Asset.AssetType.TRACK
        )
        now = timezone.now()
        self.event = Event.objects.create(
            title='Seg Edit Event', description='',
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(hours=2),
            is_approved=True, created_by=self.admin,
        )
        self.event.assets.add(self.track)
        self.seg = ActualTimeSegment.objects.create(
            event=self.event,
            start=now - timedelta(hours=1),
            end=now - timedelta(minutes=30),
        )
        self.client.login(username='seg_edit_admin', password='Testpass123!')
        self.url = reverse('cal:segment_edit', args=[self.seg.pk])

    def _edit(self, **kwargs):
        return self.client.post(
            self.url, data=json.dumps(kwargs),
            content_type='application/json',
        )

    def test_future_start_returns_400(self):
        """Setting segment start to a future time must return 400."""
        future = (timezone.now() + timedelta(minutes=10)).isoformat()
        resp = self._edit(start=future)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('future', resp.json()['error'].lower())

    def test_future_end_returns_400(self):
        """Setting segment end to a future time must return 400."""
        future = (timezone.now() + timedelta(minutes=10)).isoformat()
        resp = self._edit(end=future)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('future', resp.json()['error'].lower())

    def test_past_start_succeeds(self):
        """Editing start to a valid past time must succeed."""
        past = (timezone.now() - timedelta(hours=2)).isoformat()
        resp = self._edit(start=past)
        self.assertEqual(resp.status_code, 200)

    def test_past_end_succeeds(self):
        """Editing end to a valid past time (after start) must succeed."""
        past = (timezone.now() - timedelta(minutes=10)).isoformat()
        resp = self._edit(end=past)
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_gets_403(self):
        """Non-admin cannot edit segments."""
        regular = User.objects.create_user(username='seg_regular', password='Testpass123!')
        self.client.force_login(regular)
        resp = self._edit(end=(timezone.now() - timedelta(minutes=5)).isoformat())
        self.assertEqual(resp.status_code, 403)

    def test_nonexistent_segment_returns_404(self):
        """Editing a non-existent segment returns 404."""
        url = reverse('cal:segment_edit', args=[99999])
        resp = self.client.post(
            url, data=json.dumps({'start': (timezone.now() - timedelta(hours=1)).isoformat()}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 404)


# ── 4. Gantt tooltip data (_gantt_tooltip_data) ───────────────────────────────

class GanttTooltipDataTest(TestCase):
    """
    Calendar._gantt_tooltip_data() builds the JSON dict served as tooltip data.
    Tests cover status determination, segment listing, pause time, and asset listing.
    """

    def setUp(self):
        from cal.models import ActualTimeSegment
        from cal.utils import Calendar
        self.ATS = ActualTimeSegment
        self.cal = Calendar(2026, 4)
        self.user = User.objects.create_user(username='tip_user', password='Testpass123!')
        self.track = Asset.objects.create(
            name='Tip Track', asset_type=Asset.AssetType.TRACK, color='#dc2626'
        )
        self.vehicle = Asset.objects.create(
            name='Tip Van', asset_type=Asset.AssetType.VEHICLE
        )

    def _make_event(self, *, title='Test', approved=True,
                    start_offset_hours=-2, end_offset_hours=2):
        now = timezone.now()
        start = now + timedelta(hours=start_offset_hours)
        end = now + timedelta(hours=end_offset_hours)
        ev = Event.objects.create(
            title=title, description='A description',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=approved,
        )
        ev.assets.add(self.track)
        return ev

    def _load_event(self, ev):
        """Return the event with segments prefetched (mirrors utils usage)."""
        return Event.objects.prefetch_related('assets', 'segments').get(pk=ev.pk)

    # ── Status: Scheduled ─────────────────────────────────────────────────────

    def test_status_scheduled_for_future_approved_no_segments(self):
        """Approved future event with no segments → status 'Scheduled'."""
        ev = self._make_event(start_offset_hours=1, end_offset_hours=3)
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'Scheduled')

    # ── Status: Pending ───────────────────────────────────────────────────────

    def test_status_pending_for_unapproved_event(self):
        """Unapproved event → status 'Pending' regardless of segments."""
        ev = self._make_event(approved=False, start_offset_hours=1, end_offset_hours=3)
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'Pending')

    # ── Status: Active ────────────────────────────────────────────────────────

    def test_status_active_for_open_segment(self):
        """Approved event with an open segment that is currently active → status 'Active'."""
        ev = self._make_event(start_offset_hours=-1, end_offset_hours=1)
        self.ATS.objects.create(
            event=ev, start=timezone.now() - timedelta(minutes=30), end=None
        )
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'Active')

    # ── Status: Paused ────────────────────────────────────────────────────────

    def test_status_paused_all_segments_closed_not_stopped(self):
        """
        Approved event with segments all closed and not stopped and not past → 'Paused'.
        """
        ev = self._make_event(start_offset_hours=-1, end_offset_hours=1)
        self.ATS.objects.create(
            event=ev,
            start=timezone.now() - timedelta(minutes=50),
            end=timezone.now() - timedelta(minutes=30),
        )
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'Paused')

    # ── Status: Completed ─────────────────────────────────────────────────────

    def test_status_completed_for_stopped_event_with_segments(self):
        """
        Approved event with segments and is_stopped=True → status 'Completed'.
        (is_stopped is the flag that marks an event as definitively done.)
        """
        ev = self._make_event(start_offset_hours=-4, end_offset_hours=2)
        self.ATS.objects.create(
            event=ev,
            start=timezone.now() - timedelta(hours=3, minutes=30),
            end=timezone.now() - timedelta(hours=2),
        )
        ev.is_stopped = True
        ev.save(update_fields=['is_stopped'])
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'Completed')

    # ── Status: No-show ───────────────────────────────────────────────────────

    def test_status_noshow_for_past_event_without_segments(self):
        """Past approved event with no segments → status 'No-show'."""
        ev = self._make_event(start_offset_hours=-4, end_offset_hours=-1)
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['status'], 'No-show')

    # ── Segment list ──────────────────────────────────────────────────────────

    def test_segments_listed_with_closed_segment(self):
        """Closed segments appear in info['segments'] list."""
        ev = self._make_event(start_offset_hours=-2, end_offset_hours=2)
        self.ATS.objects.create(
            event=ev,
            start=timezone.now() - timedelta(hours=1),
            end=timezone.now() - timedelta(minutes=30),
        )
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertIn('segments', info)
        self.assertEqual(len(info['segments']), 1)

    def test_open_segment_listed_with_now_label(self):
        """Open segments appear with 'now' in the label."""
        ev = self._make_event(start_offset_hours=-1, end_offset_hours=1)
        self.ATS.objects.create(
            event=ev, start=timezone.now() - timedelta(minutes=20), end=None
        )
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertTrue(
            any('now' in s for s in info['segments']),
            'Open segment must include "now" in its label',
        )

    def test_two_segments_pause_time_calculated(self):
        """
        Two closed segments with a 15-minute gap → info['pauseTime'] is present
        and reflects the inter-segment gap.
        """
        ev = self._make_event(start_offset_hours=-3, end_offset_hours=1)
        t0 = timezone.now() - timedelta(hours=2)
        self.ATS.objects.create(event=ev, start=t0, end=t0 + timedelta(minutes=30))
        # 15-minute gap
        self.ATS.objects.create(
            event=ev,
            start=t0 + timedelta(minutes=45),
            end=t0 + timedelta(hours=1, minutes=15),
        )
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertIn('pauseTime', info,
                      'Pause time should be reported when there is a gap between segments')

    def test_no_pause_time_stopped_single_segment(self):
        """
        Stopped event with a single closed segment has no inter-segment gaps
        and the trailing-pause rule does not apply (status is Completed).
        No 'pauseTime' key in info.
        """
        ev = self._make_event(start_offset_hours=-2, end_offset_hours=2)
        self.ATS.objects.create(
            event=ev,
            start=timezone.now() - timedelta(hours=1),
            end=timezone.now() - timedelta(minutes=30),
        )
        ev.is_stopped = True
        ev.save(update_fields=['is_stopped'])
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertNotIn('pauseTime', info)

    # ── Asset listing ─────────────────────────────────────────────────────────

    def test_tracks_included_in_info(self):
        """Track-type assets attached to the event appear in info['tracks']."""
        ev = self._make_event()
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertIn('tracks', info)
        self.assertIn('Tip Track', info['tracks'])

    def test_vehicles_included_in_info(self):
        """Vehicle-type assets appear in info['vehicles']."""
        ev = self._make_event(start_offset_hours=-1, end_offset_hours=1)
        ev.assets.add(self.vehicle)
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertIn('vehicles', info)
        self.assertIn('Tip Van', info['vehicles'])

    def test_no_vehicle_key_when_no_vehicles(self):
        """If no vehicle assets, 'vehicles' key is absent."""
        ev = self._make_event()
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertNotIn('vehicles', info)

    def test_title_and_creator_present(self):
        """Basic fields title and creator are always present."""
        ev = self._make_event(title='Tooltip Title')
        ev = self._load_event(ev)
        segs = list(ev.segments.all())
        info = self.cal._gantt_tooltip_data(ev, segs)
        self.assertEqual(info['title'], 'Tooltip Title')
        self.assertEqual(info['creator'], 'tip_user')


# ── 5. Connector line rendering ───────────────────────────────────────────────

class GanttConnectorLineTest(TestCase):
    """
    _make_block() renders connector lines (gantt-connector--late / --early)
    when actual segments are disconnected from the scheduled bar.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='conn_user', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(
            name='Conn Track', asset_type=Asset.AssetType.TRACK, color='#dc2626'
        )

    def _day_html(self):
        resp = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _make_event(self, title, start, end):
        ev = Event.objects.create(
            title=title, description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        return ev

    def _add_seg(self, ev, seg_start, seg_end):
        from cal.models import ActualTimeSegment
        return ActualTimeSegment.objects.create(event=ev, start=seg_start, end=seg_end)

    def test_late_start_renders_connector_late(self):
        """
        When all segments start AFTER the scheduled bar ends, a
        gantt-connector--late div must be rendered.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 9-10, actual segment starts at 11 (late)
        ev = self._make_event('Late Conn', base.replace(hour=9), base.replace(hour=10))
        self._add_seg(ev,
                      seg_start=base.replace(hour=11),
                      seg_end=base.replace(hour=11, minute=45))
        html = self._day_html()
        self.assertIn('gantt-connector--late', html)

    def test_early_start_renders_connector_early(self):
        """
        When all segments end BEFORE the scheduled bar starts, a
        gantt-connector--early div must be rendered.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 11-12, actual segment ends at 10 (early)
        ev = self._make_event('Early Conn', base.replace(hour=11), base.replace(hour=12))
        self._add_seg(ev,
                      seg_start=base.replace(hour=9),
                      seg_end=base.replace(hour=10))
        html = self._day_html()
        self.assertIn('gantt-connector--early', html)

    def test_overlapping_segment_no_connector(self):
        """
        When a segment overlaps the scheduled bar, no connector div is rendered.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 9-11, actual 9:15-10:30 (inside)
        ev = self._make_event('No Conn', base.replace(hour=9), base.replace(hour=11))
        self._add_seg(ev,
                      seg_start=base.replace(hour=9, minute=15),
                      seg_end=base.replace(hour=10, minute=30))
        html = self._day_html()
        self.assertNotIn('gantt-connector--late', html)
        self.assertNotIn('gantt-connector--early', html)

    def test_segment_starting_inside_bar_no_connector(self):
        """
        Segment that starts inside the scheduled bar but extends beyond
        it: not a disconnected case, so no connector.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 9-10, segment 9:30-11 (starts inside, ends past bar)
        ev = self._make_event('Overflow No Conn',
                              base.replace(hour=9), base.replace(hour=10))
        self._add_seg(ev,
                      seg_start=base.replace(hour=9, minute=30),
                      seg_end=base.replace(hour=11))
        html = self._day_html()
        self.assertNotIn('gantt-connector--late', html)
        self.assertNotIn('gantt-connector--early', html)


# ── 6. Scheduled boundary markers (gantt-sched-edge) ─────────────────────────

class GanttSchedEdgeMarkerTest(TestCase):
    """
    gantt-sched-edge markers appear only when a segment straddles the edge of
    the scheduled bar — i.e., partially overlaps the scheduled start or end.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='edge_user', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(
            name='Edge Track', asset_type=Asset.AssetType.TRACK, color='#dc2626'
        )

    def _day_html(self):
        resp = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertEqual(resp.status_code, 200)
        return resp.content.decode()

    def _make_event(self, title, start, end):
        ev = Event.objects.create(
            title=title, description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        return ev

    def _add_seg(self, ev, seg_start, seg_end):
        from cal.models import ActualTimeSegment
        return ActualTimeSegment.objects.create(event=ev, start=seg_start, end=seg_end)

    def test_left_edge_marker_when_segment_covers_scheduled_start(self):
        """
        Segment starts before the scheduled bar and ends inside it →
        left edge marker rendered.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 10-12, segment 9:30-11 → straddles left edge at 10:00
        ev = self._make_event('Left Edge', base.replace(hour=10), base.replace(hour=12))
        self._add_seg(ev,
                      seg_start=base.replace(hour=9, minute=30),
                      seg_end=base.replace(hour=11))
        html = self._day_html()
        self.assertIn('gantt-sched-edge', html)

    def test_right_edge_marker_when_segment_covers_scheduled_end(self):
        """
        Segment starts inside the scheduled bar and ends after it →
        right edge marker rendered.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 9-11, segment 10-12 → straddles right edge at 11:00
        ev = self._make_event('Right Edge', base.replace(hour=9), base.replace(hour=11))
        self._add_seg(ev,
                      seg_start=base.replace(hour=10),
                      seg_end=base.replace(hour=12))
        html = self._day_html()
        self.assertIn('gantt-sched-edge', html)

    def test_segment_inside_bar_no_edge_markers(self):
        """
        Segment that stays entirely within the scheduled bar must not produce
        any edge markers.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 9-12, segment 10-11 (entirely inside)
        ev = self._make_event('Inside No Edge', base.replace(hour=9), base.replace(hour=12))
        self._add_seg(ev,
                      seg_start=base.replace(hour=10),
                      seg_end=base.replace(hour=11))
        html = self._day_html()
        self.assertNotIn('gantt-sched-edge', html)

    def test_segment_entirely_outside_bar_no_edge_markers(self):
        """
        Segment entirely before the scheduled bar (late-start case) produces
        a connector but no edge markers.
        """
        base = datetime(2026, 4, 1, 0, 0, tzinfo=_local_tz)
        # Scheduled 11-13, segment 9-10 (entirely before)
        ev = self._make_event('Outside No Edge', base.replace(hour=11), base.replace(hour=13))
        self._add_seg(ev,
                      seg_start=base.replace(hour=9),
                      seg_end=base.replace(hour=10))
        html = self._day_html()
        self.assertNotIn('gantt-sched-edge', html)


# ════════════════════════════════════════════════════════════════════════════════
# New tests: decorators, helpers, api_event_approve, RADIO_CHANNEL_CHOICES
# ════════════════════════════════════════════════════════════════════════════════


# ── StaffRequiredDecoratorTest ────────────────────────────────────────────────

class StaffRequiredDecoratorTest(TestCase):
    """Tests for @staff_required (HTML) and @staff_required_api (JSON) decorators."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='dec_staff', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='dec_user', password='Testpass123!'
        )
        self.asset = Asset.objects.create(
            name='Dec Track', asset_type=Asset.AssetType.TRACK
        )
        now = timezone.now()
        self.event = Event.objects.create(
            title='Dec Event',
            description='',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            is_approved=True,
            created_by=self.staff,
        )
        self.event.assets.add(self.asset)

    # ── @staff_required (HTML views) ──────────────────────────────────────────

    def test_html_view_unauthenticated_redirects_to_login(self):
        """Unauthenticated request to a @staff_required view redirects to login."""
        url = reverse('cal:event_delete', args=[self.event.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/users/login/', resp['Location'])

    def test_html_view_non_staff_redirected_to_calendar(self):
        """Non-staff user on a @staff_required view is redirected to the calendar."""
        self.client.login(username='dec_user', password='Testpass123!')
        url = reverse('cal:event_delete', args=[self.event.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/cal/calendar/', resp['Location'])
        # Event must not have been deleted
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_html_view_staff_allowed_through(self):
        """Staff user on a @staff_required view is allowed through (not redirected to login or calendar)."""
        self.client.login(username='dec_staff', password='Testpass123!')
        url = reverse('cal:event_delete', args=[self.event.pk])
        resp = self.client.post(url)
        # Should redirect to calendar (success), not to /users/login/ or /cal/calendar/
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('/users/login/', resp['Location'])
        # Event should now be deleted
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_html_view_pending_events_non_staff_redirected(self):
        """Non-staff request to @staff_required pending_events is redirected to calendar."""
        self.client.login(username='dec_user', password='Testpass123!')
        resp = self.client.get(reverse('cal:pending_events'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/cal/calendar/', resp['Location'])

    def test_html_view_pending_events_staff_gets_200(self):
        """Staff request to @staff_required pending_events returns 200."""
        self.client.login(username='dec_staff', password='Testpass123!')
        resp = self.client.get(reverse('cal:pending_events'))
        self.assertEqual(resp.status_code, 200)

    # ── @staff_required_api (JSON API views) ─────────────────────────────────

    def test_api_view_unauthenticated_redirects(self):
        """Unauthenticated request to a @staff_required_api view redirects (login_required)."""
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        self.assertEqual(resp.status_code, 302)

    def test_api_view_non_staff_returns_403_json(self):
        """Non-staff user on a @staff_required_api view gets 403 with JSON error."""
        self.client.login(username='dec_user', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertIn('error', data)

    def test_api_view_staff_gets_200(self):
        """Staff user on a @staff_required_api view gets 200."""
        self.client.login(username='dec_staff', password='Testpass123!')
        resp = self.client.get(reverse('cal:dashboard_events_api'))
        self.assertEqual(resp.status_code, 200)


# ── ParseApiDatetimeTest ──────────────────────────────────────────────────────

class ParseApiDatetimeTest(TestCase):
    """Tests for helpers.parse_api_datetime()."""

    def setUp(self):
        from cal.helpers import parse_api_datetime
        self.parse = parse_api_datetime
        self.user = User.objects.create_user(username='padt_user', password='Testpass123!')
        now = timezone.now()
        self.event = Event.objects.create(
            title='PADT Event',
            description='',
            start_time=now,
            end_time=now + timedelta(hours=2),
            created_by=self.user,
        )

    def test_iso_z_suffix_parsed_as_utc(self):
        """ISO 8601 string with Z suffix is parsed correctly as UTC-aware datetime."""
        result = self.parse('2026-04-01T10:00:00Z')
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 0)

    def test_iso_with_offset_parsed_correctly(self):
        """ISO 8601 string with explicit timezone offset is parsed to an aware datetime."""
        result = self.parse('2026-04-01T10:00:00+05:00')
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    def test_naive_iso_string_made_aware(self):
        """Naive ISO string (no timezone) is made aware using the current timezone."""
        result = self.parse('2026-04-01T14:30:00')
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_hhmm_with_reference_event_uses_event_date(self):
        """HH:MM string with a reference_event returns a datetime on the event's start date."""
        result = self.parse('09:30', reference_event=self.event)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 30)
        # Date must match the event's start date in local time
        from django.utils.timezone import localtime
        self.assertEqual(result.date(), localtime(self.event.start_time).date())

    def test_hhmm_without_reference_event_returns_none(self):
        """HH:MM string without a reference_event returns None (no date anchor)."""
        result = self.parse('09:30')
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = self.parse('')
        self.assertIsNone(result)

    def test_none_returns_none(self):
        """None input returns None."""
        result = self.parse(None)
        self.assertIsNone(result)

    def test_invalid_string_returns_none(self):
        """Completely invalid string returns None."""
        result = self.parse('not-a-date-at-all')
        self.assertIsNone(result)

    def test_invalid_string_with_reference_event_returns_none(self):
        """Invalid string with reference_event still returns None when parse fails."""
        result = self.parse('99:99', reference_event=self.event)
        self.assertIsNone(result)


# ── ValidateRadioChannelTest ──────────────────────────────────────────────────

class ValidateRadioChannelTest(TestCase):
    """Tests for helpers.validate_radio_channel()."""

    def setUp(self):
        from cal.helpers import validate_radio_channel
        self.validate = validate_radio_channel

    def _body(self, channel):
        import json as _json
        return _json.dumps({'channel': channel}).encode()

    def test_valid_channel_11_returns_11(self):
        """Channel 11 (lower bound) is accepted and returned as int."""
        ch, err = self.validate(self._body(11))
        self.assertEqual(ch, 11)
        self.assertIsNone(err)

    def test_valid_channel_16_returns_16(self):
        """Channel 16 (upper bound) is accepted and returned as int."""
        ch, err = self.validate(self._body(16))
        self.assertEqual(ch, 16)
        self.assertIsNone(err)

    def test_valid_channel_14_returns_14(self):
        """Channel 14 (mid-range) is accepted."""
        ch, err = self.validate(self._body(14))
        self.assertEqual(ch, 14)
        self.assertIsNone(err)

    def test_null_channel_accepted(self):
        """null channel (clears the value) is accepted with ch=None and no error."""
        ch, err = self.validate(self._body(None))
        self.assertIsNone(ch)
        self.assertIsNone(err)

    def test_channel_10_out_of_range(self):
        """Channel 10 (below minimum) is rejected with 400 error response."""
        ch, err = self.validate(self._body(10))
        self.assertIsNone(ch)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 400)

    def test_channel_17_out_of_range(self):
        """Channel 17 (above maximum) is rejected with 400 error response."""
        ch, err = self.validate(self._body(17))
        self.assertIsNone(ch)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 400)

    def test_non_integer_channel_rejected(self):
        """Non-integer channel string is rejected with 400 error response."""
        import json as _json
        ch, err = self.validate(_json.dumps({'channel': 'abc'}).encode())
        self.assertIsNone(ch)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 400)

    def test_invalid_json_body_rejected(self):
        """Malformed JSON body returns 400 error response."""
        ch, err = self.validate(b'not json at all')
        self.assertIsNone(ch)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 400)

    def test_channel_string_number_coerced(self):
        """Channel sent as the string '13' is coerced to int 13 (int() accepts this)."""
        import json as _json
        ch, err = self.validate(_json.dumps({'channel': '13'}).encode())
        self.assertEqual(ch, 13)
        self.assertIsNone(err)


# ── ApiEventApproveTest ───────────────────────────────────────────────────────

class ApiEventApproveTest(TestCase):
    """Tests for POST /cal/api/event/<id>/approve/ endpoint."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='apv_staff', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(
            username='apv_user', password='Testpass123!'
        )
        self.track = Asset.objects.create(
            name='Approve Track', asset_type=Asset.AssetType.TRACK
        )
        now = timezone.now()
        self.pending = Event.objects.create(
            title='Pending to Approve',
            description='',
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            is_approved=False,
            created_by=self.regular,
        )
        self.pending.assets.add(self.track)

    def _url(self, event_id=None):
        return reverse('cal:api_event_approve', args=[event_id or self.pending.pk])

    def _post(self, event_id=None):
        self.client.login(username='apv_staff', password='Testpass123!')
        return self.client.post(self._url(event_id))

    def test_approve_pending_event_returns_approved_true(self):
        """Staff POST to approve a pending event returns {approved: True}."""
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('approved'))

    def test_approve_pending_event_sets_is_approved(self):
        """After approval, event.is_approved is True in the database."""
        self._post()
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_approved)

    def test_approve_response_includes_event_id(self):
        """Successful approval response includes the event id."""
        resp = self._post()
        data = resp.json()
        self.assertEqual(data.get('id'), self.pending.pk)

    def test_approve_with_conflict_returns_409(self):
        """Approving when an approved event conflicts returns 409 with error and conflicts list."""
        # Create a conflicting approved event on the same track and time
        conflicting = Event.objects.create(
            title='Conflicting Approved',
            description='',
            start_time=self.pending.start_time,
            end_time=self.pending.end_time,
            is_approved=True,
            created_by=self.staff,
        )
        conflicting.assets.add(self.track)

        resp = self._post()
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertIn('error', data)
        self.assertIn('conflicts', data)
        self.assertGreater(len(data['conflicts']), 0)

    def test_approve_with_conflict_does_not_approve(self):
        """When conflict is found, the event remains unapproved."""
        conflicting = Event.objects.create(
            title='Blocker',
            description='',
            start_time=self.pending.start_time,
            end_time=self.pending.end_time,
            is_approved=True,
            created_by=self.staff,
        )
        conflicting.assets.add(self.track)
        self._post()
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_approved)

    def test_approve_conflict_response_names_conflicting_event(self):
        """409 error message includes the title of the conflicting event."""
        conflicting = Event.objects.create(
            title='Named Blocker',
            description='',
            start_time=self.pending.start_time,
            end_time=self.pending.end_time,
            is_approved=True,
            created_by=self.staff,
        )
        conflicting.assets.add(self.track)
        resp = self._post()
        data = resp.json()
        self.assertIn('Named Blocker', data.get('error', ''))

    def test_non_staff_returns_403(self):
        """Non-staff POST to api_event_approve returns 403."""
        self.client.login(username='apv_user', password='Testpass123!')
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 403)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_approved)

    def test_nonexistent_event_returns_404(self):
        """POST for a non-existent event ID returns 404."""
        resp = self._post(event_id=99999)
        self.assertEqual(resp.status_code, 404)

    def test_get_request_returns_405(self):
        """GET to api_event_approve returns 405 (POST-only endpoint)."""
        self.client.login(username='apv_staff', password='Testpass123!')
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_unauthenticated_redirects(self):
        """Unauthenticated request to api_event_approve redirects to login."""
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/users/login/', resp['Location'])

    def test_no_conflict_non_overlapping_times_approves(self):
        """Approving an event with a non-overlapping approved event on the same track succeeds."""
        # Approved event at a completely different time
        other = Event.objects.create(
            title='Different Time',
            description='',
            start_time=self.pending.start_time + timedelta(hours=8),
            end_time=self.pending.end_time + timedelta(hours=8),
            is_approved=True,
            created_by=self.staff,
        )
        other.assets.add(self.track)
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_approved)


# ── RadioChannelChoicesTest ───────────────────────────────────────────────────

class RadioChannelChoicesTest(TestCase):
    """Tests for the module-level RADIO_CHANNEL_CHOICES constant in cal.models."""

    def test_radio_channel_choices_exists_at_module_level(self):
        """RADIO_CHANNEL_CHOICES is importable directly from cal.models."""
        from cal.models import RADIO_CHANNEL_CHOICES
        self.assertIsNotNone(RADIO_CHANNEL_CHOICES)

    def test_radio_channel_choices_covers_11_to_16(self):
        """RADIO_CHANNEL_CHOICES contains exactly channels 11 through 16."""
        from cal.models import RADIO_CHANNEL_CHOICES
        values = [ch for ch, _ in RADIO_CHANNEL_CHOICES]
        self.assertEqual(values, list(range(11, 17)))

    def test_radio_channel_choices_has_six_entries(self):
        """RADIO_CHANNEL_CHOICES has exactly 6 entries (channels 11-16)."""
        from cal.models import RADIO_CHANNEL_CHOICES
        self.assertEqual(len(RADIO_CHANNEL_CHOICES), 6)

    def test_asset_uses_radio_channel_choices(self):
        """Asset.radio_channel field uses the module-level RADIO_CHANNEL_CHOICES."""
        from cal.models import RADIO_CHANNEL_CHOICES
        field = Asset._meta.get_field('radio_channel')
        self.assertEqual(list(field.choices), list(RADIO_CHANNEL_CHOICES))

    def test_event_uses_radio_channel_choices(self):
        """Event.radio_channel field uses the module-level RADIO_CHANNEL_CHOICES."""
        from cal.models import RADIO_CHANNEL_CHOICES
        field = Event._meta.get_field('radio_channel')
        self.assertEqual(list(field.choices), list(RADIO_CHANNEL_CHOICES))
