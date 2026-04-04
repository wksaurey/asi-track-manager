from django.conf import settings

from .models import Event


def pending_count(request):
    if request.user.is_authenticated and request.user.is_staff:
        return {'pending_count': Event.objects.filter(is_approved=False).count()}
    return {'pending_count': 0}


def app_timezone(request):
    """Expose Django's TIME_ZONE setting to templates for use by JS."""
    return {'app_timezone': settings.TIME_ZONE}
