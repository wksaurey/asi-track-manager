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
