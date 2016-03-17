import json
import calendar
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils.html import conditional_escape as esc
from datetime import date, datetime
from itertools import groupby
from django.conf import settings

# Maybe move these to settings
EMAIL_FROM = settings.DEFAULT_FROM_EMAIL


def day_past(year, month, day):
    """Determine if date is in the past"""
    return date(year, month, day) < date.today()


def check_add_link_status(year, month, day):
    """Check whether we should provide an add link"""
    return not day_past(year, month, day)


def add_link_constructor(obj, date_string):
    """Generate an add link for given day"""
    return "{}?start_time={}&end_time={}&equipment={}".format(
        reverse('admin:scheduling_event_add'),
        date_string, date_string, obj.equipment)


def date_string_constructor(year, month, day):
    """Generate a date string"""
    return str(date(year, month, day))


class EventCalendar(calendar.HTMLCalendar):
    """Override HTMLCalendar to populate model data"""
    # Modified from
    # http://uggedal.com/journal/creating-a-flexible-monthly-calendar-in-django/

    def __init__(self, events):
        super(EventCalendar, self).__init__()
        self.events = self.group_by_day(events)

    def formatday(self, day, weekday):
        """Adjust format day to include event data"""
        if day != 0:
            date_string = date_string_constructor(self.year, self.month, day)
            cssclass = self.cssclasses[weekday]
            if date(self.year, self.month, day) == date.today():
                cssclass += ' today'
            if day in self.events:
                cssclass += ' filled'
                body = ['<ul>']
                for event in self.events[day]:
                    if ((day_past(self.year, self.month, day) and
                                 event.end_time < datetime.now()) or
                            event.expired or event.status == 'C'):
                        event_url = '#'
                        body.append('<li class="expired-event">')
                    elif event.maintenance:
                        event_url = event.get_absolute_url()
                        body.append('<li class="maintenance-event">')
                    else:
                        event_url = event.get_absolute_url()
                        body.append('<li class="active-event">')
                    body.append('<a href="{}" title="{}">'.format(
                        event_url,
                        event.hover_text))
                    body.append(
                        esc('{} - {}'.format(event.start_timestring_time,
                                             event.end_timestring_time)))
                    body.append('</a></li>')
                body.append('</ul>')
                if check_add_link_status(self.year, self.month, day):
                    body.append(self.day_link(date_string))
                content = '{} {}'.format(day, ''.join(body))
            elif check_add_link_status(self.year, self.month, day):
                content = '{} {}'.format(day, self.day_link(date_string))
            else:
                content = day
            return self.day_cell(cssclass, content)
        return self.day_cell('noday', '&nbsp;')

    def formatmonthname(self, theyear, themonth, withyear=True):
        """ Return a month name as a table row"""
        if withyear:
            date_string = '{} {}'.format(calendar.month_name[themonth],
                                         theyear)
        else:
            date_string = '{}'.format(calendar.month_name[themonth])
        return '<tr><th colspan="7" class="month">{}</th></tr>'.format(
                            ' - '.join([date_string, self.equipment_name]))

    def formatmonth(self, year, month, equipment, equipment_name):
        """Utilize supplied year and month"""
        self.year, self.month, self.equipment, self.equipment_name = year, \
                                                                     month, \
                                                                     equipment, \
                                                                     equipment_name
        return super(EventCalendar, self).formatmonth(year, month)

    def group_by_day(self, events):
        """Group events by day"""
        return dict(
            [(day, list(items))
             for day, items in groupby(events,
                                       lambda event: event.start_time.day)])

    def day_link(self, date_string):
        """Craft a link to the admin for this particular day"""
        return '<a class="ajax neweventadd" href="{}">(+) Add</a>'.format(
            add_link_constructor(self, date_string))

    def day_cell(self, cssclass, body):
        """Override cell write for our populated data"""
        return '<td class="{}">{}</td>'.format(cssclass, body)


def get_all_user_emails(equipment=None):
    """Generate a list of all user email addresses"""
    if equipment:
        users = equipment.users.all()
    else:
        users = User.objects
    return list(users.values_list('email', flat=True))


def get_superuser_emails():
    """Generate a list of all superuser email addresses"""
    return list(User.objects.filter(is_superuser=True).\
        values_list('email', flat=True))


def jsonify_schedule(qset):
    """Convert queryset to json string"""
    json_set = list()
    for event in qset:
        field = {
            "id": event.pk,
            "title": event.user.username,
            "url": event.get_absolute_full_url,
            "status": event.status,
            "expired": event.expired,
            "start": event.start_timestamp,
            "end": event.end_timestamp
        }
        json_set.append(field)
    json_set_master = {"success": 1}
    json_set_master["result"] = json_set
    return json.dumps(json_set_master)


