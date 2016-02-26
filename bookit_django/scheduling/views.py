from django.shortcuts import render,\
    get_object_or_404, get_list_or_404
from .utils import jsonify_schedule, EventCalendar
from django.http import HttpResponse
from django.views.generic.detail import DetailView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from .models import Event, Equipment, Message
import calendar
from datetime import datetime

# Create your views here.


# def handle_month(month):
#     '''Handle some silly month assignment math'''
#     if month == 0:
#         return 12
#     return month
# 
# def handle_year(month, year):
#     '''Handle some silly year assignment math'''
#     if month == 12:
#         return year + 1
#     elif month == 1:
#         return year - 1
#     return year


class EquipmentDetailView(LoginRequiredMixin, DetailView):
    '''Detailed view of an instrument'''

    model = Equipment
    template_name = 'scheduling/equipment_detail.html'


@login_required
def month_view(request, equipment):
    '''Main calendar view'''
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
    equipment_id = Equipment.objects.get(name=equipment).id
    month_calendar = EventCalendar(events).formatmonth(
        year,
        month,
        equipment_id).replace('\n', '')
    nav_data = {'equipment': equipment}
    context = {'navigation_data': nav_data,
               'month_calendar': month_calendar,
               'calendar_data': calendar_data,
               'equipment_list': Equipment.objects.all()}
    return render(request, 'scheduling/calendar.html', context)


@login_required
def message_board(request):
    '''Message board view'''
    message_objs = Message.objects.all().order_by('-created')
    context = {'message_objs': message_objs}
    return render(request, 'scheduling/comments.html', context)


@login_required
def main_view(request):
    '''Main landing view'''
    equipment_list = Equipment.objects.all()
    message_objs = Message.objects.all().order_by('-created')[:3]
    context = {'message_objs': message_objs,
               'equipment_list': equipment_list}
    return render(request, 'scheduling/index.html', context)


def json_events(request, equipment):
    '''JSON event list -
    No login currently required so as to use as pubically
    available API (of sorts)'''
    if equipment is not None:
        event_list = get_list_or_404(Event, equipment__name=equipment)
        return HttpResponse(jsonify_schedule(event_list))
    return HttpResponse('Nothing here.')
