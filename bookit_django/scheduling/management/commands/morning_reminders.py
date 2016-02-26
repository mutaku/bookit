from django.core.management.base import BaseCommand,\
    CommandError
from scheduling.models import Event
from scheduling.utils import event_reminder_mail
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    '''Email reminder to users about upcoming events for today'''

    help = 'Sends reminder emails to users for events starting today'
    requires_system_checks = False

    def handle(self, *args, **options):
        events = Event.objects.filter(expired=False,
                                      status='A',
                                      start_time__day=datetime.now().day)
        self.stdout.write(self.style.SUCCESS(str(len(events))))
        for event in events:
            event_reminder_mail(event)
        self.stdout.write(self.style.SUCCESS(
            'Emails sent [{}].'.format(len(events))))