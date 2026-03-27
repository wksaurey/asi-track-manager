"""
Tests for ASI Track Manager v1.1 features.

Covers four new feature areas:
1. Timezone support (America/New_York)
2. Feedback submission
3. Event visibility (cross-user read-only viewing)
4. Day view scroll behavior

These tests follow the same patterns as cal/tests.py — each test class
creates its own data, uses self.client for view tests, and model instances
for model tests.

NOTE: Many of these tests are intentionally RED until the corresponding
v1.1 feature is implemented. They serve as a specification and will go
GREEN as each feature lands.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Asset, Event

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════════
# 1. Timezone Tests
# ════════════════════════════════════════════════════════════════════════════════

@override_settings(TIME_ZONE='America/New_York')
class TimezoneDisplayTests(TestCase):
    """Verify events store and display times correctly in America/New_York.

    The app should interpret user-submitted times as Eastern and render
    them back in Eastern, regardless of the internal UTC storage.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='tzuser', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(name='TZ Track', asset_type=Asset.AssetType.TRACK)

    def test_time_range_displays_in_eastern(self):
        """_time_range should format times using the active timezone (Eastern)."""
        import zoneinfo
        eastern = zoneinfo.ZoneInfo('America/New_York')
        # 2:00 PM Eastern = 6:00 PM UTC (during EDT, offset -4)
        start = datetime(2026, 6, 15, 18, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Eastern Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        # _time_range should show 2:00-4:00 PM (Eastern), not 6:00-8:00 PM (UTC)
        time_range = ev._time_range
        self.assertIn('2:00', time_range, f"Expected 2:00 PM Eastern in time range, got: {time_range}")
        self.assertIn('4:00', time_range, f"Expected 4:00 PM Eastern in time range, got: {time_range}")

    def test_gantt_block_position_reflects_local_time(self):
        """A 2:00 PM Eastern event should be positioned at the 2 PM mark on the Gantt chart.

        2 PM = 480 minutes after 6 AM start. 480/840 * 100 = 57.1429%.
        If the app incorrectly uses UTC (6 PM), position would be 720/840 = 85.7143%.
        """
        # 2:00 PM Eastern on June 15 = 6:00 PM UTC (EDT, offset -4)
        start = datetime(2026, 6, 15, 18, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Gantt Position Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-6-15')
        content = response.content.decode()
        # Should be positioned at 57.1429% (2 PM Eastern), not 85.7143% (6 PM UTC)
        self.assertIn('left:58.3333%', content,
                       "Event should be positioned at 2 PM Eastern (840/1440 = 58.3333%), "
                       "not at UTC time position")

    def test_event_near_midnight_utc_appears_on_correct_local_date(self):
        """An event at 11 PM Eastern (3 AM UTC next day) should appear on the Eastern date.

        June 15 11:00 PM Eastern = June 16 3:00 AM UTC.
        The event should appear on the June 15 day view, not June 16.
        """
        # 11:00 PM Eastern June 15 = 3:00 AM UTC June 16
        start = datetime(2026, 6, 16, 3, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 6, 16, 5, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Late Night Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        # Should appear on June 15 (Eastern date)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-6-15')
        self.assertContains(response, 'Late Night Test',
                           msg_prefix="11 PM Eastern event should appear on the Eastern date")

    def test_event_form_preserves_entered_time(self):
        """When a user enters 9:00 AM in the form, the event edit page should show 9:00 AM back.

        This tests the round-trip: form submission -> DB storage -> form display.
        """
        start_str = '2026-06-15T09:00'
        end_str = '2026-06-15T11:00'
        # Create event via POST
        self.client.post(reverse('cal:event_new'), {
            'title': 'Round Trip Test',
            'description': '',
            'start_time': start_str,
            'end_time': end_str,
            'assets': [self.track.pk],
        })
        ev = Event.objects.get(title='Round Trip Test')
        # Edit page should show the originally entered time
        response = self.client.get(reverse('cal:event_edit', args=[ev.pk]))
        content = response.content.decode()
        # The form should contain the value 2026-06-15T09:00
        self.assertIn('09:00', content,
                       "Edit form should show the originally entered time (9:00 AM)")

    def test_dst_spring_forward_march(self):
        """Events during DST spring-forward (March) should be handled correctly.

        March 8 2026: EDT begins. 2:00 AM EST -> 3:00 AM EDT.
        An event at 3:00 PM EDT should render correctly.
        """
        # 3:00 PM Eastern on March 9 (after spring forward) = 7:00 PM UTC
        start = datetime(2026, 3, 9, 19, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 3, 9, 21, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='DST Spring Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-3-9')
        self.assertContains(response, 'DST Spring Test')

    def test_dst_fall_back_november(self):
        """Events during DST fall-back (November) should be handled correctly.

        November 1 2026: EST begins. 2:00 AM EDT -> 1:00 AM EST.
        """
        # 1:00 PM Eastern on November 2 (after fall back, EST) = 6:00 PM UTC
        start = datetime(2026, 11, 2, 18, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 11, 2, 20, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='DST Fall Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-11-2')
        self.assertContains(response, 'DST Fall Test')

    def test_month_view_event_times_display_in_eastern(self):
        """Event times in month view should display in Eastern timezone."""
        # 2:00 PM Eastern = 6:00 PM UTC (during EDT)
        start = datetime(2026, 6, 15, 18, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Month TZ Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(
            reverse('cal:calendar') + '?view=month&month=2026-6'
        )
        content = response.content.decode()
        # Should show 2:00 PM times, not 6:00 PM
        self.assertIn('2:00', content,
                       "Month view should display times in Eastern timezone")

    def test_week_view_events_on_correct_day(self):
        """Events should appear on the correct Eastern day in week view."""
        # 11:00 PM Eastern June 15 = 3:00 AM UTC June 16
        start = datetime(2026, 6, 16, 3, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 6, 16, 5, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Week TZ Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        # Week view for the week containing June 15 (Monday June 15)
        response = self.client.get(
            reverse('cal:calendar') + '?view=week&date=2026-6-15'
        )
        self.assertContains(response, 'Week TZ Test')


# ════════════════════════════════════════════════════════════════════════════════
# 2. Feedback Feature Tests
# ════════════════════════════════════════════════════════════════════════════════

class FeedbackSubmissionTests(TestCase):
    """Test feedback submission and admin visibility.

    The feedback feature allows users to submit bug reports, feature requests,
    and general feedback via a floating button present on all pages. Submissions
    are stored in the DB and visible to admins.

    RED until: Feedback model, view, and URL are implemented.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='fbuser', password='Testpass123!')
        self.admin = User.objects.create_user(
            username='fbadmin', password='Testpass123!', is_staff=True
        )
        self.url = '/cal/api/feedback/'

    def test_post_with_valid_data_returns_success(self):
        """POST to /cal/api/feedback/ with valid data returns 200/201."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'bug',
            'subject': 'Mobile calendar issue',
            'message': 'The calendar does not load on mobile.',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertIn(response.status_code, [200, 201])

    def test_post_with_missing_message_returns_400(self):
        """POST with missing required 'message' field returns 400."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'bug',
            'subject': 'No message',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertEqual(response.status_code, 400)

    def test_post_with_missing_subject_returns_400(self):
        """POST with missing required 'subject' field returns 400."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'bug',
            'message': 'Some feedback',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_user_gets_redirected(self):
        """Unauthenticated POST to feedback endpoint redirects to login."""
        response = self.client.post(self.url, {
            'category': 'bug',
            'subject': 'Test',
            'message': 'Test message',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)

    def test_feedback_saved_with_correct_user(self):
        """Feedback entry is saved with the correct user who submitted it."""
        from cal.models import Feedback
        self.client.login(username='fbuser', password='Testpass123!')
        self.client.post(self.url, {
            'category': 'feature',
            'subject': 'Recurring events',
            'message': 'Please add recurring events.',
            'page_url': 'http://localhost/cal/calendar/',
        })
        fb = Feedback.objects.latest('id')
        self.assertEqual(fb.user, self.user)
        self.assertEqual(fb.category, 'feature')
        self.assertEqual(fb.message, 'Please add recurring events.')

    def test_category_bug_accepted(self):
        """Category 'bug' is a valid choice."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'bug',
            'subject': 'Bug report',
            'message': 'Bug feedback',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertIn(response.status_code, [200, 201])

    def test_category_feature_accepted(self):
        """Category 'feature' is a valid choice."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'feature',
            'subject': 'Feature request',
            'message': 'Feature feedback',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertIn(response.status_code, [200, 201])

    def test_category_other_accepted(self):
        """Category 'other' is a valid choice."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'other',
            'subject': 'General',
            'message': 'General feedback',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertIn(response.status_code, [200, 201])

    def test_get_returns_405(self):
        """GET request to feedback endpoint returns 405 (POST only)."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_page_url_auto_captured(self):
        """The page_url field should be saved from the submission data."""
        from cal.models import Feedback
        self.client.login(username='fbuser', password='Testpass123!')
        self.client.post(self.url, {
            'category': 'bug',
            'subject': 'URL test',
            'message': 'URL capture test',
            'page_url': 'http://localhost/cal/assets/',
        })
        fb = Feedback.objects.latest('id')
        self.assertEqual(fb.page_url, 'http://localhost/cal/assets/')

    def test_invalid_category_returns_400(self):
        """POST with an invalid category value returns 400."""
        self.client.login(username='fbuser', password='Testpass123!')
        response = self.client.post(self.url, {
            'category': 'invalid_category',
            'subject': 'Bad category',
            'message': 'Some feedback',
            'page_url': 'http://localhost/cal/calendar/',
        })
        self.assertEqual(response.status_code, 400)


class FeedbackButtonPresenceTests(TestCase):
    """Test that the feedback button appears/disappears based on auth state.

    RED until: base.html includes the feedback button markup.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='fbpresence', password='Testpass123!')

    def test_feedback_button_visible_when_logged_in(self):
        """Authenticated users should see the feedback button on the calendar page."""
        self.client.login(username='fbpresence', password='Testpass123!')
        response = self.client.get(reverse('cal:calendar'))
        self.assertContains(response, 'feedback-fab',
                           msg_prefix="Feedback button should be present for logged-in users")

    def test_feedback_button_not_visible_when_logged_out(self):
        """Unauthenticated users should NOT see the feedback button on login page."""
        response = self.client.get(reverse('users:login'))
        self.assertNotContains(response, 'feedback-fab',
                              msg_prefix="Feedback button should not appear for logged-out users")

    def test_feedback_button_visible_on_asset_list(self):
        """Feedback button should appear on the asset list page."""
        self.client.login(username='fbpresence', password='Testpass123!')
        response = self.client.get(reverse('cal:asset_list'))
        self.assertContains(response, 'feedback-fab')


# ════════════════════════════════════════════════════════════════════════════════
# 3. Event Visibility Tests (cross-user read-only viewing)
# ════════════════════════════════════════════════════════════════════════════════

class EventVisibilityTests(TestCase):
    """Test cross-user event viewing.

    In v1.1, non-owners should be able to VIEW (but not edit) other users'
    events. Currently (v1.0) they are redirected. These tests specify the
    new behavior.

    RED until: Event view is updated to allow read-only access for non-owners.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username='evowner', password='Testpass123!')
        self.viewer = User.objects.create_user(username='evviewer', password='Testpass123!')
        self.admin = User.objects.create_user(
            username='evadmin', password='Testpass123!', is_staff=True
        )
        self.track = Asset.objects.create(name='Vis Track', asset_type=Asset.AssetType.TRACK)
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)
        self.event = Event.objects.create(
            title='Owner Event',
            description='Test description',
            start_time=self.start,
            end_time=self.end,
            created_by=self.owner,
            is_approved=True,
        )
        self.event.assets.add(self.track)

    def test_non_owner_can_get_event_page(self):
        """Non-owner GET to /cal/event/edit/<id>/ returns 200 (read-only view, not redirect)."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200,
                        "Non-owner should see a read-only view (200), not be redirected (302)")

    def test_non_owner_cannot_post_edit(self):
        """Non-owner POST to edit another user's event should be rejected."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.post(url, {
            'title': 'Hacked Title',
            'description': '',
            'start_time': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_time': self.end.strftime('%Y-%m-%dT%H:%M'),
            'assets': [self.track.pk],
        })
        # Should either redirect or return 403, but NOT save changes
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Owner Event',
                        "Non-owner POST should not modify the event")

    def test_non_owner_sees_read_only_context(self):
        """Non-owner GET response context should include can_edit=False."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get('can_edit', True),
                        "Context should have can_edit=False for non-owners")

    def test_owner_can_edit_own_event(self):
        """Owner can still access the edit view and modify their event."""
        self.client.login(username='evowner', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Context should indicate editing is allowed
        can_edit = response.context.get('can_edit', True)
        self.assertTrue(can_edit, "Owner should have can_edit=True")

    def test_admin_can_edit_any_event(self):
        """Admin can edit any user's event."""
        self.client.login(username='evadmin', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        can_edit = response.context.get('can_edit', True)
        self.assertTrue(can_edit, "Admin should have can_edit=True for any event")

    def test_read_only_view_shows_creator_banner(self):
        """Read-only view should display a banner showing the event creator's name."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        content = response.content.decode()
        self.assertIn('evowner', content,
                       "Read-only view should show the creator's username")

    def test_read_only_view_no_save_button(self):
        """Read-only view should NOT show a Save button."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        content = response.content.decode()
        # The page should not have an active save button visible to non-owners
        # (it may exist hidden, but should not be actionable)
        self.assertNotContains(response, 'event-save-btn',
                              msg_prefix="Read-only view should not display the save button")

    def test_read_only_view_no_delete_button(self):
        """Read-only view should NOT show a Delete button."""
        self.client.login(username='evviewer', password='Testpass123!')
        url = reverse('cal:event_edit', args=[self.event.pk])
        response = self.client.get(url)
        self.assertNotContains(response, 'event-delete-btn',
                              msg_prefix="Read-only view should not display the delete button")


class EventCreatorNameInCalendarTests(TestCase):
    """Test that creator name is visible on calendar event HTML.

    RED until: get_html_url and Gantt block rendering include creator name.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='creatoruser', password='Testpass123!')
        self.track = Asset.objects.create(name='Creator Track', asset_type=Asset.AssetType.TRACK)
        self.start = datetime(2026, 4, 1, 10, 0, tzinfo=dt_timezone.utc)
        self.end = datetime(2026, 4, 1, 12, 0, tzinfo=dt_timezone.utc)
        self.event = Event.objects.create(
            title='Creator Event',
            description='',
            start_time=self.start,
            end_time=self.end,
            created_by=self.user,
            is_approved=True,
        )
        self.event.assets.add(self.track)

    def test_creator_name_in_get_html_url(self):
        """get_html_url should include the creator's username."""
        html = self.event.get_html_url
        self.assertIn('creatoruser', html,
                       "get_html_url should display the creator's username")

    def test_creator_name_in_gantt_block(self):
        """Day view Gantt block should include the creator's username in the tooltip or text."""
        viewer = User.objects.create_user(username='ganttviewer', password='Testpass123!')
        self.client.force_login(viewer)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        content = response.content.decode()
        self.assertIn('creatoruser', content,
                       "Gantt block should include the event creator's username")

    def test_creator_name_in_month_view(self):
        """Month view should include the creator's username in event rendering."""
        viewer = User.objects.create_user(username='monthviewer', password='Testpass123!')
        self.client.force_login(viewer)
        response = self.client.get(
            reverse('cal:calendar') + '?view=month&month=2026-4'
        )
        self.assertContains(response, 'creatoruser',
                           msg_prefix="Month view should display event creator's username")

    def test_creator_name_in_week_view(self):
        """Week view should include the creator's username in event rendering."""
        viewer = User.objects.create_user(username='weekviewer', password='Testpass123!')
        self.client.force_login(viewer)
        response = self.client.get(
            reverse('cal:calendar') + '?view=week&date=2026-3-30'
        )
        self.assertContains(response, 'creatoruser',
                           msg_prefix="Week view should display event creator's username")


# ════════════════════════════════════════════════════════════════════════════════
# 4. Day View Scroll Tests
# ════════════════════════════════════════════════════════════════════════════════

class DayViewScrollDataTests(TestCase):
    """Test day view data attributes for scroll behavior.

    The day view should include data attributes that JavaScript uses to
    auto-scroll the Gantt chart to show current events or current time.

    RED until: formatdayview outputs scroll-related data attributes.
    """

    def setUp(self):
        self.user = User.objects.create_user(username='scrolluser', password='Testpass123!')
        self.client.force_login(self.user)
        self.track = Asset.objects.create(name='Scroll Track', asset_type=Asset.AssetType.TRACK)

    def test_gantt_view_has_data_gantt_start(self):
        """gantt-view div should have a data-gantt-start attribute (start hour of the axis)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-gantt-start',
                           msg_prefix="gantt-view should include data-gantt-start attribute")

    def test_gantt_view_has_data_gantt_mins(self):
        """gantt-view div should have a data-gantt-mins attribute (total minutes in the axis)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-gantt-mins',
                           msg_prefix="gantt-view should include data-gantt-mins attribute")

    def test_data_gantt_start_value_is_0(self):
        """data-gantt-start should be 0 (midnight, full 24h view)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-gantt-start="0"',
                           msg_prefix="data-gantt-start should be 0")

    def test_data_gantt_mins_value_is_1440(self):
        """data-gantt-mins should be 1440 (24 hours * 60 minutes)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-gantt-mins="1440"',
                           msg_prefix="data-gantt-mins should be 1440")

    def test_data_event_earliest_reflects_event_time(self):
        """When events exist, data-event-earliest should reflect the earliest event start time."""
        start = datetime(2026, 4, 1, 8, 30, tzinfo=dt_timezone.utc)
        end = datetime(2026, 4, 1, 10, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Early Event', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-event-earliest',
                           msg_prefix="Should include data-event-earliest when events exist")

    def test_data_event_latest_reflects_event_time(self):
        """When events exist, data-event-latest should reflect the latest event end time."""
        start = datetime(2026, 4, 1, 14, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 4, 1, 17, 30, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Late Event', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-event-latest',
                           msg_prefix="Should include data-event-latest when events exist")

    def test_day_view_no_events_still_renders(self):
        """Day view with no events should still render correctly (no crash)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gantt-view')

    def test_full_24_hour_axis_markers(self):
        """Day view should render axis hour markers from 6 AM through 8 PM (15 markers)."""
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        content = response.content.decode()
        # Check for representative hour labels
        self.assertIn('6am', content, "Should have 6am axis marker")
        self.assertIn('12pm', content, "Should have 12pm axis marker")
        self.assertIn('8pm', content, "Should have 8pm axis marker")

    def test_event_blocks_positioned_correctly(self):
        """Event at 10 AM UTC = 6 AM Eastern. 360/1440 = 25%."""
        start = datetime(2026, 4, 1, 10, 0, tzinfo=dt_timezone.utc)
        end = datetime(2026, 4, 1, 12, 0, tzinfo=dt_timezone.utc)
        ev = Event.objects.create(
            title='Position Scroll Test', description='',
            start_time=start, end_time=end,
            created_by=self.user, is_approved=True,
        )
        ev.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        # 10 AM UTC = 6 AM EDT. 360/1440 * 100 = 25%
        self.assertContains(response, 'left:25.0%')

    def test_multiple_events_data_attributes(self):
        """With multiple events, data-event-earliest/latest should reflect the full range."""
        # Early event: 7 AM
        ev1 = Event.objects.create(
            title='Morning', description='',
            start_time=datetime(2026, 4, 1, 7, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 4, 1, 9, 0, tzinfo=dt_timezone.utc),
            created_by=self.user, is_approved=True,
        )
        ev1.assets.add(self.track)
        # Late event: 5 PM
        ev2 = Event.objects.create(
            title='Afternoon', description='',
            start_time=datetime(2026, 4, 1, 17, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 4, 1, 19, 0, tzinfo=dt_timezone.utc),
            created_by=self.user, is_approved=True,
        )
        ev2.assets.add(self.track)
        response = self.client.get(reverse('cal:calendar') + '?view=day&date=2026-4-1')
        self.assertContains(response, 'data-event-earliest')
        self.assertContains(response, 'data-event-latest')
