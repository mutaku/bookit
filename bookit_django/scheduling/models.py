from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime
from time import mktime
from django.contrib.auth.forms import PasswordResetForm
from django.core.urlresolvers import reverse
from utils import maintenance_cancellation


STATUS = (
    ("C", "Canceled"),
    ("A", "Active"),
    ("H", "Hold"))

YESNO = (
    ("Y", "Yes"),
    ("N", "No"))


def get_model_fields(obj):
    """Generate field names and values for templates"""
    return [(field.name, field.value_to_string(obj))
            for field in obj.__class__._meta.fields]


def find_next_booking(obj):
    """Identify next booked slot for instrument"""
    return Event.objects.\
        filter(equipment=obj,
               status__in=['A', 'H'],
               expired=False,
               start_time__gte=datetime.now()).\
        order_by('start_time')[0]


def find_last_service(obj):
    """Identify last service event for instrument"""
    return Service.objects.filter(equipment=obj).order_by('-date').first()


class Information(models.Model):
    """Informational bits for page display"""
    user = models.ForeignKey(User,
                             related_name="information_editor",
                             limit_choices_to={
                                'groups__name': 'equipment_admin'})
    header = models.CharField("Header",
                              max_length=100)
    body = models.TextField("Body")
    created = models.DateTimeField("Created",
                                   auto_now_add=True)
    modified = models.DateTimeField("Modified",
                                    auto_now=True)
    main_page_visible = models.BooleanField("Main Page Display",
                                            default=False)

    def get_body(self):
        """Return shortened body display"""
        return "{body}{ending}".format(body=self.body[:50],
                                       ending="..." if len(self.body) > 50 else "")

    def __unicode__(self):
        """Unicode return"""
        return self.header

    class Meta:
        """Override some defaults"""
        verbose_name_plural = "information"


class Brand(models.Model):
    """Component/Equipment Brand"""
    name = models.CharField("Name",
                            max_length=50,
                            null=False,
                            blank=False)

    def __unicode__(self):
        """Unicode return"""
        return self.name


class Model(models.Model):
    """Component/Equipment Model"""
    name = models.CharField("Name",
                            max_length=50,
                            null=False,
                            blank=False)

    def __unicode__(self):
        """Unicode return"""
        return self.name


class Equipment(models.Model):
    """Available Equipment for Scheduling"""
    name = models.CharField("Equipment",
                            max_length=40)
    admin = models.ForeignKey(User,
                              related_name="equipment_admin",
                              limit_choices_to={
                                'groups__name': 'equipment_admin'})
    users = models.ManyToManyField(User,
                                   related_name="equipment_user",
                                   limit_choices_to={
                                    'groups__name': 'equipment_user'})
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

    @property
    def last_service(self):
        """Identify last service date"""
        return find_last_service(self)

    @property
    def user_names_list(self):
        """List of allowed users"""
        return [str(user.username) for user in self.users.all()]

    @property
    def next_booking(self):
        """Rip down next booking for this instrument"""
        return find_next_booking(self)

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)

    @property
    def get_admin_url(self):
        """Generate admin URL"""
        return '/admin/scheduling/equipment/{}/change/'.format(self.id)

    @property
    def get_absolute_full_url(self):
        """Compile a full, absolute URL"""
        domain = Site.objects.get_current().domain.rstrip('/')
        return 'http://{}{}'.format(domain, self.get_admin_url)

    def __unicode__(self):
        """Unicode return"""
        return self.name

    class Meta:
        """Override some defaults"""
        verbose_name_plural = "equipment"


class Component(models.Model):
    """Equipment components"""
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
        """Unicode return"""
        return self.name

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)


class Message(models.Model):
    """Message board Message"""
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

    tags = models.ManyToManyField("Tag",
                                  blank=True,
                                  null=True)

    equipment = models.ForeignKey("Equipment",
                                  blank=True,
                                  null=True,
                                  help_text="If selected, will only email associated users")

    @property
    def get_admin_url(self):
        """Generate admin URL"""
        return '/scheduling/messages/#msg-{}'.format(self.id)

    @property
    def get_absolute_full_url(self):
        """Compile a full, absolute URL"""
        domain = Site.objects.get_current().domain.rstrip('/')
        return 'http://{}{}'.format(domain, self.get_admin_url)

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)

    def get_tags(self):
        """Pipe out tag list for admin changelist"""
        tags = [obj.tag for obj in self.tags.all()]
        return " | ".join(tags)
    get_tags.short_description = "Tags"


class Tag(models.Model):
    """Tags to associate posts with"""
    tag = models.CharField("Tag",
                           max_length=50,
                           unique=True)

    class Meta:
        """Override some things"""
        ordering = ["-id"]

    def __unicode__(self):
        """Unicode return"""
        return self.tag


class Ticket(models.Model):
    """Maintenance Request Tickets"""
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
        """Quantify comment load"""
        return self.comment.all().count()

    @property
    def get_admin_url(self):
        """Generate admin URL"""
        return '/admin/scheduling/ticket/{}/change/'.format(self.id)

    @property
    def get_absolute_full_url(self):
        """Compile a full, absolute URL"""
        domain = Site.objects.get_current().domain.rstrip('/')
        return 'http://{}{}'.format(domain, self.get_admin_url)

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)

    def __unicode__(self):
        """Unicode return"""
        return '{} - {}'.format(self.equipment, self.msg[:50])


