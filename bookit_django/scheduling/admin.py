from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from .models import Event, Equipment, Message, Ticket, Comment,\
    Service, Component, Brand, Model
from .utils import changed_event_mail, deleted_event_mail,\
    new_event_mail, ticket_email, message_email, ticket_status_toggle_email,\
    maintenance_announcement



def void(*args, **kwargs):
    """ Terrible usage of Python - empty function for pointers """
    return None


def toggle_boolean(modeladmin, request, queryset, field):
    """Toggle the boolean value of a model field"""
    for obj in queryset:
        setattr(obj, field, not getattr(obj, field))
        obj.save()


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

    def get_list_filter(self, request):
        """Tweak list filtering based on user"""
        if request.user.is_superuser:
            return ['start_time', 'user',
                    'equipment', 'maintenance']
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
        if request.user.is_superuser:
            list_display = list_display + ('maintenance', 'user',)
        return list_display

    def cancel_event(self, request, queryset):
        """Cancel an upcoming event"""
        queryset.filter(status='A', expired=False).update(status='C')

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
        """Override field getting"""
        if not request.user.is_superuser:
            self.exclude = ('maintenance', 'expired', 'status',)
        return super(EventAdmin, self).get_fields(request, obj, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        """Override form getting"""
        form = super(EventAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['equipment'].queryset = \
            form.base_fields['equipment'].\
            queryset.filter(users=request.user)
        return form

    def save_model(self, request, obj, form, change):
        """Adjust some values on save"""
        event_functions = {
            'new_event': new_event_mail,
            'maintenance': maintenance_announcement,
            'changed_event': changed_event_mail,
            'trivial_change': void
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
            # self.message_user(request,
            #                   "Created {}".format(obj.start_timestring),
            #                   messages.SUCCESS)
            # new_event_mail(obj)
            save_method = 'new_event'
            save_method_string = "Created {}".format(obj.start_timestring)
        elif obj.maintenance and request.user.is_superuser:
            # self.message_user(request,
            #                   "Maintence scheduled {}".format(
            #                     obj.start_timestring),
            #                   messages.SUCCESS)
            # maintenance_announcement(obj)
            save_method = 'maintenance'
            save_method_string = "Maintence scheduled {}".format(
                obj.start_timestring)
        elif ((any(f in ['start_time', 'end_time'] for
                   f in form.changed_data) and
               all(x is not None for x in
                   [obj.orig_start, obj.orig_end])) or
              (('status' in form.changed_data) and
                obj.status == 'C')):
            # self.message_user(request,
            #                   "changed from {} - {}".format(obj.orig_start,
            #                                                 obj.orig_end),
            #                   messages.SUCCESS)
            # changed_event_mail(obj)
            save_method = 'changed_event'
            save_method_string = "changed from {} - {}".format(
                obj.orig_start, obj.orig_end)
        #### ELSE: something has changed and we should either ignore or only alert
        ####   the event holder
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
        if request.user.is_superuser:
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
    #exclude = ('brand', 'model',)
    #inlines = [BrandInline, ModelInline]
    pass


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Service record management"""
    exclude = ('user',)
    list_display = ('date', 'user', 'equipment',
                    'component', 'short_job_title',
                    'completed', 'success')
    list_filter = ('completed', 'success', 'equipment')
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


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    """Equipment management"""

    list_display = ('name', 'brand', 'model',
                    'description', 'last_service', 'status')
    inlines = [ComponentInline]
    exclude = ('component',)

    def get_fields(self, request, obj=None, **kwargs):
        """Override field getting"""
        if not request.user.is_superuser:
            self.readonly_fields = ('admin',)
        return super(EquipmentAdmin, self).get_fields(request, obj, **kwargs)


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
                          messages.SUCCESS,)
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
    inlines = [CommentInline,]
    actions = ['toggle_ticket', 'toggle_priority']

    def get_queryset(self, request):
        """Override the queryset to enforce permissions"""
        qstring = super(TicketAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qstring
        return qstring.filter(user=request.user)

    def toggle_ticket(self, request, queryset):
        """Toggle ticket closed status"""
        toggle_boolean(self, request, queryset, 'status')
        for obj in queryset:
            ticket_status_toggle_email(obj)

    def toggle_priority(self, request, queryset):
        """Toggle ticket priority"""
        toggle_boolean(self, request, queryset, 'priority')

    def save_model(self, request, obj, form, change):
        """Adjust some values on save"""
        if getattr(obj, 'user', None) is None and obj.pk is None:
            obj.user = request.user
        elif (obj.pk and obj.user != request.user and
              not request.user.is_superuser):
            raise PermissionDenied
        # if getattr(obj, 'comment', None):
        #     form.cleaned_data['comment'] = self.comment.all()
        self.message_user(request, "Ticket {}".format(obj.id),
                          messages.SUCCESS)
        ticket_email(obj)
        super(TicketAdmin, self).save_model(request, obj, form, change)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Message management"""

    list_display = ('created', 'user', 'msg')

    def save_model(self, request, obj, form, change):
        """Adjust some values on save"""
        if getattr(obj, 'user', None) is None and obj.pk is None:
            obj.user = request.user
        elif (obj.pk and obj.user != request.user and
              not request.user.is_superuser):
            raise PermissionDenied
        self.message_user(request, "New message {}".format(obj.id),
                          messages.SUCCESS)
        message_email(obj)
        super(MessageAdmin, self).save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        """Prevent deleting events that have already occurred"""
        if (obj.pk and obj.user != request.user and
                not request.user.is_superuser):
            raise PermissionDenied
        self.message_user(request, "Deleted {}".format(obj.id),
                          messages.SUCCESS,)
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

admin.site.disable_action('delete_selected')
admin.site.register(Brand)
admin.site.register(Model)
admin.site.site_header = 'bookit'
admin.site.site_title = 'bookit'
admin.site.index_title = 'bookit'
# This shouldn't be hardcoded but the reverse wasn't working
# admin.site.site_url = reverse('scheduling')
admin.site.site_url = '/scheduling'
