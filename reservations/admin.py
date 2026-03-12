from django.contrib import admin
from .models import Reservation

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('user', 'start_time', 'end_time', 'created_at')
    list_filter = ('user',)
    search_fields = ('user__username',)
    ordering = ('-start_time',)
