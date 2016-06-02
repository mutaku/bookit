from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.utils import timezone, six
from django.core.exceptions import PermissionDenied
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.contrib.auth.models import User
from django.forms.utils import to_current_timezone
from django.forms.widgets import MultiWidget, DateInput, TimeInput
from django.utils.translation import ugettext_lazy as _
from .models import Event, Equipment, Message, Ticket, Comment, \
	Service, Component, Brand, Model, Information, Tag
from .utils import changed_event_mail, deleted_event_mail, \
	new_event_mail, ticket_mail, message_mail, ticket_status_toggle_mail, \
	maintenance_announcement, equipment_offline_email, equipment_online_email


def toggle_boolean(modeladmin, request, queryset, field):
	"""Toggle the boolean value of a model field"""
	for obj in queryset:
		setattr(obj, field, not getattr(obj, field))
		obj.save()


def is_admin(user):
	"""Fine tune admin status check for model and view interactions"""
	if user.is_superuser or user in User.objects.filter(
			groups__name="equipment_admin"):
		return True
	return False


class CustomDateTimeSplitWidget(MultiWidget):
	"""
	A Widget that splits datetime input into two <input type="text"> boxes.
	"""
	#### Not functional yet.
	supports_microseconds = False

	def __init__(self, attrs=None, date_format=None, time_format=None):
		widgets = (DateInput(attrs=attrs, format=date_format),
				   TimeInput(attrs=attrs, format=time_format))
		super(CustomDateTimeSplitWidget, self).__init__(widgets, attrs)

	def decompress(self, value):
		if value:
			# value = to_current_timezone(value)
			if isinstance(value, six.string_types):
				return value.split(',')
			else:
				value = to_current_timezone(value)
				return [value.date(), value.time().replace(microsecond=0)]
		return [None, None]


class UserCreationFormEmail(UserCreationForm):
	"""Modified user creation form for generating users"""

	def __init__(self, *args, **kwargs):
		super(UserCreationFormEmail, self).__init__(*args, **kwargs)
		self.fields['email'] = forms.EmailField(label=_("Email"), max_length=75)
		self.fields['first_name'] = forms.CharField(label=_("First Name"),
													max_length=30)
		self.fields['last_name'] = forms.CharField(label=_("Last Name"),
												   max_length=30)
		self.fields['password1'].required = False
		self.fields['password2'].required = False
		# If one field gets autocompleted but not the other, our 'neither
		# password or both password' validation will be triggered.
		self.fields['password1'].widget.attrs['autocomplete'] = 'off'
		self.fields['password2'].widget.attrs['autocomplete'] = 'off'

	def clean_password2(self):
		return None

	def save(self, commit=True):
		user = super(UserCreationForm, self).save(commit=False)
		user.set_password(User.objects.make_random_password(20))
		user.is_staff = True
		if commit:
			user.save()
		return user


class UserAdminMod(UserAdmin):
	"""Modified user admin for tweaked functionality"""
	add_form = UserCreationFormEmail
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('username', 'email', 'first_name', 'last_name',
					   )
		}),)


