from calendar import HTMLCalendar

from django.urls import reverse

from reservations.models import Reservation


class Calendar(HTMLCalendar):
	def __init__(self, year=None, month=None):
		self.year = year
		self.month = month
		super(Calendar, self).__init__()

	def formatday(self, day, reservations):
		reservations_per_day = reservations.filter(start_time__day=day).order_by('start_time')
		d = ''
		for r in reservations_per_day:
			url = reverse('reservations:reservation_detail', args=(r.id,))
			label = f'{r.user.username} {r.start_time.strftime("%H:%M")}'
			d += f'<li><a href="{url}">{label}</a></li>'

		if day != 0:
			return f"<td><span class='date'>{day}</span><ul> {d} </ul></td>"
		return '<td></td>'

	def formatweek(self, theweek, reservations):
		week = ''
		for d, weekday in theweek:
			week += self.formatday(d, reservations)
		return f'<tr> {week} </tr>'

	def formatmonth(self, withyear=True):
		reservations = Reservation.objects.filter(
			start_time__year=self.year,
			start_time__month=self.month,
		).select_related('user')

		cal = f'<table border="0" cellpadding="0" cellspacing="0" class="calendar">\n'
		cal += f'{self.formatmonthname(self.year, self.month, withyear=withyear)}\n'
		cal += f'{self.formatweekheader()}\n'
		for week in self.monthdays2calendar(self.year, self.month):
			cal += f'{self.formatweek(week, reservations)}\n'
		return cal
