from django.shortcuts import get_list_or_404, get_object_or_404
from .utils import jsonify_schedule, EventCalendar, alert_requested, \
	request_granted, is_admin
from django.http import HttpResponse
from django.contrib import messages
from django.views.generic.detail import DetailView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .models import Event, Equipment, Message, Information, Tag
import calendar
from datetime import datetime


# def handle_month(month):
#     """Handle some silly month assignment math"""
#     if month == 0:
#         return 12
#     return month
#
# def handle_year(month, year):
#     """Handle some silly year assignment math"""
#     if month == 12:
#         return year + 1
#     elif month == 1:
#         return year - 1
#     return year


class EquipmentDetailView(LoginRequiredMixin, DetailView):
	"""Detailed view of an instrument"""

	model = Equipment
	template_name = 'scheduling/equipment_detail.html'


@login_required
def request_equipment_perms(request, pk):
	"""Request to be added to instrument for booking"""
	equipment = get_object_or_404(Equipment, id=pk)

	alert_requested(equipment, request.user)
	result_string = 'Requested use of {0.name}. You will be notified by email.' \
		.format(equipment)
	result_status = messages.SUCCESS

	messages.add_message(request, result_status,
						 result_string)
	return redirect('scheduling.views.main_view')


@login_required
def activate_equipment_perms(request, equip_pk, user_pk):
	"""Trigger user instrument permissions granted"""
	equipment = get_object_or_404(Equipment, id=equip_pk)
	user = get_object_or_404(User, id=user_pk)

	if is_admin(request.user):
		equipment.users.add(user)
		equipment.save()
		request_granted(equipment, user)
		msg = 'User {0.username} added to {1.name}'.format(user,
														   equipment)
		messages.add_message(request, messages.SUCCESS,
							 msg)
	else:
		messages.add_message(request, messages.ERROR, 'Failed to add user.')
	return redirect('scheduling.views.main_view')


@login_required
def month_view(request, equipment):
	"""Main calendar view"""
	year = request.GET.get('year', None)
	month = request.GET.get('month', None)
	if not all([year, month]):
		year, month = datetime.now().year, datetime.now().month
	else:
		year, month = [int(x) for x in [year, month]]
	calendar_data = {
		'current':
			{'year': year,
			 'month': month,
			 'month_name': calendar.month_name[month]},
		'last':
			{'year': year,
			 'month': (month - 1) % 12,
			 'month_name': calendar.month_name[(month - 1) % 12]},
		'next':
			{'year': year,
			 'month': (month + 1) % 12,
			 'month_name': calendar.month_name[(month + 1) % 12]},
		'actual':
			{'year': datetime.now().year,
			 'month': datetime.now().month,
			 'month_name': calendar.month_name[datetime.now().month]}}

	# This next part is ugly.
	if month == 12:
		calendar_data['next']['year'] += 1
	elif month == 1:
		calendar_data['last']['year'] -= 1
		calendar_data['last']['month'] = 12
		calendar_data['last']['month_name'] = calendar.month_name[12]
	elif month == 11:
		calendar_data['next']['month'] = 12
		calendar_data['next']['month_name'] = calendar.month_name[12]

	events = Event.objects.filter(
		start_time__year=year,
		start_time__month=month,
		equipment__name=equipment)
	equipment_result = Equipment.objects.get(name=equipment)
	month_calendar = EventCalendar(events).formatmonth(
		year,
		month,
		equipment_result).replace('\n', '')
	nav_data = {'equipment': equipment}
	context = {'navigation_data': nav_data,
			   'month_calendar': month_calendar,
			   'calendar_data': calendar_data,
			   'equipment_list': Equipment.objects.all()}
	return render(request, 'scheduling/calendar.html', context)


@login_required
def message_board(request):
	"""Message board view"""
	tag_filter = request.GET.get('tag', None)
	equipment_filter = request.GET.get('equipment', None)
	nav_data = dict()
	if tag_filter:
		tag = get_object_or_404(Tag, tag=tag_filter)
		message_objs = Message.objects.filter(tags__id=tag.id)
		nav_data['tag'] = tag_filter
	else:
		message_objs = Message.objects.all()
	# Maybe not the best filtering setup, let's redesign this
	if equipment_filter:
		message_objs = message_objs.filter(equipment__name=equipment_filter)
		nav_data['equipment'] = equipment_filter
	context = {'message_objs': message_objs.order_by('-created'),
			   'tags': Tag.objects.all().order_by('tag'),
			   'equipment_list': Equipment.objects.all().order_by('name'),
			   'nav_data': nav_data}
	return render(request, 'scheduling/comments.html', context)


@login_required
def main_view(request):
	"""Main landing view"""
	equipment_list = Equipment.objects.all()
	message_objs = Message.objects.all().order_by('-created')[:3]
	information_list = Information.objects.filter(main_page_visible=True)
	context = {'message_objs': message_objs,
			   'equipment_list': equipment_list,
			   'information_list': information_list}
	return render(request, 'scheduling/index.html', context)


def json_events(request, equipment):
	"""JSON event list -
	No login currently required so as to use as publicly
	available API (of sorts)"""
	if equipment is not None:
		event_list = get_list_or_404(Event, equipment__name=equipment)
		return HttpResponse(jsonify_schedule(event_list))
	return HttpResponse('Nothing here.')