# class EventForm(forms.ModelForm):
#     """Tweak event form for validation"""
#     def __init__(self, *args, **kwargs):
#         self.user = kwargs.pop('user', None)
#         super(EventForm, self).__init__(*args, **kwargs)
#
#     def clean(self):
#         """Tweak cleaning validation"""
#         if self.user not in self.equipment.users.all():
#             raise ValidationError(
#               'You do not have access to this instrument.')
#         return self.cleaned_data


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
	"""Tweak the Event admin form"""

	readonly_fields = ('elapsed_hours',)
	actions = ['cancel_event']
	exclude = ()

	# formfield_overrides = {
	#     models.DateTimeField: {'widget': CustomDateTimeSplitWidget},
	# }

	def get_list_filter(self, request):
		"""Tweak list filtering based on user"""
		# if request.user.is_superuser:
		if is_admin(request.user):
			return ['start_time', 'user',
					'equipment', 'maintenance', 'service']
		return ['equipment']

	def get_list_display(self, request):
		"""Tweak list display based on user"""
		list_display = ('start_time',
						'end_time',
						'elapsed_hours',
						'upcoming',
						'equipment',
						'disassemble',
						'get_notes')
		# if request.user.is_superuser:
		if is_admin(request.user):
			list_display = list_display + ('maintenance', 'service', 'user',)
		return list_display

	def cancel_event(self, request, queryset):
		"""Cancel an upcoming event"""
		queryset.filter(status__in=['A', 'H'],
						expired=False).update(status='C')

	def has_delete_permission(self, request, obj=None):
		"""Adjust deletion permissions to use cancel"""
		if request.user.is_superuser:
			return True
		return False

	# def formfield_for_choice_field(self, db_field, request, **kwargs):
	#     """Override choice fields based on conditions"""
	#     if db_field.name == 'status' and not request.user.is_superuser:
	#         kwargs['choices'] = (
	#             ("C", "Canceled"),
	#             ("A", "Active"))
	#     return super(EventAdmin, self).formfield_for_choice_field(
	#         db_field, request, **kwargs)

	def get_fields(self, request, obj=None, **kwargs):
		"""Override field getting
		This occasionally gets buggy and I'm not sure as to why.
		Maybe the empty base-level "exclude" will help.
		"""
		# if not request.user.is_superuser:
		if not is_admin(request.user):
			self.exclude = ('maintenance', 'expired', 'status', 'service',)
		return super(EventAdmin, self).get_fields(request, obj, **kwargs)

	def get_form(self, request, obj=None, **kwargs):
		"""Override form getting"""
		form = super(EventAdmin, self).get_form(request, obj, **kwargs)
		form.base_fields['equipment'].queryset = \
			form.base_fields['equipment']. \
				queryset.filter(users=request.user)
		return form

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		event_functions = {
			'new_event': new_event_mail,
			'maintenance': maintenance_announcement,
			'cancelled_event': deleted_event_mail,
			'changed_event': changed_event_mail,
			'trivial_change': lambda x: None
		}
		if getattr(obj, 'user', None) is None:
			obj.user = request.user
		if obj.user not in obj.equipment.users.all():
			raise PermissionDenied(
				request,
				'You are not authorized for this instrument.')
		elapsed_td = (obj.end_time - obj.start_time).seconds
		obj.elapsed_hours = round(float(elapsed_td / 3600.0), 2)
		if obj.pk is None and not obj.maintenance:
			save_method = 'new_event'
			save_method_string = "Created {}".format(obj.start_timestring)
		# elif obj.maintenance and request.user.is_superuser:
		elif obj.maintenance and is_admin(request.user):
			save_method = 'maintenance'
			save_method_string = "Maintenance scheduled {}".format(
				obj.start_timestring)
		elif ('status' in form.changed_data) and obj.status == 'C':
			save_method = 'cancelled_event'
			save_method_string = "Cancelled event start on {}".format(
				obj.start_timestring)
		elif ((any(f in ['start_time', 'end_time'] for
				   f in form.changed_data) and
				   all(x is not None for x in
					   [obj.orig_start, obj.orig_end]))):
			save_method = 'changed_event'
			save_method_string = "changed from {} - {}".format(
				obj.orig_start, obj.orig_end)
		else:
			save_method = 'trivial_change'
			save_method_string = 'Adjusted event without changing booking time.'
		super(EventAdmin, self).save_model(request, obj, form, change)
		event_functions[save_method](obj)
		self.message_user(request,
						  save_method_string,
						  messages.SUCCESS)

	def get_queryset(self, request):
		"""Override the queryset to enforce permissions"""
		qstring = super(EventAdmin, self).get_queryset(request)
		# if request.user.is_superuser:
		if is_admin(request.user):
			return qstring
		return qstring.filter(user=request.user)

	def delete_model(self, request, obj):
		"""Prevent deleting events that have already occurred"""
		if getattr(obj, 'end_time', None) <= timezone.now():
			raise PermissionDenied
		self.message_user(request, "Deleted {}".format(obj.id),
						  messages.SUCCESS)
		deleted_event_mail(obj)
		super(EventAdmin, self).delete_model(request, obj)

	def response_add(self, request, obj, post_url_continue=None):
		"""Redirect back to main view after successful add"""
		self.message_user(request, 'Added {}'.format(obj.start_timestring),
						  messages.SUCCESS)
		return HttpResponseRedirect(
			'{}?{}'.format(
				reverse('month_view', args=[obj.equipment.name]),
				'year={}&month={}'.format(
					obj.start_time.year,
					obj.start_time.month)))

	def response_change(self, request, obj):
		"""Redirect back to main view after successful edit"""
		self.message_user(request, 'Edited {}'.format(obj.start_timestring),
						  messages.SUCCESS)
		return HttpResponseRedirect(
			'{}?{}'.format(
				reverse('month_view', args=[obj.equipment.name]),
				'year={}&month={}'.format(
					obj.start_time.year,
					obj.start_time.month)))

	def response_delete(self, request, obj_name, obj_id):
		"""Redirect back to main view after successful delete"""
		self.message_user(request, 'Deleted {} - {}'.format(obj_name,
															obj_id),
						  messages.SUCCESS)
		return HttpResponseRedirect(
			reverse('admin:scheduling_event_changelist'))

	def change_view(self, request, object_id, form_url='', extra_context=None):
		if not self.get_queryset(request).filter(id=object_id).exists():
			return HttpResponseRedirect(
				reverse('admin:scheduling_event_changelist'))
		return super(EventAdmin, self).change_view(request,
												   object_id,
												   form_url,
												   extra_context)

	def delete_view(self, request, object_id, extra_context=None):
		if not self.get_queryset(request).filter(id=object_id).exists():
			return HttpResponseRedirect(
				reverse('admin:scheduling_event_changelist'))
		return super(EventAdmin, self).delete_view(request,
												   object_id,
												   extra_context)

	def history_view(self, request, object_id, extra_context=None):
		if not self.get_queryset(request).filter(id=object_id).exists():
			return HttpResponseRedirect(
				reverse('admin:scheduling_event_changelist'))
		return super(EventAdmin, self).history_view(request,
													object_id,
													extra_context)


