"""
URL configuration for the ``cal`` application.

All routes are namespaced under ``cal:`` (e.g. ``reverse('cal:calendar')``).
The root path redirects to the calendar; all other paths require login,
enforced at the view level.
"""

from django.urls import path
from . import views

app_name = 'cal'
urlpatterns = [
    # ── Authentication ─────────────────────────────────────────────────────
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Root redirect ──────────────────────────────────────────────────────
    path('', views.index, name='index'),

    # ── Calendar views (month / week / day) ────────────────────────────────
    path('calendar/', views.CalendarView.as_view(), name='calendar'),

    # ── Event CRUD + approval ──────────────────────────────────────────────
    path('event/new/',                     views.event,          name='event_new'),
    path('event/edit/<int:event_id>/',     views.event,          name='event_edit'),
    path('event/delete/<int:event_id>/',   views.event_delete,   name='event_delete'),
    path('event/approve/<int:event_id>/',  views.event_approve,  name='event_approve'),
    path('events/pending/',                views.pending_events, name='pending_events'),

    # ── Asset management ───────────────────────────────────────────────────
    path('assets/',                        views.asset_list,   name='asset_list'),
    path('assets/new/',                    views.asset_create, name='asset_create'),
    path('assets/edit/<int:asset_id>/',    views.asset_edit,   name='asset_edit'),
    path('assets/delete/<int:asset_id>/',   views.asset_delete, name='asset_delete'),
    path('assets/<int:asset_id>/',         views.asset_detail, name='asset_detail'),
]
