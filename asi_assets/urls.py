from django.urls import path

from . import views

urlpatterns = [
    path('assets/', views.index, name='index'),
    path("track/<int:track_id>/", views.track_detail, name="track_detail"),
    path("vehicle/<int:vehicle_id>/", views.vehicle_detail, name="vehicle_detail"),
]