class ComponentInline(admin.TabularInline):
	"""Components to attach to equipment"""
	model = Equipment.component.through
	extra = 0
	can_delete = True


# class ServiceInline(admin.TabularInline):
#     """Service record for equipment"""
#     model = Equipment.service_record.through
#     extra = 0
#     can_delete = False


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
	"""Component management"""
	# exclude = ('brand', 'model',)
	# inlines = [BrandInline, ModelInline]
	pass


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
	"""Service record management"""
	exclude = ('user',)
	list_display = ('date', 'user', 'equipment',
					'component', 'short_job_title', 'ticket',
					'event', 'completed', 'success')
	list_filter = ('completed', 'success', 'equipment')
	list_editable = ['user']
	actions = ['toggle_completed', 'toggle_success']

	def toggle_success(self, request, queryset):
		"""Toggle ticket priority"""
		toggle_boolean(self, request, queryset, 'success')

	def toggle_completed(self, request, queryset):
		"""Toggle ticket priority"""
		toggle_boolean(self, request, queryset, 'completed')

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		if getattr(obj, 'user', None) is None:
			obj.user = request.user
		super(ServiceAdmin, self).save_model(request, obj, form, change)


@admin.register(Information)
class InformationAdmin(admin.ModelAdmin):
	"""Information Display Management"""
	list_display = ('header', 'get_body', 'user',
					'main_page_visible', 'created', 'modified')
	actions = ['toggle_main_page_visible']
	exclude = ('user',)

	def toggle_main_page_visible(self, request, queryset):
		"""Toggle visibility on main page"""
		toggle_boolean(self, request, queryset, 'main_page_visible')

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		obj.user = request.user
		super(InformationAdmin, self).save_model(request, obj, form, change)


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
	"""Equipment management"""

	list_display = ('name', 'brand', 'model',
					'description', 'last_service', 'status')
	inlines = [ComponentInline]
	exclude = ('component',)

	def get_fields(self, request, obj=None, **kwargs):
		"""Override field getting"""
		# if not request.user.is_superuser:
		if not is_admin(request.user):
			self.readonly_fields = ('admin',)
		return super(EquipmentAdmin, self).get_fields(request, obj, **kwargs)

	def save_model(self, request, obj, form, change):
		"""Adjust save routine"""
		super(EquipmentAdmin, self).save_model(request, obj, form, change)
		if 'status' in form.changed_data:
			if obj.status == False:
				equipment_offline_email(obj)
			else:
				equipment_online_email(obj)
			self.message_user(request,
							  "{} set running={}".format(obj.name, obj.status),
							  messages.SUCCESS)


