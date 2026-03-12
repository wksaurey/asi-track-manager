from django.contrib import admin
from .models import Track, Vehicle

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