class Service(models.Model):
    """Service record for equipment/components"""
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
    ticket = models.ForeignKey(Ticket,
                               null=True)
    completed = models.BooleanField("Completed",
                                    default=False)
    success = models.BooleanField("Success",
                                  default=False)
    notes = models.TextField("Notes",
                             blank=True,
                             null=True)

    @property
    def short_job_title(self):
        """shortified (TM) version of job title"""
        return self.job[:40]

    def __unicode__(self):
        """Unicode return"""
        return '{} - {} - completed: {}'.format(self.date,
                                                self.short_job_title,
                                                self.completed)

    @property
    def get_admin_url(self):
        """Generate admin URL"""
        return '/admin/scheduling/service/{}/change/'.format(self.id)

    @property
    def get_absolute_full_url(self):
        """Compile a full, absolute URL"""
        domain = Site.objects.get_current().domain.rstrip('/')
        return 'http://{}{}'.format(domain, self.get_admin_url)

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)


class Comment(models.Model):
    """Comments for Maintenance Request Tickets"""
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
        """Unicode return"""
        return '{} - {}'.format(self.user.username,
                                self.msg[:100])

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)


class Event(models.Model):
    """Equipment Scheduling Event"""

    def __init__(self, *args, **kwargs):
        """Add in initialization routines"""
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
    service = models.OneToOneField(Service,
                                   on_delete=models.CASCADE,
                                   null=True,
                                   blank=True)
    expired = models.BooleanField("Expired",
                                  default=False)

    def upcoming(self):
        """Event is still in the future"""
        if not self.expired and self.status in ['A', 'H']:
            return True
        return False
    upcoming.boolean = True

    @property
    def start_timestring_time(self):
        """Start time only to string"""
        return self.start_time.time().strftime("%I:%M%p")

    @property
    def end_timestring_time(self):
        """End time only to string"""
        return self.end_time.time().strftime("%I:%M%p")

    @property
    def start_timestring(self):
        """Start time to string"""
        return str(self.start_time)

    @property
    def end_timestring(self):
        """End time to string"""
        return str(self.end_time)

    @property
    def get_admin_url(self):
        """Generate admin URL"""
        return '/admin/scheduling/event/{}/change/'.format(self.id)

    @property
    def get_absolute_full_url(self):
        """Compile a full, absolute URL"""
        domain = Site.objects.get_current().domain.rstrip('/')
        return 'http://{}{}'.format(domain, self.get_admin_url)

    @property
    def start_timestamp(self):
        """Generate start timestamp in ms"""
        return '{0}'.format(int(mktime(self.start_time.timetuple()))*1000)

    @property
    def end_timestamp(self):
        """Generate end timestamp in ms"""
        return '{0}'.format(int(mktime(self.end_time.timetuple()))*1000)

    def get_notes(self):
        """Generate a shortened notes view"""
        if self.notes:
            return "{note}{ending}".format(note=self.notes[:25],
                                           ending="..." if len(self.notes) > 25 else "")
        return None

    def get_absolute_url(self):
        """Generate the absolute URL for this object"""
        # Using the admin change form for this
        return reverse('admin:scheduling_event_change', args=(self.id,))

    def clean(self, *args, **kwargs):
        """Add some custom validation"""
        super(Event, self).clean(*args, **kwargs)
        if not self.equipment.status:
            raise ValidationError('{} is offline.'.format(
                self.equipment.name))
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be later than start.')
        if not self.id and self.start_time < timezone.now():
            raise ValidationError('Cannot retroactively schedule an event.')
        if (self.id and
                self.end_time < timezone.now() and
                not self.user.is_superuser):
            raise ValidationError('Cannot edit an event that has expired.')
        if (any([self.maintenance, self.service])
                and (not all([self.maintenance, self.service]))):
            raise ValidationError('Maintenance must be attached with a service.')
        overlaps = self.__class__._default_manager.filter(
            end_time__gte=self.start_time,
            start_time__lte=self.end_time,
            status__in=['A', 'H'],
            expired=False,
            equipment=self.equipment).exclude(id=self.id)
        if overlaps.count() > 0:
            if self.maintenance is False:
                raise ValidationError('Overlaps with existing booking.')
            else:
                for obj in overlaps:
                    obj.status = 'C'
                    obj.save()
                    maintenance_cancellation(obj)

    def save(self, *args, **kwargs):
        """Tweak save routine to run stuff"""
        super(Event, self).save(*args, **kwargs)

    @property
    def current_status(self):
        """Stringify display name of current status"""
        return self.get_status_display()

    @property
    def hover_text(self):
        """Generate descriptive text for html viewing"""
        attrs = ['Start: {0.start_timestring_time}',
                 'End: {0.end_timestring_time}',
                 'User: {0.user.username}',
                 'Expired: {0.expired}',
                 'Status: {0.current_status}',
                 'Equipment: {0.equipment.name}',
                 'Disassemble: {0.disassemble}',
                 'Notes: {1}']
        return ' &#10; '.join(attrs).format(self, self.get_notes())

    def get_fields(self):
        """Generate field names and values for templates"""
        return get_model_fields(self)

    def __unicode__(self):
        """Unicode return"""
        return '{} - {}'.format(self.user.username,
                                self.start_timestring)

    class Meta:
        """Override some things"""
        ordering = ["-start_time"]


def email_new_user(sender, **kwargs):
    """Email new user when one is created"""
    if kwargs["created"]:
        user = kwargs["instance"]
        form = PasswordResetForm({'email': user.email})
        assert form.is_valid()
        form.save(from_email='bookit@mutaku.com',
                  use_https=True,
                  subject_template_name="scheduling/password_reset_subject.txt",
                  email_template_name="scheduling/password_reset_email.html")

post_save.connect(email_new_user, sender=User)