class CommentInline(admin.TabularInline):
	"""Comments to attach to a ticket"""
	model = Ticket.comment.through
	extra = 0
	can_delete = False

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == 'comment' and not request.user.is_superuser:
			kwargs['queryset'] = Comment.objects.filter(user=request.user)
		return super(CommentInline, self).formfield_for_foreignkey(db_field,
																   request,
																   **kwargs)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
	"""Comment admin"""
	# inlines = [CommentInline,]
	exclude = ('comment',)

	def get_queryset(self, request):
		"""Override the queryset to enforce permissions"""
		qstring = super(CommentAdmin, self).get_queryset(request)
		if request.user.is_superuser:
			return qstring
		return qstring.filter(user=request.user)

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		if getattr(obj, 'user', None) is None and obj.pk is None:
			obj.user = request.user
		elif (obj.pk and obj.user != request.user and
				  not request.user.is_superuser):
			raise PermissionDenied
		super(CommentAdmin, self).save_model(request, obj, form, change)

	def delete_model(self, request, obj):
		"""Prevent deleting events that have already occurred"""
		if (obj.pk and obj.user != request.user and
				not request.user.is_superuser):
			raise PermissionDenied
		self.message_user(request, "Deleted {}".format(obj.id),
						  messages.SUCCESS, )
		super(CommentAdmin, self).delete_model(request, obj)

	def change_view(self, request, object_id, form_url='', extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_comment_changelist'))
		return super(CommentAdmin, self).change_view(request,
													 object_id,
													 form_url,
													 extra_context)

	def delete_view(self, request, object_id, extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_comment_changelist'))
		return super(CommentAdmin, self).delete_view(request,
													 object_id,
													 extra_context)

	def history_view(self, request, object_id, extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_comment_changelist'))
		return super(CommentAdmin, self).history_view(request,
													  object_id,
													  extra_context)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
	"""Maintenance Request Ticket management"""

	list_display = ('created', 'user', 'equipment', 'priority',
					'comment_count', 'msg', 'status')
	exclude = ('comment',)
	readonly_fields = ('status',)
	inlines = [CommentInline, ]
	actions = ['toggle_ticket', 'toggle_priority']

	def get_queryset(self, request):
		"""Override the queryset to enforce permissions"""
		qstring = super(TicketAdmin, self).get_queryset(request)
		# if request.user.is_superuser:
		if is_admin(request.user):
			return qstring
		return qstring.filter(user=request.user)

	def toggle_ticket(self, request, queryset):
		"""Toggle ticket closed status"""
		toggle_boolean(self, request, queryset, 'status')
		for obj in queryset:
			ticket_status_toggle_mail(obj)

	def toggle_priority(self, request, queryset):
		"""Toggle ticket priority"""
		toggle_boolean(self, request, queryset, 'priority')

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		if getattr(obj, 'user', None) is None and obj.pk is None:
			obj.user = request.user
		# elif (obj.pk and obj.user != request.user and
		#      not request.user.is_superuser):
		elif (obj.pk and not is_admin(request.user)):
			raise PermissionDenied
		# if getattr(obj, 'comment', None):
		#     form.cleaned_data['comment'] = self.comment.all()
		super(TicketAdmin, self).save_model(request, obj, form, change)
		self.message_user(request, "Ticket {}".format(obj.id),
						  messages.SUCCESS)
		ticket_mail(obj)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
	"""Message management"""

	list_display = ('created', 'user', 'equipment', 'msg', 'get_tags')

	def save_model(self, request, obj, form, change):
		"""Adjust some values on save"""
		if getattr(obj, 'user', None) is None and obj.pk is None:
			obj.user = request.user
		elif (obj.pk and obj.user != request.user and
				  not request.user.is_superuser):
			raise PermissionDenied
		super(MessageAdmin, self).save_model(request, obj, form, change)
		self.message_user(request, "New message {}".format(obj.id),
						  messages.SUCCESS)
		message_mail(obj)

	def delete_model(self, request, obj):
		"""Prevent deleting events that have already occurred"""
		if (obj.pk and obj.user != request.user and
				not request.user.is_superuser):
			raise PermissionDenied
		self.message_user(request, "Deleted {}".format(obj.id),
						  messages.SUCCESS, )
		super(MessageAdmin, self).delete_model(request, obj)

	def change_view(self, request, object_id, form_url='', extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_message_changelist'))
		return super(MessageAdmin, self).change_view(request,
													 object_id,
													 form_url,
													 extra_context)

	def delete_view(self, request, object_id, extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_message_changelist'))
		return super(MessageAdmin, self).delete_view(request,
													 object_id,
													 extra_context)

	def history_view(self, request, object_id, extra_context=None):
		if (not request.user.is_superuser and
				not self.get_queryset(request).
						filter(id=object_id, user=request.user).exists()):
			self.message_user(request, 'Permission denied', messages.ERROR)
			return HttpResponseRedirect(
				reverse('admin:scheduling_message_changelist'))
		return super(MessageAdmin, self).history_view(request,
													  object_id,
													  extra_context)


admin.site.unregister(User)
admin.site.register(User, UserAdminMod)
admin.site.disable_action('delete_selected')
admin.site.register(Brand)
admin.site.register(Model)
admin.site.register(Tag)
admin.site.site_header = 'bookit'
admin.site.site_title = 'bookit'
admin.site.index_title = 'bookit'
# This shouldn't be hardcoded but the reverse wasn't working
# admin.site.site_url = reverse('scheduling')
admin.site.site_url = '/scheduling'
