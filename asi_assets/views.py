from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Track, Vehicle


def home(request):
    return render(request, 'asi-assets/home.html')


@login_required
def index(request):
    # Placeholder for index view
    tracks = Track.objects.all()
    vehicles = Vehicle.objects.all()
    context = {
        "tracks": tracks,
        "vehicles": vehicles,
    }
    return render(request, "asi-assets/index.html", context)

@login_required
def track_detail(request, track_id):
    # Placeholder for track detail view
    context = {
        "track": get_object_or_404(Track, pk=track_id)
    }
    return render(request, "asi-assets/track_detail.html", context)

@login_required
def vehicle_detail(request, vehicle_id):
    # Placeholder for vehicle detail view
    context = {
        "vehicle": get_object_or_404(Vehicle, pk=vehicle_id)
    }
    return render(request, "asi-assets/vehicle_detail.html", context)   
