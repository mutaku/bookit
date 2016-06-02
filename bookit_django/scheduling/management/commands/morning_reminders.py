from django.core.management.base import BaseCommand
from scheduling.models import Event
from scheduling.utils import event_reminder_mail
from datetime import datetime


class Command(BaseCommand):
	"""Email reminder to users about upcoming events for next day.
	Allows time for 'day before' preparations.
	"""

	help = "Sends reminder emails to users for events starting next day"
	requires_system_checks = False

	def handle(self, *args, **options):
		events = Event.objects.filter(expired=False,
									  status__in=['A', 'H'],
									  equipment__status=True,
									  start_time__day=datetime.now().day + 1)
		self.stdout.write(self.style.SUCCESS(
			"{} Reminders: Found [{}] events.".format(
				datetime.now().strftime('%a %d-%b-%y %H-%M-%S'),
				str(len(events)))))
		for event in events:
			event_reminder_mail(event)
		self.stdout.write(self.style.SUCCESS(
			'{} Reminders: Emails [{}] sent.'.format(
				datetime.now().strftime('%a %d-%b-%y %H-%M-%S'),
				len(events))))
