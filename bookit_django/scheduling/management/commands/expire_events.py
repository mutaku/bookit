from django.core.management.base import BaseCommand,\
    CommandError
from scheduling.models import Event
from datetime import datetime


class Command(BaseCommand):
    """Expire old events"""

    help = "Expires events that have already occurred"
    requires_system_checks = False

    def handle(self, *args, **options):
        events = Event.objects.filter(expired=False,
                                      end_time__lt=datetime.now())
        self.stdout.write(self.style.SUCCESS(
            "Found [{}] events.".format(str(len(events)))))
        for event in events:
            event.expired = True
            event.save()
        self.stdout.write(self.style.SUCCESS(
            'Expired [{}] events.'.format(len(events))))