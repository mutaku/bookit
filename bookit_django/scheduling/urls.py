from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^calendar/month/(?P<equipment>.*)/$',
        views.month_view, name='month_view'),
    url(r'^equipment/(?P<pk>.*)/$',
        views.EquipmentDetailView.as_view(), name='equipment-detail'),
    url(r'^messages/$',
        views.message_board, name='message_board'),
    url(r'^json/(?P<equipment>.*)/$', views.json_events, name='json_events'),
    url(r'^requestperms/(?P<pk>.*)/$',
        views.request_equipment_perms, name='request-equipment-perms'),
    url(r'^activateperms/(?P<equip_pk>\d+)/(?P<user_pk>\d+)/$',
        views.activate_equipment_perms, name='activate-equipment-perms'),
    url(r'^$',
        views.main_view, name='main_view'),
]
