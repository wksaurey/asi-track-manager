from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    is_developer = models.BooleanField(default=False)
