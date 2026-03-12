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
        self.assertTrue(str(user))


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
        self.assertRedirects(response, reverse('users:login'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

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
        self.assertRedirects(response, '/assets/')

    def test_login_post_invalid(self):
        response = self.client.post(reverse('users:login'), {
            'username': 'testuser',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_redirects_next(self):
        response = self.client.post('/users/login/?next=/reservations/', {
            'username': 'testuser',
            'password': 'Testpass123!',
        })
        self.assertRedirects(response, '/reservations/')


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
