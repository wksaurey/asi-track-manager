from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTest(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(username='testuser', password='pass1234!')
        self.assertEqual(user.username, 'testuser')
        self.assertIsInstance(user, User)

    def test_user_str(self):
        user = User.objects.create_user(username='testuser', password='pass1234!')
        self.assertEqual(str(user), 'testuser')


class RegisterViewTest(TestCase):
    def test_register_get(self):
        response = self.client.get(reverse('users:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form')
        self.assertTemplateUsed(response, 'users/register.html')

    def test_register_post_valid(self):
        response = self.client.post(reverse('users:register'), {
            'username': 'newuser',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertRedirects(response, reverse('cal:calendar'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        # User should be auto-logged in after registration
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_register_post_invalid_passwords(self):
        response = self.client.post(reverse('users:register'), {
            'username': 'newuser',
            'password1': 'pass',
            'password2': 'different',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_register_post_duplicate_username(self):
        User.objects.create_user(username='existing', password='Testpass123!')
        response = self.client.post(reverse('users:register'), {
            'username': 'existing',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='existing').count(), 1)


class LoginViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Testpass123!')

    def test_login_get(self):
        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_login_post_valid(self):
        response = self.client.post(reverse('users:login'), {
            'username': 'testuser',
            'password': 'Testpass123!',
        })
        self.assertRedirects(response, '/cal/calendar/')

    def test_login_post_invalid(self):
        response = self.client.post(reverse('users:login'), {
            'username': 'testuser',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_redirects_next(self):
        response = self.client.post('/users/login/?next=/cal/calendar/', {
            'username': 'testuser',
            'password': 'Testpass123!',
        })
        self.assertRedirects(response, '/cal/calendar/')


class LogoutViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Testpass123!')
        self.client.login(username='testuser', password='Testpass123!')

    def test_logout_redirects(self):
        response = self.client.post(reverse('users:logout'))
        self.assertRedirects(response, '/users/login/')

    def test_logout_unauthenticates(self):
        self.client.post(reverse('users:logout'))
        response = self.client.get(reverse('users:login'))
        self.assertFalse(response.wsgi_request.user.is_authenticated)


# ── UI Redesign: verify users/ templates after promotion to base.html ─────────

class UsersTemplateBaseIntegrationTest(TestCase):
    """These tests verify the users/ templates remain correct after the UI redesign.

    test_login_uses_correct_template and test_register_uses_correct_template
    remain GREEN before and after implementation (template names don't change).

    test_login_extends_global_base and test_register_extends_global_base are
    RED before implementation (templates are standalone HTML, not extending base.html).
    """

    def test_login_uses_correct_template(self):
        """users:login must render users/login.html (template name must not change)."""
        response = self.client.get(reverse('users:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_register_uses_correct_template(self):
        """users:register must render users/register.html (template name must not change)."""
        response = self.client.get(reverse('users:register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')

    def test_login_extends_global_base(self):
        """users/login.html must extend the project-wide base.html after redesign.

        RED until: users/login.html is rewritten to {% extends 'base.html' %} and
        BASE_DIR/'templates' is in DIRS.
        """
        response = self.client.get(reverse('users:login'))
        self.assertTemplateUsed(response, 'base.html')

    def test_register_extends_global_base(self):
        """users/register.html must extend the project-wide base.html after redesign.

        RED until: users/register.html is rewritten to {% extends 'base.html' %}.
        """
        response = self.client.get(reverse('users:register'))
        self.assertTemplateUsed(response, 'base.html')


# ── Bug 4: auto-login after registration + safe next redirect ─────────────────

class RegistrationAutoLoginTest(TestCase):
    """Bug 4: After valid registration, user must be auto-logged in and redirected safely."""

    def test_registration_auto_logs_in_user(self):
        """After valid registration POST, the user must be authenticated."""
        response = self.client.post(reverse('users:register'), {
            'username': 'newuser',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_registration_with_safe_next_redirects_to_next(self):
        """After valid registration with a safe ?next=, redirect goes to that URL."""
        url = reverse('users:register') + '?next=/cal/calendar/'
        response = self.client.post(url, {
            'username': 'nextuser',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertRedirects(response, '/cal/calendar/')

    def test_registration_with_unsafe_next_redirects_to_calendar(self):
        """After valid registration with an unsafe next URL, redirect falls back to calendar."""
        url = reverse('users:register') + '?next=http://evil.com'
        response = self.client.post(url, {
            'username': 'eviluser',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertRedirects(response, reverse('cal:calendar'))


# ── Test Gap 1: Toggle admin endpoint ─────────────────────────────────────────

class ToggleAdminTest(TestCase):
    """Tests for the users:toggle_admin endpoint (staff-only, POST-only)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')

    def test_staff_can_toggle_user_admin(self):
        """Staff POSTs to toggle_admin with another user's ID -> 200, user.is_staff flips."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:toggle_admin', args=[self.regular.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_staff)

    def test_self_toggle_returns_400(self):
        """Staff tries to toggle own status -> 400 error."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:toggle_admin', args=[self.staff.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

    def test_non_staff_gets_403(self):
        """Regular user POSTs -> 403."""
        self.client.login(username='employee', password='Testpass123!')
        url = reverse('users:toggle_admin', args=[self.staff.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_get_returns_405(self):
        """GET request -> 405 (require_POST decorator)."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:toggle_admin', args=[self.regular.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_superuser_protection(self):
        """Non-superuser staff tries to toggle a superuser -> 403."""
        superuser = User.objects.create_superuser(
            username='superadmin', password='Testpass123!'
        )
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:toggle_admin', args=[superuser.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)


# ── Test Gap 2: Delete user endpoint ──────────────────────────────────────────

class DeleteUserTest(TestCase):
    """Tests for the users:delete_user endpoint (staff-only, POST-only)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='admin', password='Testpass123!', is_staff=True
        )
        self.regular = User.objects.create_user(username='employee', password='Testpass123!')

    def test_staff_can_delete_user(self):
        """Staff POSTs to delete_user with another user's ID -> 200, user deleted."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:delete_user', args=[self.regular.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.regular.pk).exists())

    def test_self_delete_returns_400(self):
        """Staff tries to delete self -> 400."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:delete_user', args=[self.staff.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

    def test_non_staff_gets_403(self):
        """Regular user POSTs -> 403."""
        self.client.login(username='employee', password='Testpass123!')
        url = reverse('users:delete_user', args=[self.staff.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_get_returns_405(self):
        """GET request -> 405 (require_POST decorator)."""
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:delete_user', args=[self.regular.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_events_orphaned_after_delete(self):
        """Delete a user who created events -> events still exist but created_by=None."""
        from cal.models import Asset, Event
        from datetime import timedelta
        from django.utils import timezone
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=2)
        event = Event.objects.create(
            title='Orphan Test',
            description='desc',
            start_time=start,
            end_time=end,
            created_by=self.regular,
        )
        self.client.login(username='admin', password='Testpass123!')
        url = reverse('users:delete_user', args=[self.regular.pk])
        self.client.post(url)
        event.refresh_from_db()
        self.assertIsNone(event.created_by)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())


class ProfileViewAccessTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='profuser', password='Testpass123!')
        self.url = reverse('users:profile')

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.url)

    def test_logged_in_gets_profile_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username_form', resp.context)
        self.assertIn('password_form', resp.context)


class ProfileUsernameChangeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='origname', password='Testpass123!')
        self.url = reverse('users:profile')
        self.client.force_login(self.user)

    def test_valid_username_change(self):
        resp = self.client.post(self.url, {
            'action': 'change_username', 'username': 'newname',
        })
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newname')

    def test_username_normalized_to_lowercase(self):
        self.client.post(self.url, {
            'action': 'change_username', 'username': 'MixedCase',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'mixedcase')

    def test_duplicate_username_case_insensitive(self):
        User.objects.create_user(username='taken', password='Testpass123!')
        resp = self.client.post(self.url, {
            'action': 'change_username', 'username': 'Taken',
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form with errors
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'origname')

    def test_same_username_accepted(self):
        resp = self.client.post(self.url, {
            'action': 'change_username', 'username': 'origname',
        })
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'origname')

    def test_blank_username_rejected(self):
        resp = self.client.post(self.url, {
            'action': 'change_username', 'username': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'origname')


class ProfilePasswordChangeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pwuser', password='Testpass123!')
        self.url = reverse('users:profile')
        self.client.force_login(self.user)

    def test_valid_password_change(self):
        resp = self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'Testpass123!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Newpass456!',
        })
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Newpass456!'))

    def test_session_stays_alive_after_password_change(self):
        self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'Testpass123!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Newpass456!',
        })
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)  # still logged in, not redirected

    def test_wrong_current_password(self):
        self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'WrongPass!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Newpass456!',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Testpass123!'))

    def test_mismatched_new_passwords(self):
        self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'Testpass123!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Different789!',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Testpass123!'))


class ProfileBothChangesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='bothuser', password='Testpass123!')
        self.url = reverse('users:profile')
        self.client.force_login(self.user)

    def test_change_username_then_password(self):
        self.client.post(self.url, {
            'action': 'change_username', 'username': 'newboth',
        })
        self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'Testpass123!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Newpass456!',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newboth')
        self.assertTrue(self.user.check_password('Newpass456!'))

    def test_success_message_on_username_change(self):
        resp = self.client.post(self.url, {
            'action': 'change_username', 'username': 'msguser',
        }, follow=True)
        messages = list(resp.context['messages'])
        self.assertTrue(any('Username' in str(m) for m in messages))

    def test_success_message_on_password_change(self):
        resp = self.client.post(self.url, {
            'action': 'change_password',
            'old_password': 'Testpass123!',
            'new_password1': 'Newpass456!',
            'new_password2': 'Newpass456!',
        }, follow=True)
        messages = list(resp.context['messages'])
        self.assertTrue(any('Password' in str(m) for m in messages))
