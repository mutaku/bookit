from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta, datetime
from time import mktime
from django.core.urlresolvers import reverse
from utils import maintenance_cancellation


STATUS = (
    ("C", "Canceled"),
    ("A", "Active"))

YESNO = (
    ("Y", "Yes"),
    ("N", "No"))


def get_model_fields(obj):
    '''Generate field names and values for templates'''
    return [(field.name, field.value_to_string(obj))
            for field in obj.__class__._meta.fields]


def find_next_booking(obj):
    '''Identify next booked slot for instrument'''
    return Event.objects.\
        filter(equipment=obj,
               status='A',
               expired=False,
               start_time__gte=datetime.now()).\
        order_by('start_time')[0]


class Brand(models.Model):
    '''Component/Equipment Brand'''
    name = models.CharField("Name",
                            max_length=50,
                            null=False,
                            blank=False)

    def __unicode__(self):
        '''Unicode return'''
        return self.name


class Model(models.Model):
    '''Component/Equipment Model'''
    name = models.CharField("Name",
                            max_length=50,
                            null=False,
                            blank=False)

    def __unicode__(self):
        '''Unicode return'''
        return self.name


class Equipment(models.Model):
    '''Available Equipment for Scheduling'''
    name = models.CharField("Equipment",
                            max_length=40)
    description = models.TextField("Description",
                                   blank=True,
                                   null=True)
    brand = models.ForeignKey(Brand,
                              related_name="equipment")
    model = models.ForeignKey(Model,
                              related_name="equipment")
    component = models.ManyToManyField("Component",
                                       related_name="equipment",
                                       blank=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True)
    status = models.BooleanField("Running",
                                 default=True)

    # @property
    # def last_service(self):
    #     '''Identify last service date'''
    #     return Service.objects.filter(equipment=self).order_by('-date')[0]

    @property
    def next_booking(self):
        '''Rip down next booking for this instrument'''
        return find_next_booking(self)

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


    def __unicode__(self):
        '''Unicode return'''
        return self.name

    class Meta:
        '''Overide some defaults'''
        verbose_name_plural = "equipment"


class Component(models.Model):
    '''Equipment components'''
    name = models.CharField("Name",
                            max_length=50,
                            null=False,
                            blank=False)
    created = models.DateTimeField("Created",
                                   editable=False,
                                   auto_now_add=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True,
                                    editable=False)
    brand = models.ForeignKey(Brand,
                              related_name="components")
    model = models.ForeignKey(Model,
                              related_name="components")
    description = models.TextField("Description",
                                   null=True,
                                   blank=True)
    notes = models.TextField("Notes",
                             null=True,
                             blank=True)

    def __unicode__(self):
        '''Unicode return'''
        return self.name

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


class Service(models.Model):
    '''Service record for equipment/components'''
    date = models.DateTimeField("Date",
                                auto_now_add=True)
    user = models.ForeignKey(User,
                             related_name='services')
    equipment = models.ForeignKey(Equipment,
                                  related_name='services')
    component = models.ForeignKey(Component,
                                  related_name='services',
                                  null=True,
                                  blank=True)
    job = models.TextField("Job")
    success = models.BooleanField("Success",
                                  default=True)
    notes = models.TextField("Notes",
                             blank=True,
                             null=True)

    def __unicode__(self):
        '''Unicode return'''
        return '{} - {}'.format(self.date, self.job)

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


class Message(models.Model):
    '''Message board Message'''
    msg = models.TextField("Message",
                           null=False,
                           blank=False)
    user = models.ForeignKey(User,
                             editable=False,
                             related_name='messages')
    created = models.DateTimeField("Created",
                                   editable=False,
                                   auto_now_add=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True,
                                    editable=False)
    critical = models.BooleanField("Critical",
                                   default=False)

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


class Ticket(models.Model):
    '''Maintenance Request Tickets'''
    msg = models.TextField("Ticket",
                           null=False,
                           blank=False)
    equipment = models.ForeignKey(Equipment)
    priority = models.BooleanField('High priority',
                                   default=False)
    user = models.ForeignKey(User,
                             editable=False,
                             related_name='tickets')
    created = models.DateTimeField("Created",
                                   editable=False,
                                   auto_now_add=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True,
                                    editable=False)
    comment = models.ManyToManyField("Comment",
                                     related_name="comments",
                                     blank=True)
    status = models.BooleanField("Closed",
                                 default=False)


    @property
    def comment_count(self):
        '''Quantify comment load'''
        return self.comment.all().count()

    @property
    def admin_url(self):
        '''Generate an admin URL for this ticket'''
        return '/admin/scheduling/ticket/{0}/change/'.format(self.id)

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


