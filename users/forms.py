from django.contrib.auth.forms import UserCreationForm
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
