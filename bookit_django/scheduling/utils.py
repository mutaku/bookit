import json
import calendar
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils.html import conditional_escape as esc
from datetime import date, datetime
from itertools import groupby
from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.sites.models import Site
from django.template.loader import render_to_string

# Maybe move these to settings
EMAIL_FROM = settings.DEFAULT_FROM_EMAIL


def day_past(year, month, day):
	"""Determine if date is in the past"""
	return date(year, month, day) < date.today()


def check_add_link_status(equipment_status, year, month, day):
	"""Check whether we should provide an add link"""
	if equipment_status is False:
		return False
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
					elif event.status == 'H':
						event_url = event.get_absolute_url()
						body.append('<li class="hold-event">')
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
				if check_add_link_status(self.equipment_status,
										 self.year, self.month, day):
					body.append(self.day_link(date_string))
				content = '{} {}'.format(day, ''.join(body))
			elif check_add_link_status(self.equipment_status,
									   self.year, self.month, day):
				content = '{} {}'.format(day, self.day_link(date_string))
			else:
				content = day
			return self.day_cell(cssclass, content)
		return self.day_cell('noday', '&nbsp;')

	def formatmonthname(self, theyear, themonth, withyear=True):
		""" Return a month name as a table row"""
		equipment_string = self.equipment_name +\
			(" <span class=warning>OFFLINE<span>" if not self.equipment_status else '')
		date_string = ' '.join([str(calendar.month_name[themonth]),
								str(theyear) if withyear else ''])
		return '<tr><th colspan="7" class="month">{}</th></tr>'.format(
			' - '.join([date_string, equipment_string]))

	def formatmonth(self, year, month, equipment):
		"""Utilize supplied year and month"""
		self.year, self.month, self.equipment,\
		self.equipment_name, self.equipment_status = year, \
													 month, \
													 equipment.id, \
													 equipment.name, \
													 equipment.status
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
	return list(User.objects.filter(is_superuser=True). \
				values_list('email', flat=True))


def get_admin_emails():
	"""Generate a list of all equipment admins - entire pool,
	not just actively assigned ones
	"""
	return list(set(list(User.objects.filter(groups__name="equipment_admin"). \
						 values_list('email', flat=True)) + get_superuser_emails()))


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
	context = {'event': obj,
			   'admin': obj.equipment.admin.get_full_name()}
	EmailMessage('The {0.equipment.name} has been scheduled for maintenance'.format(obj),
				 render_to_string('scheduling/maintenance_announcement.txt', context),
				 EMAIL_FROM,
				 [],
				 get_all_user_emails(obj.equipment)).send()


def maintenance_cancellation(obj):
	"""Email user regarding an event cancellation for maint"""
	context = {'event': obj,
			   'admin': obj.equipment.admin.get_full_name()}
	send_mail('{0.start_time} on {0.equipment.name} cancelled - emergency maintenance'.format(obj),
			  render_to_string('scheduling/maintenance_cancellation.txt', context),
			  EMAIL_FROM,
			  [obj.user.email],
			  fail_silently=False)


def ticket_mail(obj):
	"""Email superusers to inform of a new ticket or comment"""
	context = {'user': obj.user.get_full_name(),
			   'ticket': obj}
	EmailMessage('{0.equipment.name} has a new ticket'.format(obj),
				 render_to_string('scheduling/ticket_mail.txt', context),
				 EMAIL_FROM,
				 [],
				 get_admin_emails()).send()


def ticket_status_toggle_mail(obj):
	"""Email specific user regarding their updated ticket status"""
	context = {'ticket': obj}
	send_mail('{0.created} re:{0.equipment.name} - ticket updated'.format(obj),
			  render_to_string('scheduling/ticket_status_toggle_mail.txt', context),
			  EMAIL_FROM,
			  [obj.user.email],
			  fail_silently=False)


def message_mail(obj):
	"""Email all users about new message"""
	context = {'user': obj.user.get_full_name(),
			   'message': obj}
	EmailMessage('New Bookit message from {0}'.format(context['user']),
				 render_to_string('scheduling/message_mail.txt', context),
				 EMAIL_FROM,
				 [],
				 get_all_user_emails() if not obj.equipment
				 	else get_all_user_emails(obj.equipment)).send()


