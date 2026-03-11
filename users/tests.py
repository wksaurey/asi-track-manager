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
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form')

    def test_register_post_valid(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'Testpass123!',
            'password2': 'Testpass123!',
        })
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_post_invalid(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'pass',
            'password2': 'different',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())


class LoginViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='Testpass123!')

    def test_login_get(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_login_post_valid(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'Testpass123!',
        })
        self.assertRedirects(response, '/assets/')
