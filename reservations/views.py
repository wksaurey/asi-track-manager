from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ReservationForm
from .models import Reservation


@login_required
def reservation_list(request):
    reservations = Reservation.objects.filter(user=request.user).order_by('start_time')
    return render(request, 'reservations/reservation_list.html', {'reservations': reservations})


@login_required
def reservation_create(request):
    if request.method == 'POST':
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.user = request.user
            reservation.save()
            form.save_m2m()
            return redirect('reservations:reservation_list')
    else:
        form = ReservationForm()
    return render(request, 'reservations/reservation_form.html', {'form': form})


@login_required
def reservation_detail(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id)
    return render(request, 'reservations/reservation_detail.html', {'reservation': reservation})


@login_required
def reservation_delete(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id, user=request.user)
    if request.method == 'POST':
        reservation.delete()
        return redirect('reservations:reservation_list')
    return render(request, 'reservations/reservation_confirm_delete.html', {'reservation': reservation})