def changed_event_mail(obj):
	"""Email all users of an edited event"""
	context = {'user': obj.user.get_full_name(),
	 			'event': obj,
	 			'url': 'http://{0}{1}'.format(
		 			Site.objects.get(id=1).domain,
		 			reverse('month_view', args=(obj.equipment.name,)))}
	EmailMessage('{0.equipment.name} - {0.orig_start} has changed'.format(obj),
				 render_to_string('scheduling/changed_event_mail.txt', context),
				 EMAIL_FROM,
				 [],
				 get_all_user_emails(obj.equipment)).send()


def deleted_event_mail(obj):
	"""Email all users of a deleted event"""
	context = {'user': obj.user.get_full_name(),
			   'event': obj,
			   'url': 'http://{0}{1}'.format(
				   Site.objects.get(id=1).domain,
				   reverse('month_view', args=(obj.equipment.name,)))}
	EmailMessage('{0.equipment.name} - {0.orig_start} is now open'.format(obj),
				 render_to_string('scheduling/deleted_event_mail.txt', context),
				 EMAIL_FROM,
				 [],
				 get_all_user_emails(obj.equipment)).send()


def new_event_mail(obj):
	"""Email user of their newly scheduled event"""
	context = {'event': obj}
	send_mail('You booked the {0.equipment.name} for {0.start_time}'.format(obj),
			  render_to_string('scheduling/new_event_email.txt', context),
			  EMAIL_FROM,
			  [obj.user.email],
			  fail_silently=False)


def event_reminder_mail(obj):
	"""Email user to remind them of their event today"""
	context = {'event': obj,
			   'event_details': obj.hover_text.replace('&#10;', '\n\t')}
	send_mail('Bookit reminder: {0.equipment.name} at {0.start_time}'.format(obj),
		render_to_string('scheduling/event_reminder_email.txt', context),
			  EMAIL_FROM,
			  [obj.user.email],
			  fail_silently=False)


def alert_requested(equipment, user):
	"""Email equipment admin about new user request"""
	context = {'user': user.get_full_name(),
			   'equipment': equipment,
			   'url': 'http://{0}{1}'.format(
				   Site.objects.get(id=1).domain,
				   reverse('activate-equipment-perms',
						   args=(equipment.id, user.id,)))}
	send_mail('{0} has requested access to the {1}'.format(
					user.get_full_name(),
					equipment.name),
			  render_to_string('scheduling/alert_requested.txt', context),
			  EMAIL_FROM,
			  [user.email],
			  fail_silently=False)


def request_granted(equipment, user):
	"""Email user that their instrument perms request has been granted"""
	context = {'equipment': equipment,
			   'equipment_url': 'http://{0}{1}'.format(
				   Site.objects.get(id=1).domain,
				   reverse('month_view', args=(equipment.name,))),
				'admin': equipment.admin.get_full_name(),
				'ticket_url': 'http://{0}{1}?equipment={2}'.format(
					Site.objects.get(id=1).domain,
					reverse('admin:scheduling_ticket_add'),
					equipment.id)}
	send_mail('{0} usage permission request granted'.format(equipment.name),
			  render_to_string('scheduling/request_granted.txt', context),
			  EMAIL_FROM,
			  [user.email],
			  fail_silently=False)


def equipment_online_email(equipment):
	"""Email users and admins that an instrument is back online"""
	context = {'equipment': equipment,
			   'url': 'http://{0}{1}'.format(
				   Site.objects.get(id=1).domain,
				   reverse('month_view', args=(equipment.name,)))}
	EmailMessage("{0.name} is back online.".format(equipment),
				 render_to_string('scheduling/equipment_online_email.txt',
								  context),
				 EMAIL_FROM,
				 [],
				 list(set(get_all_user_emails(equipment) + get_admin_emails()))).send()


def equipment_offline_email(equipment):
	"""Email users adn admins that an instrument has gone offline"""
	context = {'equipment': equipment,
			   'admin': equipment.admin.get_full_name()}
	EmailMessage("{0.name} is now OFFLINE.".format(equipment),
				 render_to_string('scheduling/equipment_offline_email.txt',
								  context),
				 EMAIL_FROM,
				 [],
				 list(set(get_all_user_emails(equipment) + get_admin_emails()))).send()
