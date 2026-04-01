from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from .models import User


class UserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove all password help text so no requirements are shown to the user.
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''

    def clean_username(self):
        """Normalize username to lowercase to prevent case-variant duplicates."""
        return self.cleaned_data['username'].lower()


class UsernameChangeForm(forms.Form):
    username = forms.CharField(max_length=150, label='New username')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data['username'].lower()
        if User.objects.filter(username__iexact=username).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return username


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['old_password'].help_text = ''
        self.fields['new_password1'].help_text = ''
        self.fields['new_password2'].help_text = ''