class Comment(models.Model):
    '''Comments for Maintenance Request Tickets'''
    msg = models.TextField("Comment",
                           null=False,
                           blank=False)
    user = models.ForeignKey(User,
                             editable=False,
                             related_name='comments')
    created = models.DateTimeField("Created",
                                   editable=False,
                                   auto_now_add=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True,
                                    editable=False)

    def __unicode__(self):
        '''Unicode return'''
        return '{} - {}'.format(self.user.username,
                                self.msg[:100])

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)


class Event(models.Model):
    '''Equipment Scheduling Event'''

    def __init__(self, *args, **kwargs):
        '''Add in initialization routines'''
        super(Event, self).__init__(*args, **kwargs)
        setattr(self, 'orig_start', getattr(self, 'start_time', None))
        setattr(self, 'orig_end', getattr(self, 'end_time', None))

    user = models.ForeignKey(User,
                             editable=False,
                             related_name='events')
    start_time = models.DateTimeField("Start time",
                                      blank=False,
                                      null=False)
    end_time = models.DateTimeField("End time",
                                    blank=False,
                                    null=False)
    elapsed_hours = models.FloatField("Elapsed time (h)",
                                      blank=True,
                                      null=True)
    equipment = models.ForeignKey(Equipment)
    status = models.CharField(choices=STATUS,
                              max_length=1,
                              default="A")
    notes = models.TextField("Notes",
                             blank=True,
                             null=True)
    disassemble = models.BooleanField("Can disassemble",
                                      default=True)
    maintenance = models.BooleanField("Maintenance Mode",
                                      default=False)
    expired = models.BooleanField("Expired",
                                  default=False)

    def upcoming(self):
        '''Event is still in the future'''
        if not self.expired and self.status == 'A':
            return True
        return False
    upcoming.boolean = True

    @property
    def start_timestring_time(self):
        '''Start time only to string'''
        return self.start_time.time().strftime("%H:%M")

    @property
    def end_timestring_time(self):
        '''End time only to string'''
        return self.end_time.time().strftime("%H:%M")

    @property
    def start_timestring(self):
        '''Start time to string'''
        return str(self.start_time)

    @property
    def end_timestring(self):
        '''End time to string'''
        return str(self.end_time)

    @property
    def admin_url(self):
        '''Generate an admin URL for this event'''
        return '/admin/scheduling/event/{0}/change/'.format(self.id)

    @property
    def start_timestamp(self):
        '''Generate start timestamp in ms'''
        return '{0}'.format(int(mktime(self.start_time.timetuple()))*1000)

    @property
    def end_timestamp(self):
        '''Generate end timestamp in ms'''
        return '{0}'.format(int(mktime(self.end_time.timetuple()))*1000)

    def get_absolute_url(self):
        '''Generate the absolute URL for this object'''
        # Using the admin change form for this
        return reverse('admin:scheduling_event_change', args=(self.id,))

    def clean(self, *args, **kwargs):
        '''Add some custom validation'''
        super(Event, self).clean(*args, **kwargs)
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be later than start.')
        if not self.id and self.start_time < timezone.now():
            raise ValidationError('Cannot retroactively schedule an event.')
        if (self.id and
                self.end_time < timezone.now() and
                not self.user.is_superuser):
            raise ValidationError('Cannot edit an event that has expired.')

        selected_day = self.start_time.date()
        future_events = self.__class__._default_manager.filter(
            start_time__range=[selected_day-timedelta(1),
                               selected_day+timedelta(1)],
            status='A',
            expired=False,
            equipment=self.equipment).exclude(id=self.id)
        overlaps = list()
        for event in future_events:
            if ((self.end_time >= event.end_time and
                 self.start_time <= event.end_time) or
                    (self.end_time >= event.start_time and
                     self.start_time <= event.start_time) or
                    (self.start_time >= event.start_time and
                     self.end_time <= event.end_time)):
                overlaps.append(event)
        if len(overlaps) and self.maintenance is False:
            raise ValidationError('Overlaps with existing booking.')
        elif len(overlaps) and self.maintenance is True:
            for obj in overlaps:
                obj.status = 'C'
                obj.save()
                # UNCOMMENT THE FOLLOWING WHEN READY FOR EMAIL!
                # maintenance_cancellation(obj)

    def save(self, *args, **kwargs):
        '''Tweak save routine to run stuff'''
        super(Event, self).save(*args, **kwargs)

    @property
    def current_status(self):
        '''Stringify display name of current status'''
        return self.get_status_display()

    @property
    def hover_text(self):
        '''Generate descriptive text for html viewing'''
        attrs = ['Start: {0.start_timestring_time}',
                 'End: {0.end_timestring_time}',
                 'User: {0.user.username}',
                 'Status: {0.current_status}',
                 'Equipment: {0.equipment.name}',
                 'Disassemble: {0.disassemble}']
        return ' &#10; '.join(attrs).format(self)

    def get_fields(self):
        '''Generate field names and values for templates'''
        return get_model_fields(self)

    class Meta:
        '''Overide some things'''
        ordering = ["-start_time"]