def maintenance_announcement(obj):
    """Email all users about maintenance"""
    msg = """{0.equipment.name} has been scheduled for
    emergency maintenance from {0.start_time} to {0.end_time}.
    If this has affected your scheduled booking, you will receive
    a separate email notifying you of this change.""".format(obj)
    subj = """{0.equipment.name} has been scheduled for
    emergency maintenance""".format(obj).replace('\n', '')
    recips = get_all_user_emails(obj.equipment)
    send_mail(subj, msg, EMAIL_FROM, recips, fail_silently=False)


def maintenance_cancellation(obj):
    """Email user regarding an event cancellation for maint"""
    msg = """Your event on {0.start_time} using {0.equipment.name}
    has been cancelled due to an emergency maintenance procedure.
    Please contact the admin for further information.""".format(obj)
    subj = '{0.start_time} emergency maintenance cancellation'.format(obj)
    send_mail(subj, msg, EMAIL_FROM, [obj.user.email], fail_silently=False)


def ticket_email(obj):
    """Email superusers to inform of a new ticket or comment"""
    msg = """{0.user.username} has created/edited
    a new ticket {0.id} for {0.equipment.name} with high priority: {0.priority}
    - {0.get_absolute_full_url}""".format(obj)
    subj = '{0.equipment.name} has a new ticket'.format(obj)
    recips = get_superuser_emails()
    recips.append(obj.equipment.admin.email)
    send_mail(subj, msg, EMAIL_FROM, recips, fail_silently=False)


def ticket_status_toggle_email(obj):
    """Email specific user regarding their updated ticket status"""
    msg = """Your ticket created on {0.created} has changed
    status to closed={0.status}""".format(obj)
    subj = '{0.created} ticket updated'.format(obj)
    send_mail(subj, msg, EMAIL_FROM, [obj.user.email], fail_silently=False)


def message_email(obj):
    """Email all users about new message"""
    msg = """{0.user.username} has created a new message
    on {0.created}: {0.msg}
    {0.get_absolute_full_url}""".format(obj)
    subj = 'New Bookit message from {0.user.username}'.format(obj)
    recips = get_all_user_emails()
    send_mail(subj, msg, EMAIL_FROM, recips, fail_silently=False)


def changed_event_mail(obj):
    """Email all users of an edited event"""
    if obj.orig_start == obj.start_time and obj.status == 'C':
        msg = """{0.user.username} has edited an event.
    {0.orig_start} {0.equipment.name} is now CANCELLED."""
    else:
        msg = """{0.user.username} has edited an event.
    {0.orig_start} - {0.orig_end} on {0.equipment.name} is now
    {0.start_timestring} - {0.end_timestring}."""
    msg = msg.format(obj)
    subj = '{0.equipment.name} - {0.orig_start} has changed'.format(obj)
    recips = get_all_user_emails(obj.equipment)
    send_mail(subj, msg, EMAIL_FROM, recips, fail_silently=False)


def deleted_event_mail(obj):
    """Email all users of a deleted event"""
    msg = """{0.user.username} has deleted an event.
    {0.start_timestring} - {0.end_timestring} on {0.equipment.name}
    is now available for scheduling.""".format(obj)
    subj = '{0.equipment.name} - {0.orig_start} is now open'.format(obj)
    recips = get_all_user_emails(obj.equipment)
    send_mail(subj, msg, EMAIL_FROM, recips, fail_silently=False)


def new_event_mail(obj):
    """Email user of their newly scheduled event"""
    msg = """You have successfully booked {0.equipment.name}
    for {0.start_timestring} - {0.end_timestring}. {0.get_absolute_full_url}
    """.format(obj)
    # Maybe add the admin URL to this email for convenience
    subj = 'You booked {0.equipment.name} starting {0.start_timestring}'.\
           format(obj)
    send_mail(subj, msg, EMAIL_FROM, [obj.user.email], fail_silently=False)


def event_reminder_mail(obj):
    """Email user to remind them of their event today"""
    msg = """This is a reminder email from Bookit that you are booked on
    the {0.equipment.name} today at {0.start_timestring}.
    {0.get_absolute_full_url}""".format(obj)
    subj = 'Bookit reminder: {0.equipment.name} at {0.start_timestring}'.\
           format(obj)
    send_mail(subj, msg, EMAIL_FROM, [obj.user.email], fail_silently=False)
