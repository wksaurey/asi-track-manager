from multiprocessing import context

from django.shortcuts import render

from .models import Track, Vehicle

# Create your views here.
def index(request):
    # Placeholder for index view
    tracks = Track.objects.all()
    vehicles = Vehicle.objects.all()
    context = {
        "tracks": tracks,
        "vehicles": vehicles,
    }
    return render(request, "asi-assets/index.html", context)

def track_detail(request, track_id):
    # Placeholder for track detail view
    context = {
        "track": Track.objects.get(id=track_id)
    }
    return render(request, "asi-assets/track_detail.html", context)

def vehicle_detail(request, vehicle_id):
    # Placeholder for vehicle detail view
    context = {
        "vehicle": Vehicle.objects.get(id=vehicle_id)
    }
    return render(request, "asi-assets/vehicle_detail.html", context)   
