"""
Custom view decorators for the ASI Track Manager calendar application.

Provides staff-only access decorators that combine login_required with
is_staff checks, eliminating repetitive inline authorization patterns.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse


def staff_required(view_func):
    """Decorator for HTML views that require staff access. Redirects non-staff to calendar."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return HttpResponseRedirect(reverse('cal:calendar'))
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_required_api(view_func):
    """Decorator for JSON API views that require staff access. Returns 403 for non-staff."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper
